from datetime import datetime
import json
import os
import zoneinfo
from typing import Callable, Optional

from meal_planner.models import UserProfile, load_catalog
from meal_planner.tools.onboarding import (
    init_user_profile,
    load_user_profile,
    resolve_timezone
)
from meal_planner.tools.macro_calculator import calculate_daily_targets
from meal_planner.tools.meal_generator import generate_weekly_plan, export_meal_plan_csv
from meal_planner.tools.grocery_planner import (
    PantryState,
    generate_split_groceries,
    export_grocery_list_csv
)
from meal_planner.tools.tracker import (
    init_bookkeeping_artifacts,
    record_price,
    log_meal_consumption,
    get_analytics_summary
)
from meal_planner.tools.adaptation import (
    apply_meal_deviation,
    apply_grocery_substitution
)
from meal_planner.tools.memory import MemoryManager
from meal_planner.tools.meal_generator import (
    generate_weekly_plan,
    export_meal_plan_csv,
    ensure_weekly_plan_artifacts,
    get_current_cycle_prefix
)

def build_system_instruction(user_timezone: str = "Europe/Brussels", data_dir: str = "data") -> str:
    """Builds the system instruction prompt for the Gemini meal planner agent."""
    tz = resolve_timezone(user_timezone)
    now_local = datetime.now(tz)
    now_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    weekday_str = now_local.strftime("%A")

    # Load memory context
    mem_mgr = MemoryManager(data_dir)
    mem_ctx = mem_mgr.get_context()
    weekly_notes = "\n".join(f"  - [Weekly Note] {n}" for n in mem_ctx["weekly"]) or "  (None recorded for this week)"
    long_term_notes = "\n".join(f"  - [Durable Fact] {n}" for n in mem_ctx["long_term"]) or "  (None recorded yet)"

    profile = load_user_profile(data_dir)
    week_start_day = profile.week_start_day if profile else "Saturday"
    weeks_ahead = profile.weeks_ahead if profile else 1
    prefix = get_current_cycle_prefix(user_timezone, now_local, week_start_day=week_start_day)
    active_plan_csv = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
    active_batch_csv = os.path.join(data_dir, "plans", f"{prefix}_batch_cook.csv")
    active_grocery_csv = os.path.join(data_dir, "plans", f"{prefix}_grocery_list.csv")

    is_onboarded = bool(profile.is_onboarded and profile.bodyweight_kg > 0 and profile.target_calories > 0) if profile else False
    if profile and is_onboarded:
        ensure_weekly_plan_artifacts(profile, data_dir)
        profile_summary = (
            f"- Bodyweight: {profile.bodyweight_kg:.1f} kg | Goal: {profile.goal_state} | Target Calories: {profile.target_calories:.0f} kcal\n"
            f"- Daily Target Macros: Protein {profile.protein_multiplier * profile.bodyweight_kg:.1f}g ({profile.protein_multiplier:.1f}g/kg), "
            f"Fat {profile.fat_multiplier * profile.bodyweight_kg:.1f}g ({profile.fat_multiplier:.1f}g/kg)\n"
            f"- Week Start Day: {week_start_day} | Planning Window: Current + {weeks_ahead} week(s) ahead"
        )
        lifecycle_instructions = f"""LIFECYCLE STATE: ACTIVE PLANNING STATE (SUBSEQUENT CHAT)
- The athlete is fully onboarded. Their preferences and active meal plan ALREADY EXIST.
- ATHLETE PREFERENCES:
{profile_summary}
- Current Weekly Meal Plan Artifact: {active_plan_csv}
- Current Weekly Batch Cook Artifact: {active_batch_csv}
- Current Weekly Grocery List Artifact: {active_grocery_csv}
- DO NOT ask for onboarding preferences again.
- Direct support: Assist the athlete immediately with their planning requests (schedule lookups, meal deviations, logging eaten meals, price updates, recipe substitutions, and grocery adjustments)."""
    else:
        profile_summary = "- Profile not yet onboarded. Prompt user to onboard and configure preferences."
        currency_val = profile.currency if profile else "EUR"
        lifecycle_instructions = f"""LIFECYCLE STATE: ONBOARDING STATE (FIRST CHAT)
- You do NOT have any meal plans yet and this athlete is not yet onboarded.
- YOUR IMMEDIATE PRIORITY IN THIS FIRST CHAT:
  1. Warmly welcome the user to their AI Meal & Grocery Planner.
  2. Ask the user for their core preferences needed to calculate macros and generate their zero-waste weekly meal plan:
     - Current bodyweight in kg
     - Fitness goal (maintenance, lean_bulk, or cut)
     - Target daily calories (or let you calculate based on bodyweight and goal)
     - Dietary restrictions, preferences, or allergies (if any, default none)
     - Preferred timezone and currency (default: {user_timezone}, {currency_val})
  3. Once the user replies with their preferences (or confirms details):
     - Call `tool_onboard_user(...)` to persist their profile.
     - Call `tool_generate_meal_plan()` to generate their zero-waste weekly plan, batch cook file, and split grocery list.
     - Point the user to the newly generated plan file: {active_plan_csv}."""

    return f"""You are the AI Meal & Grocery Planner Agent, a specialized dietary, logistics, financial, and vision-enabled assistant for a powerlifting athlete.

CURRENT TEMPORAL & ARTIFACT CONTEXT:
- Local Time: {now_str} ({weekday_str})
- Timezone: {user_timezone}
- Active Cycle Prefix: {prefix} (Starting {week_start_day}, {weeks_ahead} week(s) ahead)
- Current Weekly Meal Plan Artifact: {active_plan_csv}
- Current Weekly Batch Cook Artifact: {active_batch_csv}
- Current Weekly Grocery List Artifact: {active_grocery_csv}
Always interpret relative temporal expressions ("today", "tonight", "tomorrow's lunch", "Thursday dinner") using this current local clock.

{lifecycle_instructions}

ATHLETE MEMORY:
* Short-Term (Weekly):
{weekly_notes}

* Long-Term (Monthly/Yearly Durable Preferences & History):
{long_term_notes}

CONVERSATION & COMMUNICATION POLICY (STRICT):
1. PRECISION & BREVITY:
   - Be direct, concise, and focused. Only talk about the immediate changes or preferences at hand.
   - Do NOT provide unsolicited summaries or verbose filler.
2. POINT TO THE ARTIFACT FILE:
   - When asked about schedules, recipes, meal plans, or grocery lists (e.g. "what is my schedule for this week?"):
     - If the plan file exists on disk, POINT TO THE ARTIFACT FILE: {active_plan_csv}.
     - If the plan file has not yet been generated, call `tool_generate_meal_plan` to generate it before answering.
   - ONLY print tabular meal rows or detailed lists directly in chat if the user explicitly asks you to ("print it here", "show me the plan", etc.).
3. MEMORY RETENTION & DISCRIMINATION:
   - Actively record meaningful insights with `tool_save_memory_note(note, tier)`:
     - Use tier='weekly' for temporary physical fatigue, temporary schedule shifts, or perishable roll-overs.
     - Use tier='long_term' for permanent food intolerances, durable recipe preferences, or macro milestones.
     - NEVER record trivial conversational chatter (e.g. "ok", "thank you", "sounds good", "hello").
4. NEW FOOD DETECTION & CONFIRMATION (STRICT):
   - When the user mentions a new food/ingredient (from conversation updates, shopping, or receipts/bills) not currently in the catalog:
     - DO NOT add it immediately or silently.
     - FIRST, explicitly ask the user for confirmation:
       "I found a new food: [Food Name] ([Category], ~[Protein]g P / [Carbs]g C / [Fat]g F, ~[Calories] kcal per 100g, €[Price] per [Package Size]). Would you like me to add this to your food catalog?"
     - ONLY after the user confirms (e.g. "yes", "add it", "sure", or clarifies details), call `tool_add_food_item` to save it to the catalog and prices.csv.

MULTIMODAL PHOTO HANDLING (BILLS & MEALS):
1. GROCERY BILLS / RECEIPT PHOTOS:
   - When the user uploads a photo of a store bill or receipt:
     - Detect the store name (e.g. Colruyt, Delhaize, Albert Heijn) and date.
     - Extract prices for athlete protein and staple ingredients.
     - If the item is already in the catalog, invoke `tool_log_price_update(ingredient_id, price_eur, store)`.
     - If the receipt contains a NEW food not currently recognized:
       - State that a new food was detected with estimated macros and price, and ask the user for confirmation to add it.
       - After user confirms, call `tool_add_food_item`.
     - If the user bought a substitution, call `tool_substitute_ingredient`.
     - Respond concisely with the prices logged and spend totals.
2. MEAL CONSUMPTION PHOTOS:
   - When the user uploads a photo of a meal, plate, or shake:
     - Identify the ingredients and estimate the protein (g) and calorie content from portion sizes.
     - Correlate with today's scheduled meal slot (breakfast, lunch, or dinner).
     - If it deviates from the scheduled meal (e.g. restaurant food, drinking a shake instead of cooking, extra portions), call `tool_report_meal_deviation(day, meal, actual_recipe_name, protein_consumed_g, calories_consumed)`.
     - Confirm that macros were rebalanced and state any perishable meats flagged to roll over or freeze.

CORE ATHLETE RULES:
1. Texture Rules: Breakfast & Dinner strictly soft, liquid, or broth-based (smoothies, Phở); Lunch strictly solid batch (Thịt kho, Gà xào sả ớt).
2. Dietary Bans: Fortified soy milk only (no dairy), ON Whey only, canned tuna only.
3. Raw Weights: All recipes dictate raw/dry ingredient weights.
4. Split Grocery Runs: Saturday Run (Sat-Tue meats + Sun batch prep); Wednesday Run (Wed-Fri meats + Wed batch prep). Meat fridge life <= 72h.
"""

