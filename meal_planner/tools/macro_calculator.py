from dataclasses import dataclass

@dataclass
class MacroTargets:
    calories: float
    protein_g: float
    fat_g: float
    carbs_g: float

def calculate_daily_targets(
    bodyweight_kg: float,
    protein_mult: float,
    fat_mult: float,
    target_calories: float
) -> MacroTargets:
    """Calculates flat daily macronutrient targets.
    
    Raises:
        ValueError: if target_calories cannot sustain protein, fat, and a minimum carb floor.
    """
    protein_g = round(bodyweight_kg * protein_mult, 1)
    fat_g = round(bodyweight_kg * fat_mult, 1)
    
    protein_kcal = protein_g * 4.0
    fat_kcal = fat_g * 9.0
    
    # Minimum 50g carbs floor for brain/metabolic health in powerlifting
    min_carbs_g = 50.0
    min_carbs_kcal = min_carbs_g * 4.0
    
    if target_calories < (protein_kcal + fat_kcal + min_carbs_kcal):
        raise ValueError(
            f"Target calories ({target_calories:.0f} kcal) is too low to sustain "
            f"{protein_g}g protein ({protein_kcal:.0f} kcal) and {fat_g}g fat ({fat_kcal:.0f} kcal). "
            f"Minimum feasible calories: {protein_kcal + fat_kcal + min_carbs_kcal:.0f} kcal."
        )
    
    remaining_kcal = target_calories - protein_kcal - fat_kcal
    carbs_g = round(remaining_kcal / 4.0, 2)
    
    return MacroTargets(
        calories=target_calories,
        protein_g=protein_g,
        fat_g=fat_g,
        carbs_g=carbs_g
    )

def solve_protein_raw_weight(
    required_protein_g: float,
    baseline_dish_protein_g: float,
    meat_protein_density: float
) -> float:
    """Solves the required raw/dry weight (in grams) of meat to meet a meal's protein target.
    
    Args:
        required_protein_g: Total protein target for this meal.
        baseline_dish_protein_g: Protein already provided by base carbs/broth/sauce.
        meat_protein_density: Grams of protein per 100g of raw ingredient.
        
    Returns:
        float: Exact raw weight in grams.
    """
    needed_protein = max(0.0, required_protein_g - baseline_dish_protein_g)
    if meat_protein_density <= 0:
        return 0.0
    raw_weight_g = (needed_protein / meat_protein_density) * 100.0
    return round(raw_weight_g, 1)
