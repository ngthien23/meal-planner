from dataclasses import dataclass, field
import json
import os
from typing import Optional

@dataclass
class Ingredient:
    id: str
    name: str
    category: str
    protein_per_100g: float
    fat_per_100g: float
    carbs_per_100g: float
    calories_per_100g: float
    package_size_g: float
    unit_price_eur: float
    perishable: bool
    unit_type: str = "per_pack"
    reorder_threshold_g: float = 0.0

@dataclass
class Recipe:
    id: str
    name: str
    meal_type: str  # breakfast, lunch, dinner
    texture: str    # liquid, soft, broth, solid
    prep_type: str  # fresh_quick, batch_reheatable
    base_ingredients: list[dict]
    description: str = ""
    protein_ingredient_id: Optional[str] = None

@dataclass
class UserProfile:
    timezone: str = "UTC"
    bodyweight_kg: float = 65.0
    goal_state: str = "lean_bulk"  # lean_bulk, cut, maintenance
    target_calories: float = 2550.0
    protein_multiplier: float = 2.3
    fat_multiplier: float = 1.0
    restrictions: list[str] = field(default_factory=lambda: [
        "no dairy milk (fortified soy only)",
        "ON whey only",
        "canned tuna only (no fresh tuna)"
    ])
    texture_rules: dict = field(default_factory=lambda: {
        "breakfast": "soft_or_liquid",
        "lunch": "solid_batch",
        "dinner": "broth_or_soft"
    })
    batch_prep_days: list[str] = field(default_factory=lambda: ["Sunday", "Wednesday"])
    week_start_day: str = "Saturday"
    weeks_ahead: int = 1

@dataclass
class MealSlot:
    recipe_id: str
    recipe_name: str
    meal_type: str
    texture: str
    ingredients: list[dict]  # list of {"id": str, "name": str, "raw_weight_g": float}
    protein_g: float
    fat_g: float
    carbs_g: float
    calories: float
    prep_type: str = "fresh_quick"
    veg_g: int = 0
    fruit_g: int = 0

@dataclass
class DayPlan:
    day_name: str
    date_str: str
    breakfast: MealSlot
    lunch: MealSlot
    dinner: MealSlot
    total_protein_g: float = 0.0
    total_fat_g: float = 0.0
    total_carbs_g: float = 0.0
    total_calories: float = 0.0
    total_veg_g: int = 0
    total_fruit_g: int = 0

@dataclass
class WeeklyPlan:
    days: list[DayPlan]
    rollover_items: list[dict] = field(default_factory=list)

def load_catalog(catalog_dir: Optional[str] = None) -> tuple[dict[str, Ingredient], dict[str, Recipe]]:
    if catalog_dir is None:
        catalog_dir = os.path.join(os.path.dirname(__file__), "catalog")

    ing_path = os.path.join(catalog_dir, "ingredients.json")
    rec_path = os.path.join(catalog_dir, "recipes.json")

    with open(ing_path, "r", encoding="utf-8") as f:
        ing_data = json.load(f)
    with open(rec_path, "r", encoding="utf-8") as f:
        rec_data = json.load(f)

    ingredients = {
        item_id: Ingredient(**data)
        for item_id, data in ing_data.items()
    }
    recipes = {
        rec_id: Recipe(**data)
        for rec_id, data in rec_data.items()
    }
    return ingredients, recipes
