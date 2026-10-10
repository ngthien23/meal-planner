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

    prefix = get_current_cycle_prefix(user_timezone, now_local)
    active_plan_csv = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
    active_grocery_csv = os.path.join(data_dir, "plans", f"{prefix}_grocery_list.csv")

    profile = load_user_profile(data_dir)
    if profile:
        profile_summary = (
            f"- Bodyweight: {profile.bodyweight_kg:.1f} kg | Goal: {profile.goal_state} | Target Calories: {profile.target_calories:.0f} kcal\n"
            f"- Daily Target Macros: Protein {profile.protein_multiplier * profile.bodyweight_kg:.1f}g ({profile.protein_multiplier:.1f}g/kg), "
            f"Fat {profile.fat_multiplier * profile.bodyweight_kg:.1f}g ({profile.fat_multiplier:.1f}g/kg)"
        )
    else:
        profile_summary = "- Profile not yet onboarded. Prompt user to onboard if requested."

    return f"""You are the AI Meal & Grocery Planner Agent, a specialized dietary, logistics, financial, and vision-enabled assistant for a powerlifting athlete.

CURRENT TEMPORAL & ARTIFACT CONTEXT:
- Local Time: {now_str} ({weekday_str})
- Timezone: {user_timezone}
- Active Cycle Prefix: {prefix} (Saturday-to-Friday)
- Current Weekly Meal Plan Artifact: {active_plan_csv}
- Current Weekly Grocery List Artifact: {active_grocery_csv}
Always interpret relative temporal expressions ("today", "tonight", "tomorrow's lunch", "Thursday dinner") using this current local clock.

ATHLETE PREFERENCES:
{profile_summary}

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
   - When asked about schedules, recipes, meal plans, or grocery lists (e.g. "what is my schedule for this week?"), POINT TO THE ARTIFACT FILE: {active_plan_csv}.
   - ONLY print tabular meal rows or detailed lists directly in chat if the user explicitly asks you to ("print it here", "show me the plan", etc.).
3. MEMORY RETENTION & DISCRIMINATION:
   - Actively record meaningful insights with `tool_save_memory_note(note, tier)`:
     - Use tier='weekly' for temporary physical fatigue, temporary schedule shifts, or perishable roll-overs.
     - Use tier='long_term' for permanent food intolerances, durable recipe preferences, or macro milestones.
     - NEVER record trivial conversational chatter (e.g. "ok", "thank you", "sounds good", "hello").

MULTIMODAL PHOTO HANDLING (BILLS & MEALS):
1. GROCERY BILLS / RECEIPT PHOTOS:
   - When the user uploads a photo of a store bill or receipt:
     - Detect the store name (e.g. Colruyt, Delhaize, Albert Heijn) and date.
     - Extract prices for athlete protein and staple ingredients (chicken breast, pork shoulder, flank steak, eggs, shrimp, soy milk, rice).
     - Calculate unit price (€/kg or €/unit).
     - Invoke `tool_log_price_update(ingredient_id, price_eur, store)` for matched items.
     - If the user bought a substitution, call `tool_substitute_ingredient`.
     - Respond concisely with the prices logged and updated spend totals.
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
        fat_multiplier: float
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
            "fat_multiplier": fat_multiplier
        })
        init_bookkeeping_artifacts(data_dir)
        PantryState.load(data_dir).save(data_dir)
        return (
            f"Profile created successfully for {bodyweight_kg}kg ({goal_state}). "
            f"Timezone: {profile.timezone}. Calorie target: {target_calories:.0f} kcal. "
            f"Daily targets: {bodyweight_kg * protein_multiplier:.1f}g Protein, {bodyweight_kg * fat_multiplier:.1f}g Fat."
        )

    def tool_generate_meal_plan() -> str:
        """Generates or updates the weekly zero-waste meal plan and split grocery list, exporting CSV artifacts."""
        profile = load_user_profile(data_dir)
        if not profile:
            return "Error: No user profile found. Please onboard first."
        
        plan_path, grocery_path, newly_created = ensure_weekly_plan_artifacts(profile, data_dir)
        plan = generate_weekly_plan(profile)
        plan_cache["plan"] = plan

        status = "Generated 7-day meal plan" if newly_created else "Active 7-day meal plan"
        return (
            f"{status} (Saturday-Friday) saved to {plan_path}. "
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

        updated = apply_grocery_substitution(plan_cache["plan"], original_id, new_ingredient_id, new_price_eur)
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
        prefix = get_current_cycle_prefix(profile.timezone if profile else "UTC")
        dated_grocery = os.path.join(data_dir, "plans", f"{prefix}_grocery_list.csv")
        path = dated_grocery if os.path.exists(dated_grocery) else os.path.join(data_dir, "grocery_list.csv")
        if not os.path.exists(path):
            return "No grocery list CSV generated yet. Please generate a meal plan first."
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[:15]) + ("\n... [remaining items in CSV]" if len(lines) > 15 else "")

    return [
        tool_save_memory_note,
        tool_onboard_user,
        tool_generate_meal_plan,
        tool_report_meal_deviation,
        tool_substitute_ingredient,
        tool_log_price_update,
        tool_get_analytics,
        tool_view_grocery_list
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
