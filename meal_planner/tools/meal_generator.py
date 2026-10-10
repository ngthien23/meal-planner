import csv
import os
import re
from datetime import datetime, timedelta
from typing import Optional
from meal_planner.models import (
    load_catalog,
    UserProfile,
    MealSlot,
    DayPlan,
    WeeklyPlan,
    Recipe,
    Ingredient
)
from meal_planner.tools.macro_calculator import calculate_daily_targets, solve_protein_raw_weight

DAY_NAME_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}

MEAL_BY_DAY = {
    "Saturday": ("whey_soy_smoothie", "ga_xao_sa_ot_fresh", "pho_shrimp"),
    "Sunday": ("avocado_soy_shake", "ga_xao_sa_ot_fresh", "pho_shrimp"),
    "Monday": ("whey_soy_smoothie", "thit_kho_tau", "pho_beef"),
    "Tuesday": ("whey_soy_smoothie", "thit_kho_tau", "pho_beef"),
    "Wednesday": ("avocado_soy_shake", "thit_kho_tau", "pho_beef"),
    "Thursday": ("whey_soy_smoothie", "ga_xao_sa_ot", "pho_shrimp"),
    "Friday": ("whey_soy_smoothie", "ga_xao_sa_ot", "pho_shrimp"),
}

def _build_meal_slot(
    recipe: Recipe,
    target_protein: float,
    ingredients_catalog: dict[str, Ingredient]
) -> MealSlot:
    """Builds a MealSlot with raw ingredient weights adjusted to meet target protein, tracking veg and fruit macros."""
    total_p = 0.0
    total_f = 0.0
    total_c = 0.0
    total_kcal = 0.0
    total_veg = 0.0
    total_fruit = 0.0
    resolved_ingredients = []

    # Identify if recipe has a variable protein source
    protein_id = recipe.protein_ingredient_id
    base_protein_from_others = 0.0

    # First pass: calculate baseline protein from non-primary ingredients
    for item in recipe.base_ingredients:
        ing_id = item["id"]
        ing = ingredients_catalog.get(ing_id)
        if not ing:
            continue
        if ing_id != protein_id:
            weight = item["raw_weight_g"]
            base_protein_from_others += (weight / 100.0) * ing.protein_per_100g

    # Adjust primary protein ingredient if present
    for item in recipe.base_ingredients:
        ing_id = item["id"]
        ing = ingredients_catalog.get(ing_id)
        if not ing:
            continue
        weight = item["raw_weight_g"]
        if ing_id == protein_id and ing.protein_per_100g > 0:
            weight = solve_protein_raw_weight(target_protein, base_protein_from_others, ing.protein_per_100g)

        p = (weight / 100.0) * ing.protein_per_100g
        f = (weight / 100.0) * ing.fat_per_100g
        c = (weight / 100.0) * ing.carbs_per_100g
        kcal = (weight / 100.0) * ing.calories_per_100g

        total_p += p
        total_f += f
        total_c += c
        total_kcal += kcal

        if ing.category == "vegetable":
            total_veg += weight
        elif ing.category == "fruit":
            total_fruit += weight

        weight_rounded = int(round(weight))
        label = f"{weight_rounded}g raw/dry {ing.name}"
        resolved_ingredients.append({
            "id": ing_id,
            "name": ing.name,
            "raw_weight_g": weight_rounded,
            "label": label
        })

    return MealSlot(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        meal_type=recipe.meal_type,
        texture=recipe.texture,
        ingredients=resolved_ingredients,
        protein_g=round(total_p, 1),
        fat_g=round(total_f, 1),
        carbs_g=round(total_c, 1),
        calories=round(total_kcal, 1),
        prep_type=recipe.prep_type,
        veg_g=int(round(total_veg)),
        fruit_g=int(round(total_fruit))
    )