def get_agent_tools(data_dir: str = "data") -> list[Callable]:
    """Returns the suite of callable tools bound to the specified data directory."""
    # Active weekly plan cached in memory / disk
    plan_cache = {"plan": None}

    def tool_save_memory_note(note: str, tier: str = "weekly") -> str:
        """Saves an important conversational note into short-term (weekly) or long-term memory.
        
        Args:
            note: Meaningful factual note or preference learned from user.
            tier: 'weekly' for temporary weekly notes, or 'long_term' for permanent preferences.
        """
        mgr = MemoryManager(data_dir)
        res = mgr.add_note(note, tier)
        if res["status"] == "saved":
            tier_label = "long-term" if res['tier'] == "long_term" else "weekly"
            return f"Saved to {tier_label} memory: '{note}'."
        else:
            return f"Memory note ignored: {res.get('reason', 'trivial or duplicate')}."

    def tool_onboard_user(
        timezone: str,
        bodyweight_kg: float,
        goal_state: str,
        target_calories: float,
        protein_multiplier: float,
        fat_multiplier: float,
        week_start_day: str = "Saturday",
        weeks_ahead: int = 1,
        currency: str = "EUR",
        restrictions: Optional[list[str]] = None
    ) -> str:
        """Onboards the user, stores their timezone and dietary profile, and initializes bookkeeping files."""
        # Validate calorie feasibility upfront
        try:
            calculate_daily_targets(bodyweight_kg, protein_multiplier, fat_multiplier, target_calories)
        except ValueError as e:
            return f"Error: Infeasible nutritional targets. {e}"

        profile = init_user_profile(data_dir, {
            "timezone": timezone,
            "bodyweight_kg": bodyweight_kg,
            "goal_state": goal_state,
            "target_calories": target_calories,
            "protein_multiplier": protein_multiplier,
            "fat_multiplier": fat_multiplier,
            "week_start_day": week_start_day,
            "weeks_ahead": weeks_ahead,
            "currency": currency,
            "restrictions": restrictions if restrictions is not None else [],
            "is_onboarded": True
        })
        init_bookkeeping_artifacts(data_dir)
        PantryState.load(data_dir).save(data_dir)
        return (
            f"Profile created. Profile initialized successfully for {bodyweight_kg}kg ({goal_state}). "
            f"Timezone: {profile.timezone}. Calorie target: {target_calories:.0f} kcal. "
            f"Daily targets: {bodyweight_kg * protein_multiplier:.1f}g Protein, {bodyweight_kg * fat_multiplier:.1f}g Fat. "
            f"Schedule: Week starts on {profile.week_start_day}, planning {profile.weeks_ahead} week(s) ahead."
        )

    def tool_configure_planning_schedule(
        week_start_day: Optional[str] = None,
        weeks_ahead: Optional[int] = None
    ) -> str:
        """Configures which day starts the week and how many weeks ahead are planned and retained.
        
        Args:
            week_start_day: Day that starts the planning cycle (e.g. 'Saturday', 'Monday', 'Sunday').
            weeks_ahead: Number of future weeks ahead to generate and retain (default 1 for current + next week).
        """
        profile = load_user_profile(data_dir)
        if not profile:
            return "Error: No user profile found. Please onboard first."
        if week_start_day:
            profile.week_start_day = week_start_day.strip().capitalize()
        if weeks_ahead is not None:
            profile.weeks_ahead = max(0, int(weeks_ahead))

        profile_path = os.path.join(data_dir, "profile.json")
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile.__dict__, f, indent=2)

        plan_path, grocery_path, _ = ensure_weekly_plan_artifacts(profile, data_dir, force=True)
        prefix = get_current_cycle_prefix(profile.timezone, week_start_day=profile.week_start_day)
        batch_path = os.path.join(data_dir, "plans", f"{prefix}_batch_cook.csv")

        return (
            f"Updated planning schedule: Week starts on {profile.week_start_day}, "
            f"planning {profile.weeks_ahead} week(s) ahead. Active cycle plan: {plan_path}, "
            f"batch cook: {batch_path}, groceries: {grocery_path}."
        )

    def tool_generate_meal_plan() -> str:
        """Generates or updates the weekly zero-waste meal plan, batch cook file, and split grocery list."""
        profile = load_user_profile(data_dir)
        if not profile:
            return "Error: No user profile found. Please onboard first."
        
        plan_path, grocery_path, newly_created = ensure_weekly_plan_artifacts(profile, data_dir, force=True)
        plan = generate_weekly_plan(profile)
        plan_cache["plan"] = plan

        prefix = get_current_cycle_prefix(profile.timezone, week_start_day=profile.week_start_day)
        batch_path = os.path.join(data_dir, "plans", f"{prefix}_batch_cook.csv")

        status = "Generated 7-day meal plan" if newly_created else "Active 7-day meal plan"
        return (
            f"{status} (starting {profile.week_start_day}) saved to {plan_path}. "
            f"Batch cook requirements saved to {batch_path}. "
            f"Split grocery list saved to {grocery_path}."
        )

    def tool_report_meal_deviation(
        day: str,
        meal: str,
        actual_recipe_name: str,
        protein_consumed_g: float,
        calories_consumed: float
    ) -> str:
        """Adapts the meal plan when a meal was changed or skipped, rolling over perishable meats and re-balancing macros."""
        profile = load_user_profile(data_dir)
        if not profile:
            return "Error: Profile not found."

        if plan_cache["plan"] is None:
            plan_cache["plan"] = generate_weekly_plan(profile)

        updated_plan = apply_meal_deviation(plan_cache["plan"], {
            "day": day,
            "meal": meal,
            "actual_recipe_name": actual_recipe_name,
            "protein_consumed_g": protein_consumed_g,
            "calories_consumed": calories_consumed
        })
        plan_cache["plan"] = updated_plan

        plan_csv = os.path.join(data_dir, "meal_plan.csv")
        export_meal_plan_csv(updated_plan, plan_csv)
        prefix = get_current_cycle_prefix(profile.timezone)
        dated_plan_csv = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
        if os.path.exists(os.path.dirname(dated_plan_csv)):
            export_meal_plan_csv(updated_plan, dated_plan_csv)

        # Log consumption to tracker
        log_meal_consumption(data_dir, {
            "meal": meal,
            "recipe": actual_recipe_name,
            "adherence": "adapted",
            "calories": calories_consumed,
            "notes": f"Deviation on {day}: {actual_recipe_name}"
        })

        rollover_info = ""
        if updated_plan.rollover_items:
            latest = updated_plan.rollover_items[-1]
            rollover_info = f" Perishable safety: {latest['name']} ({latest['raw_weight_g']}g) flagged for {latest['action']}."

        return f"Adapted meal plan for {day} {meal}. CSV updated at {dated_plan_csv if os.path.exists(dated_plan_csv) else plan_csv}.{rollover_info}"

    def tool_substitute_ingredient(
        original_id: str,
        new_ingredient_id: str,
        new_price_eur: float
    ) -> str:
        """Substitutes an ingredient across upcoming meals due to stock/price friction, recalibrating raw weights."""
        profile = load_user_profile(data_dir)
        if not profile:
            return "Error: Profile not found."
        if plan_cache["plan"] is None:
            plan_cache["plan"] = generate_weekly_plan(profile)

        updated = apply_grocery_substitution(plan_cache["plan"], original_id, new_ingredient_id, new_price_eur, data_dir=data_dir)
        plan_cache["plan"] = updated

        plan_csv = os.path.join(data_dir, "meal_plan.csv")
        export_meal_plan_csv(updated, plan_csv)
        prefix = get_current_cycle_prefix(profile.timezone)
        dated_plan_csv = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
        if os.path.exists(os.path.dirname(dated_plan_csv)):
            export_meal_plan_csv(updated, dated_plan_csv)

        record_price(data_dir, new_ingredient_id, "Colruyt", new_price_eur)
        return f"Substituted {original_id} with {new_ingredient_id}. Recalibrated raw protein weights and updated {dated_plan_csv if os.path.exists(dated_plan_csv) else plan_csv}."

    def tool_log_price_update(
        ingredient_id: str,
        price_eur: float,
        store: str = "Colruyt"
    ) -> str:
        """Logs an observed unit price for an ingredient into prices.csv."""
        record_price(data_dir, ingredient_id, store, price_eur)
        return f"Recorded price for {ingredient_id}: €{price_eur:.2f} at {store}."

    def tool_get_analytics() -> str:
        """Retrieves financial and nutritional tracking summaries from local CSVs."""
        summary = get_analytics_summary(data_dir)
        return (
            f"Analytics Summary: Total protein spend logged: €{summary['total_protein_spend_eur']:.2f}. "
            f"Logged meals: {summary['logged_meals_count']}. Adherence rate: {summary['adherence_rate_pct']}%. "
            f"Avg calories per logged meal: {summary['average_calories_per_logged_meal']:.0f} kcal."
        )

    def tool_view_grocery_list() -> str:
        """Returns a summary of the current split grocery list."""
        profile = load_user_profile(data_dir)
        prefix = get_current_cycle_prefix(
            profile.timezone if profile else "UTC",
            week_start_day=profile.week_start_day if profile else "Saturday"
        )
        dated_grocery = os.path.join(data_dir, "plans", f"{prefix}_grocery_list.csv")
        path = dated_grocery if os.path.exists(dated_grocery) else os.path.join(data_dir, "grocery_list.csv")
        if not os.path.exists(path):
            return "No grocery list CSV generated yet. Please generate a meal plan first."
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[:15]) + ("\n... [remaining items in CSV]" if len(lines) > 15 else "")

    def tool_view_batch_cook_list() -> str:
        """Returns a summary of the batch-cooked dishes for the current week and their grocery requirements."""
        profile = load_user_profile(data_dir)
        prefix = get_current_cycle_prefix(
            profile.timezone if profile else "UTC",
            week_start_day=profile.week_start_day if profile else "Saturday"
        )
        dated_batch = os.path.join(data_dir, "plans", f"{prefix}_batch_cook.csv")
        path = dated_batch if os.path.exists(dated_batch) else os.path.join(data_dir, "batch_cook.csv")
        if not os.path.exists(path):
            return "No batch cook CSV generated yet. Please generate a meal plan first."
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[:15]) + ("\n... [remaining items in CSV]" if len(lines) > 15 else "")

    def tool_add_food_item(
        name: str,
        category: str,
        protein_per_100g: float,
        fat_per_100g: float = 0.0,
        carbs_per_100g: float = 0.0,
        calories_per_100g: float = 0.0,
        package_size_g: float = 500.0,
        unit_price_eur: float = 1.99,
        perishable: bool = True,
        unit_type: str = "per_pack",
        store: str = "Colruyt"
    ) -> str:
        """Adds a new food item to the catalog and logs its price into prices.csv.
        
        Call this tool AFTER confirming with the user that they want to add the newly found food.
        
        Args:
            name: Human-readable name of the food (e.g. 'Skim Skyr', 'Cottage Cheese', 'Frozen Edamame').
            category: Food category ('dairy', 'dairy_alternative', 'meat', 'seafood', 'vegetable', 'fruit', 'grains', 'pantry', 'supplement').
            protein_per_100g: Protein in grams per 100g.
            fat_per_100g: Fat in grams per 100g.
            carbs_per_100g: Carbohydrates in grams per 100g.
            calories_per_100g: Total calories per 100g (calculated automatically if 0).
            package_size_g: Total weight or volume per package in grams (e.g. 500.0).
            unit_price_eur: Price per package in EUR.
            perishable: True if refrigerated/fresh perishable food, False if shelf-stable pantry item.
            unit_type: Package descriptor (e.g. 'per_pack', 'per_tub', 'per_kg', 'per_bottle').
            store: Store where item was purchased or observed (default 'Colruyt').
        """
        import re
        from meal_planner.models import Ingredient, add_ingredient_to_catalog
        
        clean_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if not clean_id:
            clean_id = "custom_food"

        calc_kcal = calories_per_100g
        if calc_kcal <= 0:
            calc_kcal = round(protein_per_100g * 4.0 + carbs_per_100g * 4.0 + fat_per_100g * 9.0, 1)

        new_ingredient = Ingredient(
            id=clean_id,
            name=name,
            category=category.lower(),
            protein_per_100g=round(float(protein_per_100g), 1),
            fat_per_100g=round(float(fat_per_100g), 1),
            carbs_per_100g=round(float(carbs_per_100g), 1),
            calories_per_100g=round(float(calc_kcal), 1),
            package_size_g=round(float(package_size_g), 1),
            unit_price_eur=round(float(unit_price_eur), 2),
            perishable=bool(perishable),
            unit_type=unit_type
        )

        add_ingredient_to_catalog(new_ingredient, data_dir=data_dir)
        record_price(data_dir, clean_id, store, float(unit_price_eur), unit_type)

        return (
            f"Added '{name}' (ID: {clean_id}) to catalog under {category.capitalize()}. "
            f"Macros per 100g: {protein_per_100g:.1f}g P, {carbs_per_100g:.1f}g C, {fat_per_100g:.1f}g F ({calc_kcal:.0f} kcal). "
            f"Package: {int(round(package_size_g))}g, €{unit_price_eur:.2f} at {store}. "
            f"Logged to prices.csv and ready for meal planning & substitutions."
        )

    return [
        tool_save_memory_note,
        tool_onboard_user,
        tool_configure_planning_schedule,
        tool_generate_meal_plan,
        tool_report_meal_deviation,
        tool_substitute_ingredient,
        tool_log_price_update,
        tool_get_analytics,
        tool_view_grocery_list,
        tool_view_batch_cook_list,
        tool_add_food_item
    ]

def get_root_agent(data_dir: str = "data"):
    """Instantiates the Google ADK Agent for the Meal Planner."""
    try:
        from google.adk import Agent
    except ImportError:
        return None

    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    profile = load_user_profile(data_dir)
    user_tz = profile.timezone if profile else "Europe/Brussels"
    if profile and profile.is_onboarded and profile.target_calories > 0:
        ensure_weekly_plan_artifacts(profile, data_dir)
    tools = get_agent_tools(data_dir)

    def dynamic_instruction(ctx=None) -> str:
        p = load_user_profile(data_dir)
        tz_name = p.timezone if p else user_tz
        return build_system_instruction(tz_name, data_dir=data_dir)

    return Agent(
        name="meal_planner",
        model=model_name,
        description="AI Meal & Grocery Planner Agent with multimodal receipt and meal analysis for powerlifting athlete.",
        instruction=dynamic_instruction,
        tools=tools,
    )

root_agent = get_root_agent("data")
