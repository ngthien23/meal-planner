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

def build_system_instruction(user_timezone: str = "UTC") -> str:
    """Builds the system instruction prompt for the Gemini meal planner agent."""
    tz = resolve_timezone(user_timezone)
    now_local = datetime.now(tz)
    now_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    weekday_str = now_local.strftime("%A")

    return f"""You are the AI Meal & Grocery Planner Agent, a specialized dietary, logistics, and financial assistant for a powerlifting athlete.

CURRENT TEMPORAL CONTEXT:
- Local Time: {now_str} ({weekday_str})
- Timezone: {user_timezone}
Always interpret relative temporal expressions ("today", "tonight", "tomorrow's lunch", "Thursday dinner") using this current local clock.

CORE ATHLETE CONSTRAINTS & RULES:
1. Texture & Fatigue Rules:
   - Breakfast and Dinner MUST STRICTLY be soft, liquid, or broth-based (e.g. ON Whey smoothies, Phở with thinly sliced meat in hot broth) to prevent chewing fatigue.
   - Lunch MUST STRICTLY be solid, savory, batch-cooked meals (e.g. Thịt kho tàu, Gà xào sả ớt with steamed jasmine rice).
2. Dietary Bans:
   - NO dairy milk (fortified soy milk only due to acne).
   - NO non-Optimum Nutrition whey (digestive issues; ON Gold Standard Whey only).
   - NO fresh tuna (canned tuna in brine only).
3. Precision Raw Weights:
   - All meal plans must specify raw/dry ingredient weights (e.g., "110g dry pho noodles", "200g raw lean beef"). Never cooked weights.
4. Zero-Waste Logistics & Split Grocery Runs:
   - The weekly plan runs Saturday through Friday.
   - Perishable packages (like 1kg frozen shrimp) are split evenly across meals with 0% waste.
   - Fresh meat cannot sit in the fridge > 48-72 hours. Shopping is strictly partitioned into:
     - Saturday Run (for Sat/Sun meals, Sunday batch prep, Sat-Tue meats)
     - Wednesday Run (for Wed batch prep, Wed-Fri meats)
     - Pantry Restock (for bulk staples like 2.27kg whey tub when low)

YOUR CAPABILITIES & TOOLS:
- Onboard new users and record profile preferences (`tool_onboard_user`).
- Generate weekly zero-waste meal plans and split grocery CSV artifacts (`tool_generate_meal_plan`).
- Adapt to real-world friction (skipped dinner, extra shakes, grocery substitutions) in real time (`tool_report_meal_deviation`, `tool_substitute_ingredient`).
- Track grocery unit prices and report trends (`tool_log_price_update`, `tool_get_analytics`).

When a user chats with you:
- Be concise, helpful, and athletic-focused.
- If no profile exists yet, guide them warmly through onboarding.
- Whenever plan changes occur, call the relevant tools so CSV artifacts stay up-to-date locally, and explain the changes conversationally.
"""

def get_agent_tools(data_dir: str = "data") -> list[Callable]:
    """Returns the suite of callable tools bound to the specified data directory."""
    # Active weekly plan cached in memory / disk
    plan_cache = {"plan": None}

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
        """Generates the weekly zero-waste meal plan and split grocery list, exporting CSV artifacts."""
        profile = load_user_profile(data_dir)
        if not profile:
            return "Error: No user profile found. Please onboard first."
        
        plan = generate_weekly_plan(profile)
        plan_cache["plan"] = plan

        plan_csv = os.path.join(data_dir, "meal_plan.csv")
        export_meal_plan_csv(plan, plan_csv)

        pantry = PantryState.load(data_dir)
        groceries = generate_split_groceries(plan, pantry)
        grocery_csv = os.path.join(data_dir, "grocery_list.csv")
        export_grocery_list_csv(groceries, grocery_csv)

        return (
            f"Generated 7-day meal plan (Saturday-Friday) and saved to {plan_csv}. "
            f"Split grocery list (Saturday Run, Wednesday Run, Pantry Restock) saved to {grocery_csv}."
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

        return f"Adapted meal plan for {day} {meal}. CSV updated at {plan_csv}.{rollover_info}"

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

        record_price(data_dir, new_ingredient_id, "Colruyt", new_price_eur)
        return f"Substituted {original_id} with {new_ingredient_id}. Recalibrated raw protein weights and updated {plan_csv}."

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
        path = os.path.join(data_dir, "grocery_list.csv")
        if not os.path.exists(path):
            return "No grocery list CSV generated yet. Please generate a meal plan first."
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[:15]) + ("\n... [remaining items in CSV]" if len(lines) > 15 else "")

    return [
        tool_onboard_user,
        tool_generate_meal_plan,
        tool_report_meal_deviation,
        tool_substitute_ingredient,
        tool_log_price_update,
        tool_get_analytics,
        tool_view_grocery_list
    ]
