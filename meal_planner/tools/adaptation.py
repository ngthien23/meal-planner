import copy
from typing import Optional
from meal_planner.models import (
    load_catalog,
    WeeklyPlan,
    MealSlot,
    DayPlan,
    UserProfile
)
from meal_planner.tools.macro_calculator import solve_protein_raw_weight

def apply_meal_deviation(plan: WeeklyPlan, deviation: dict) -> WeeklyPlan:
    """Adapts the weekly plan when a meal deviation occurs (e.g., skipped dinner, double shake).
    
    Deviation dict:
        day: Day name (e.g. "Thursday")
        meal: "breakfast" | "lunch" | "dinner"
        actual_recipe_name: Description of what was actually consumed
        protein_consumed_g: float
        calories_consumed: float
    """
    updated_plan = copy.deepcopy(plan)
    day_name = deviation.get("day", "").capitalize()
    meal_type = deviation.get("meal", "").lower()
    actual_name = deviation.get("actual_recipe_name", "Alternative Meal")
    consumed_p = float(deviation.get("protein_consumed_g", 0.0))
    consumed_kcal = float(deviation.get("calories_consumed", 0.0))

    target_day_idx = None
    for idx, day in enumerate(updated_plan.days):
        if day.day_name.lower() == day_name.lower():
            target_day_idx = idx
            break

    if target_day_idx is None:
        return updated_plan

    day = updated_plan.days[target_day_idx]
    current_slot = getattr(day, meal_type)
    old_p = current_slot.protein_g
    old_kcal = current_slot.calories
    delta_p = old_p - consumed_p

    # Capture unused perishable ingredients for rollover
    ingredients_catalog, _ = load_catalog()
    for item in current_slot.ingredients:
        ing_id = item["id"]
        ing = ingredients_catalog.get(ing_id)
        if ing and ing.perishable and ing.category in ["meat", "seafood"]:
            # Food safety shelf-life check:
            # If target day is Thursday or Friday, fresh meat must either roll to Friday or be frozen
            action = "rollover_to_friday" if (day_name == "Thursday" and meal_type == "dinner") else "freeze"
            updated_plan.rollover_items.append({
                "source_day": day_name,
                "ingredient_id": ing_id,
                "name": ing.name,
                "raw_weight_g": item["raw_weight_g"],
                "action": action,
                "note": f"Unused due to deviation ({actual_name}). Prevent spoilage."
            })

    # Update the deviated meal slot
    adapted_slot = MealSlot(
        recipe_id="adapted_deviation",
        recipe_name=actual_name,
        meal_type=meal_type,
        texture=current_slot.texture,
        ingredients=[{
            "id": "consumed_alt",
            "name": actual_name,
            "raw_weight_g": 0.0,
            "label": f"Actual: {actual_name}"
        }],
        protein_g=consumed_p,
        fat_g=round(consumed_kcal * 0.15 / 9.0, 1),
        carbs_g=round((consumed_kcal - (consumed_p * 4.0)) / 4.0, 1) if consumed_kcal > (consumed_p * 4.0) else 0.0,
        calories=consumed_kcal
    )
    setattr(day, meal_type, adapted_slot)
    day.total_protein_g = round(day.breakfast.protein_g + day.lunch.protein_g + day.dinner.protein_g, 1)
    day.total_calories = round(day.breakfast.calories + day.lunch.calories + day.dinner.calories, 1)

    # Balance remaining protein delta across subsequent days if delta is significant
    remaining_days = updated_plan.days[target_day_idx + 1:]
    if remaining_days and abs(delta_p) > 5.0:
        p_adj_per_day = round(delta_p / len(remaining_days), 1)
        for rem_day in remaining_days:
            # Distribute into breakfast smoothie (avoids chewing fatigue)
            rem_b = rem_day.breakfast
            rem_b.protein_g = round(rem_b.protein_g + p_adj_per_day, 1)
            rem_b.calories = round(rem_b.calories + (p_adj_per_day * 4.0), 1)
            rem_day.total_protein_g = round(rem_day.breakfast.protein_g + rem_day.lunch.protein_g + rem_day.dinner.protein_g, 1)
            rem_day.total_calories = round(rem_day.breakfast.calories + rem_day.lunch.calories + rem_day.dinner.calories, 1)

    return updated_plan

def apply_grocery_substitution(
    plan: WeeklyPlan,
    original_id: str,
    sub_id: str,
    new_price_eur: float
) -> WeeklyPlan:
    """Substitutes an ingredient across the weekly plan and recalculates raw weights and macros."""
    ingredients_catalog, _ = load_catalog()
    sub_ing = ingredients_catalog.get(sub_id)
    if not sub_ing:
        return plan

    updated_plan = copy.deepcopy(plan)
    for day in updated_plan.days:
        day_changed = False
        for slot in [day.breakfast, day.lunch, day.dinner]:
            has_orig = any(item["id"] == original_id for item in slot.ingredients)
            if not has_orig:
                continue

            day_changed = True
            # Compute baseline protein from other ingredients
            baseline_p = sum(
                (item["raw_weight_g"] / 100.0) * ingredients_catalog[item["id"]].protein_per_100g
                for item in slot.ingredients
                if item["id"] != original_id and item["id"] in ingredients_catalog
            )
            recalculated_weight = solve_protein_raw_weight(slot.protein_g, baseline_p, sub_ing.protein_per_100g)

            new_ingredients = []
            for item in slot.ingredients:
                if item["id"] == original_id:
                    new_ingredients.append({
                        "id": sub_id,
                        "name": sub_ing.name,
                        "raw_weight_g": recalculated_weight,
                        "label": f"{recalculated_weight:.1f}g raw/dry {sub_ing.name}"
                    })
                else:
                    new_ingredients.append(item)

            slot.ingredients = new_ingredients

            # Update recipe name
            if "pork" in original_id and "chicken" in sub_id:
                slot.recipe_name = slot.recipe_name.replace("Pork", "Chicken").replace("Thịt Kho", "Gà Kho")
            elif "chicken" in original_id and "pork" in sub_id:
                slot.recipe_name = slot.recipe_name.replace("Chicken", "Pork")

            # Recompute slot macros from all ingredients
            tot_p = 0.0
            tot_f = 0.0
            tot_c = 0.0
            tot_kcal = 0.0
            for item in slot.ingredients:
                ing = ingredients_catalog.get(item["id"])
                if ing:
                    w = item["raw_weight_g"]
                    tot_p += (w / 100.0) * ing.protein_per_100g
                    tot_f += (w / 100.0) * ing.fat_per_100g
                    tot_c += (w / 100.0) * ing.carbs_per_100g
                    tot_kcal += (w / 100.0) * ing.calories_per_100g

            slot.protein_g = round(tot_p, 1)
            slot.fat_g = round(tot_f, 1)
            slot.carbs_g = round(tot_c, 1)
            slot.calories = round(tot_kcal, 1)

        if day_changed:
            day.total_protein_g = round(day.breakfast.protein_g + day.lunch.protein_g + day.dinner.protein_g, 1)
            day.total_fat_g = round(day.breakfast.fat_g + day.lunch.fat_g + day.dinner.fat_g, 1)
            day.total_carbs_g = round(day.breakfast.carbs_g + day.lunch.carbs_g + day.dinner.carbs_g, 1)
            day.total_calories = round(day.breakfast.calories + day.lunch.calories + day.dinner.calories, 1)

    return updated_plan
