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

CURRENCY_SYMBOLS: dict[str, str] = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "VND": "₫",
    "CAD": "CA$",
    "AUD": "A$",
    "JPY": "¥",
    "CHF": "CHF",
}

def get_currency_symbol(currency_code: str) -> str:
    """Returns the visual currency symbol for a currency code (e.g. EUR -> €)."""
    return CURRENCY_SYMBOLS.get((currency_code or "").upper().strip(), currency_code)

@dataclass
class UserProfile:
    timezone: str = "UTC"
    bodyweight_kg: float = 65.0
    goal_state: str = "lean_bulk"  # lean_bulk, cut, maintenance
    target_calories: float = 2550.0
    protein_multiplier: float = 2.2
    fat_multiplier: float = 1.0
    weekly_protein_budget: float = 0.0
    restrictions: list[str] = field(default_factory=list)
    week_start_day: str = "Saturday"
    weeks_ahead: int = 1
    currency: str = "EUR"
    is_onboarded: bool = True
    texture_rules: dict = field(default_factory=dict)
    batch_prep_days: list[str] = field(default_factory=list)

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

@dataclass
class InventoryItem:
    food_id: str
    name: str
    quantity_g: float
    status: str = "actual"  # "actual" | "assumed"
    source: str = "user_report"
    purchased_date: str = ""

@dataclass
class InventoryState:
    last_reconciled_at: Optional[str] = None
    carried_calories: float = 0.0
    carried_protein_g: float = 0.0
    items: list[InventoryItem] = field(default_factory=list)
    assumed_runs: list[str] = field(default_factory=list)

def load_catalog(
    catalog_dir: Optional[str] = None,
    data_dir: Optional[str] = None
) -> tuple[dict[str, Ingredient], dict[str, Recipe]]:
    if catalog_dir is None:
        catalog_dir = os.path.join(os.path.dirname(__file__), "catalog")

    ing_path = os.path.join(catalog_dir, "ingredients.json")
    rec_path = os.path.join(catalog_dir, "recipes.json")

    with open(ing_path, "r", encoding="utf-8") as f:
        ing_data = json.load(f)
    with open(rec_path, "r", encoding="utf-8") as f:
        rec_data = json.load(f)

    # Check for custom ingredients in data_dir (or default 'data' if exists)
    custom_paths = []
    if data_dir:
        custom_paths.append(os.path.join(data_dir, "custom_ingredients.json"))
    if os.path.exists(os.path.join("data", "custom_ingredients.json")) and data_dir != "data":
        custom_paths.append(os.path.join("data", "custom_ingredients.json"))

    for cp in custom_paths:
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    custom_data = json.load(f)
                    ing_data.update(custom_data)
            except Exception:
                pass

    ingredients = {
        item_id: Ingredient(**data)
        for item_id, data in ing_data.items()
    }
    recipes = {
        rec_id: Recipe(**data)
        for rec_id, data in rec_data.items()
    }
    return ingredients, recipes

def add_ingredient_to_catalog(
    ingredient: Ingredient,
    catalog_dir: Optional[str] = None,
    data_dir: Optional[str] = None
) -> None:
    """Persists a new or updated ingredient to data_dir custom_ingredients.json (if provided) and/or catalog_dir."""
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
        custom_path = os.path.join(data_dir, "custom_ingredients.json")
        custom_data = {}
        if os.path.exists(custom_path):
            with open(custom_path, "r", encoding="utf-8") as f:
                try:
                    custom_data = json.load(f)
                except Exception:
                    custom_data = {}
        custom_data[ingredient.id] = ingredient.__dict__
        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(custom_data, f, indent=2)

    if catalog_dir:
        ing_path = os.path.join(catalog_dir, "ingredients.json")
        if os.path.exists(ing_path):
            with open(ing_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data[ingredient.id] = ingredient.__dict__
            with open(ing_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