def generate_weekly_plan(
    profile: UserProfile,
    start_date: Optional[str] = None
) -> WeeklyPlan:
    """Generates a 7-day zero-waste meal plan satisfying texture rules starting on profile.week_start_day."""
    ingredients_catalog, recipes_catalog = load_catalog()
    macro_targets = calculate_daily_targets(
        profile.bodyweight_kg,
        profile.protein_multiplier,
        profile.fat_multiplier,
        profile.target_calories
    )

    # Base reference date: start_date if given, else current cycle start based on profile.week_start_day
    if start_date:
        base_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        now = datetime.now()
        start_day_name = getattr(profile, "week_start_day", "Saturday")
        start_wd = DAY_NAME_MAP.get(start_day_name.lower(), 5)
        days_since_start = (now.weekday() - start_wd) % 7
        base_dt = now - timedelta(days=days_since_start)

    # Target protein distribution: Breakfast ~25-30%, Lunch ~35%, Dinner ~35%
    p_breakfast = round(macro_targets.protein_g * 0.28, 1)
    p_lunch = round(macro_targets.protein_g * 0.36, 1)
    p_dinner = round(macro_targets.protein_g * 0.36, 1)

    days = []
    for i in range(7):
        day_dt = base_dt + timedelta(days=i)
        day_name = day_dt.strftime("%A")
        date_str = day_dt.strftime("%Y-%m-%d")

        b_id, l_id, d_id = MEAL_BY_DAY.get(day_name, ("whey_soy_smoothie", "ga_xao_sa_ot_fresh", "pho_shrimp"))

        b_slot = _build_meal_slot(recipes_catalog[b_id], p_breakfast, ingredients_catalog)
        l_slot = _build_meal_slot(recipes_catalog[l_id], p_lunch, ingredients_catalog)
        d_slot = _build_meal_slot(recipes_catalog[d_id], p_dinner, ingredients_catalog)

        tot_p = round(b_slot.protein_g + l_slot.protein_g + d_slot.protein_g, 1)
        tot_f = round(b_slot.fat_g + l_slot.fat_g + d_slot.fat_g, 1)
        tot_c = round(b_slot.carbs_g + l_slot.carbs_g + d_slot.carbs_g, 1)
        tot_kcal = round(b_slot.calories + l_slot.calories + d_slot.calories, 1)
        tot_veg = b_slot.veg_g + l_slot.veg_g + d_slot.veg_g
        tot_fruit = b_slot.fruit_g + l_slot.fruit_g + d_slot.fruit_g

        days.append(DayPlan(
            day_name=day_name,
            date_str=date_str,
            breakfast=b_slot,
            lunch=l_slot,
            dinner=d_slot,
            total_protein_g=tot_p,
            total_fat_g=tot_f,
            total_carbs_g=tot_c,
            total_calories=tot_kcal,
            total_veg_g=tot_veg,
            total_fruit_g=tot_fruit
        ))

    return WeeklyPlan(days=days, rollover_items=[])

def export_meal_plan_csv(plan: WeeklyPlan, filepath: str) -> None:
    """Exports the weekly meal plan to CSV with strict columns and rounded integers."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    fieldnames = [
        "Date", "Meal", "Recipe", "Ingredient", "P", "C", "F", "Calories"
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for day in plan.days:
            for slot in [day.breakfast, day.lunch, day.dinner]:
                ingredients_str = "; ".join(item.get("label", f"{int(round(item['raw_weight_g']))}g raw {item['name']}") for item in slot.ingredients)
                writer.writerow({
                    "Date": day.date_str,
                    "Meal": slot.meal_type.capitalize(),
                    "Recipe": slot.recipe_name,
                    "Ingredient": ingredients_str,
                    "P": int(round(slot.protein_g)),
                    "C": int(round(slot.carbs_g)),
                    "F": int(round(slot.fat_g)),
                    "Calories": int(round(slot.calories))
                })

def export_batch_cook_csv(plan: WeeklyPlan, filepath: str) -> None:
    """Exports a dedicated CSV showing batch-cooked dishes for the week, main protein amount, and meal count."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    fieldnames = [
        "Dish", "Main_Protein", "Meals"
    ]

    # Collect batch-cooked slots from the weekly plan
    batch_dishes: dict[str, dict] = {}
    for day in plan.days:
        for slot in [day.breakfast, day.lunch, day.dinner]:
            if slot.prep_type == "batch_reheatable":
                recipe_name = slot.recipe_name
                if recipe_name not in batch_dishes:
                    batch_dishes[recipe_name] = {
                        "dish": recipe_name,
                        "portions": 0,
                        "ingredients": {}
                    }
                batch_dishes[recipe_name]["portions"] += 1
                for item in slot.ingredients:
                    ing_name = item["name"]
                    w = float(item["raw_weight_g"])
                    batch_dishes[recipe_name]["ingredients"][ing_name] = (
                        batch_dishes[recipe_name]["ingredients"].get(ing_name, 0.0) + w
                    )

    protein_keywords = [
        "pork belly", "chicken breast", "chicken thigh", "beef", "shrimp",
        "fish", "salmon", "tofu", "tuna", "pork", "chicken", "turkey", "egg"
    ]
    rows = []
    for dish_info in batch_dishes.values():
        best_match = None
        best_weight = 0.0
        for ing_name, tot_w in dish_info["ingredients"].items():
            lower_name = ing_name.lower()
            is_prot = any(kw in lower_name for kw in protein_keywords)
            if is_prot and tot_w > best_weight:
                best_match = ing_name
                best_weight = tot_w
        if not best_match and dish_info["ingredients"]:
            best_match, best_weight = max(dish_info["ingredients"].items(), key=lambda x: x[1])

        main_protein_str = f"{int(round(best_weight))}g {best_match}" if best_match else ""
        rows.append({
            "Dish": dish_info["dish"],
            "Main_Protein": main_protein_str,
            "Meals": str(dish_info["portions"])
        })

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def get_current_cycle_prefix(
    tz_name: str = "UTC",
    reference_dt: Optional[datetime] = None,
    week_start_day: str = "Saturday"
) -> str:
    """Calculates the YYMMDD prefix for the cycle start date based on week_start_day."""
    from meal_planner.tools.onboarding import resolve_timezone
    tz = resolve_timezone(tz_name)
    now = reference_dt if reference_dt is not None else datetime.now(tz)
    start_wd = DAY_NAME_MAP.get(week_start_day.lower(), 5)
    days_since_start = (now.weekday() - start_wd) % 7
    cycle_start = now - timedelta(days=days_since_start)
    return cycle_start.strftime("%y%m%d")

