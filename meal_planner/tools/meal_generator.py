import csv
import os
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

def _build_meal_slot(
    recipe: Recipe,
    target_protein: float,
    ingredients_catalog: dict[str, Ingredient]
) -> MealSlot:
    """Builds a MealSlot with raw ingredient weights adjusted to meet target protein."""
    total_p = 0.0
    total_f = 0.0
    total_c = 0.0
    total_kcal = 0.0
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

        label = f"{round(weight, 1)}g raw/dry {ing.name}"
        resolved_ingredients.append({
            "id": ing_id,
            "name": ing.name,
            "raw_weight_g": round(weight, 1),
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
        prep_type=recipe.prep_type
    )

def generate_weekly_plan(
    profile: UserProfile,
    start_date: Optional[str] = None
) -> WeeklyPlan:
    """Generates a 7-day Saturday-to-Friday zero-waste meal plan satisfying texture rules."""
    ingredients_catalog, recipes_catalog = load_catalog()
    macro_targets = calculate_daily_targets(
        profile.bodyweight_kg,
        profile.protein_multiplier,
        profile.fat_multiplier,
        profile.target_calories
    )

    # Base reference date: next or current Saturday
    if start_date:
        base_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        now = datetime.now()
        days_to_saturday = (5 - now.weekday()) % 7
        base_dt = now + timedelta(days=days_to_saturday)

    # Target protein distribution: Breakfast ~25-30%, Lunch ~35%, Dinner ~35%
    p_breakfast = round(macro_targets.protein_g * 0.28, 1)
    p_lunch = round(macro_targets.protein_g * 0.36, 1)
    p_dinner = round(macro_targets.protein_g * 0.36, 1)

    # 7-day template (Saturday to Friday)
    schedule_template = [
        # (Day name, breakfast_id, lunch_id, dinner_id)
        ("Saturday", "whey_soy_smoothie", "ga_xao_sa_ot_fresh", "pho_shrimp"),
        ("Sunday", "avocado_soy_shake", "ga_xao_sa_ot_fresh", "pho_shrimp"),
        ("Monday", "whey_soy_smoothie", "thit_kho_tau", "pho_beef"),
        ("Tuesday", "whey_soy_smoothie", "thit_kho_tau", "pho_beef"),
        ("Wednesday", "avocado_soy_shake", "thit_kho_tau", "pho_beef"),
        ("Thursday", "whey_soy_smoothie", "ga_xao_sa_ot", "pho_shrimp"),
        ("Friday", "whey_soy_smoothie", "ga_xao_sa_ot", "pho_shrimp"),
    ]

    days = []
    for i, (day_name, b_id, l_id, d_id) in enumerate(schedule_template):
        day_dt = base_dt + timedelta(days=i)
        date_str = day_dt.strftime("%Y-%m-%d")

        b_slot = _build_meal_slot(recipes_catalog[b_id], p_breakfast, ingredients_catalog)
        l_slot = _build_meal_slot(recipes_catalog[l_id], p_lunch, ingredients_catalog)
        d_slot = _build_meal_slot(recipes_catalog[d_id], p_dinner, ingredients_catalog)

        tot_p = round(b_slot.protein_g + l_slot.protein_g + d_slot.protein_g, 1)
        tot_f = round(b_slot.fat_g + l_slot.fat_g + d_slot.fat_g, 1)
        tot_c = round(b_slot.carbs_g + l_slot.carbs_g + d_slot.carbs_g, 1)
        tot_kcal = round(b_slot.calories + l_slot.calories + d_slot.calories, 1)

        days.append(DayPlan(
            day_name=day_name,
            date_str=date_str,
            breakfast=b_slot,
            lunch=l_slot,
            dinner=d_slot,
            total_protein_g=tot_p,
            total_fat_g=tot_f,
            total_carbs_g=tot_c,
            total_calories=tot_kcal
        ))

    return WeeklyPlan(days=days, rollover_items=[])

def export_meal_plan_csv(plan: WeeklyPlan, filepath: str) -> None:
    """Exports the weekly meal plan to CSV with raw weights."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    fieldnames = [
        "Day", "Date", "Meal", "Recipe", "Texture", "Prep_Type",
        "Ingredients", "Protein_g", "Fat_g", "Carbs_g", "Calories"
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for day in plan.days:
            for slot in [day.breakfast, day.lunch, day.dinner]:
                ingredients_str = "; ".join(item.get("label", f"{item['raw_weight_g']}g {item['name']}") for item in slot.ingredients)
                writer.writerow({
                    "Day": day.day_name,
                    "Date": day.date_str,
                    "Meal": slot.meal_type.capitalize(),
                    "Recipe": slot.recipe_name,
                    "Texture": slot.texture,
                    "Prep_Type": slot.prep_type,
                    "Ingredients": ingredients_str,
                    "Protein_g": slot.protein_g,
                    "Fat_g": slot.fat_g,
                    "Carbs_g": slot.carbs_g,
                    "Calories": slot.calories
                })