def ensure_weekly_plan_artifacts(
    profile: UserProfile,
    data_dir: str,
    reference_dt: Optional[datetime] = None,
    force: bool = False
) -> tuple[str, str, bool]:
    """Ensures isolated weekly meal plan, batch cook, and grocery CSVs exist for current and future weeks.
    
    Generates files for the current week and next `profile.weeks_ahead` weeks (default 1).
    Prunes any weekly files outside this active window.
    
    Returns:
        tuple[plan_path, grocery_path, newly_created]
    """
    from meal_planner.tools.onboarding import resolve_timezone
    from meal_planner.tools.grocery_planner import PantryState, generate_split_groceries, export_grocery_list_csv

    plans_dir = os.path.join(data_dir, "plans")
    os.makedirs(plans_dir, exist_ok=True)

    tz = resolve_timezone(profile.timezone)
    now = reference_dt if reference_dt is not None else datetime.now(tz)

    start_day_name = getattr(profile, "week_start_day", "Saturday")
    start_wd = DAY_NAME_MAP.get(start_day_name.lower(), 5)
    days_since_start = (now.weekday() - start_wd) % 7
    cycle_start = now - timedelta(days=days_since_start)

    weeks_ahead = max(0, int(getattr(profile, "weeks_ahead", 1)))
    valid_prefixes = set()

    current_plan_path = None
    current_grocery_path = None
    any_newly_created = False

    pantry = PantryState.load(data_dir)

    for w in range(weeks_ahead + 1):
        w_start_dt = cycle_start + timedelta(weeks=w)
        prefix = w_start_dt.strftime("%y%m%d")
        valid_prefixes.add(prefix)

        plan_path = os.path.join(plans_dir, f"{prefix}_meal_plan.csv")
        grocery_path = os.path.join(plans_dir, f"{prefix}_grocery_list.csv")
        batch_path = os.path.join(plans_dir, f"{prefix}_batch_cook.csv")

        if w == 0:
            current_plan_path = plan_path
            current_grocery_path = grocery_path

        needs_gen = force or not (os.path.exists(plan_path) and os.path.exists(grocery_path) and os.path.exists(batch_path))

        if needs_gen:
            plan = generate_weekly_plan(profile, start_date=w_start_dt.strftime("%Y-%m-%d"))
            export_meal_plan_csv(plan, plan_path)
            export_batch_cook_csv(plan, batch_path)
            groceries = generate_split_groceries(plan, pantry)
            export_grocery_list_csv(groceries, grocery_path)
            any_newly_created = True

            if w == 0:
                export_meal_plan_csv(plan, os.path.join(data_dir, "meal_plan.csv"))
                export_grocery_list_csv(groceries, os.path.join(data_dir, "grocery_list.csv"))
                export_batch_cook_csv(plan, os.path.join(data_dir, "batch_cook.csv"))

    # Retention Window Pruning: remove any weekly plan files in plans_dir outside valid_prefixes
    for filename in os.listdir(plans_dir):
        m = re.match(r"^(\d{6})_(meal_plan|grocery_list|batch_cook)\.csv$", filename)
        if m:
            file_prefix = m.group(1)
            if file_prefix not in valid_prefixes:
                try:
                    os.remove(os.path.join(plans_dir, filename))
                except OSError:
                    pass

    return current_plan_path, current_grocery_path, any_newly_created
