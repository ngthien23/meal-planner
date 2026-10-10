from dataclasses import dataclass, field
import csv
import json
import math
import os
from typing import Optional
from meal_planner.models import load_catalog, WeeklyPlan, Ingredient

@dataclass
class PantryState:
    items: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: str) -> "PantryState":
        path = os.path.join(data_dir, "pantry.json")
        if not os.path.exists(path):
            return cls(items={
                "jasmine_rice": 5000.0,
                "on_whey": 2270.0,
                "cooking_oil": 920.0,
                "fortified_soy_milk": 1000.0,
                "dry_pho_noodles": 400.0
            })
        with open(path, "r", encoding="utf-8") as f:
            return cls(items=json.load(f))

    def save(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "pantry.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=2)

@dataclass
class SplitGroceryList:
    saturday_run: list[dict]
    wednesday_run: list[dict]
    pantry_restock: list[dict]

def generate_split_groceries(
    plan: WeeklyPlan,
    pantry: Optional[PantryState] = None
) -> SplitGroceryList:
    """Generates split Saturday and Wednesday grocery runs and pantry restock items."""
    ingredients_catalog, _ = load_catalog()
    if pantry is None:
        pantry = PantryState()

    # Track item usage partitioned by run
    sat_usage: dict[str, float] = {}
    wed_usage: dict[str, float] = {}
    total_weekly_usage: dict[str, float] = {}

    for i, day in enumerate(plan.days):
        # Day index 0..3 (Sat, Sun, Mon, Tue) fresh meats assigned to Saturday Run
        # Sunday batch lunch (for Mon-Wed) assigned to Saturday Run
        # Wednesday batch lunch (for Thu-Fri) assigned to Wednesday Run
        for slot in [day.breakfast, day.lunch, day.dinner]:
            for item in slot.ingredients:
                ing_id = item["id"]
                weight = item["raw_weight_g"]
                total_weekly_usage[ing_id] = total_weekly_usage.get(ing_id, 0.0) + weight

                ing = ingredients_catalog.get(ing_id)
                is_pantry = ing and ing.category in ["pantry", "supplement", "grains"] and not ing.perishable

                if is_pantry:
                    continue  # pantry handled via restock check

                # Frozen seafood/meat (e.g. frozen shrimp) is non-perishable in freezer (doesn't spoil in 72h).
                # Allocate full weekly amount to Saturday Run to prevent splitting a single package into two rounded purchases.
                if ing and ing.category == "seafood" and "frozen" in ing.id:
                    sat_usage[ing_id] = sat_usage.get(ing_id, 0.0) + weight
                    continue

                # Perishable assignment based on 48-72h food safety constraint:
                # Sat (0) and Sun (1) meals -> Saturday Run
                # Mon-Wed lunches prepped Sunday evening (i=2,3,4 lunch) -> Saturday Run
                # Mon-Tue fresh dinner meats -> Saturday Run
                # Wed dinner & Thu-Fri fresh dinner meats & Wed batch lunch (Thu-Fri) -> Wednesday Run
                if i < 4 or (i == 4 and slot.meal_type == "lunch"):
                    sat_usage[ing_id] = sat_usage.get(ing_id, 0.0) + weight
                else:
                    wed_usage[ing_id] = wed_usage.get(ing_id, 0.0) + weight

    def _build_run_items(usage_dict: dict[str, float], run_label: str) -> list[dict]:
        items = []
        for ing_id, needed_g in usage_dict.items():
            ing = ingredients_catalog.get(ing_id)
            if not ing:
                continue
            pkg_size = ing.package_size_g if ing.package_size_g > 0 else 500.0
            num_pkgs = math.ceil(needed_g / pkg_size)
            est_cost = round(num_pkgs * ing.unit_price_eur, 2)
            storage_note = "Fridge (<= 72h)" if ing.perishable and ing.category == "meat" else "Pantry / Freezer"
            items.append({
                "run": run_label,
                "id": ing_id,
                "name": ing.name,
                "category": ing.category,
                "needed_g": int(round(needed_g)),
                "packages": num_pkgs,
                "package_size": f"{int(round(pkg_size))}g",
                "estimated_price_eur": est_cost,
                "storage_note": storage_note
            })
        return items

    saturday_items = _build_run_items(sat_usage, "Saturday")
    wednesday_items = _build_run_items(wed_usage, "Wednesday")

    # Pantry restock check across ALL non-perishable catalog pantry items
    restock_items = []
    for ing_id, ing in ingredients_catalog.items():
        if ing.perishable or ing.category not in ["pantry", "supplement", "grains", "dairy_alternative"]:
            continue
        planned_g = total_weekly_usage.get(ing_id, 0.0)
        current_stock = pantry.items.get(ing_id, 0.0)
        remaining_stock = current_stock - planned_g
        threshold = ing.reorder_threshold_g

        if remaining_stock <= threshold:
            pkg_size = ing.package_size_g if ing.package_size_g > 0 else 1000.0
            restock_items.append({
                "run": "Pantry",
                "id": ing_id,
                "name": ing.name,
                "category": ing.category,
                "current_stock_g": int(round(current_stock)),
                "needed_g": int(round(planned_g)),
                "packages": 1,
                "package_size": f"{int(round(pkg_size))}g",
                "estimated_price_eur": ing.unit_price_eur,
                "storage_note": "Pantry Restock"
            })

    return SplitGroceryList(
        saturday_run=saturday_items,
        wednesday_run=wednesday_items,
        pantry_restock=restock_items
    )

def export_grocery_list_csv(grocery_list: SplitGroceryList, filepath: str) -> None:
    """Exports split grocery list to CSV."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    fieldnames = [
        "Run", "Category", "Item", "Quantity", "Package_Size", "Estimated_Price_EUR", "Storage_Note"
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for run_items in [grocery_list.saturday_run, grocery_list.wednesday_run, grocery_list.pantry_restock]:
            for item in run_items:
                needed_g_val = int(round(item.get("needed_g", 0)))
                writer.writerow({
                    "Run": item["run"],
                    "Category": item["category"].capitalize(),
                    "Item": item["name"],
                    "Quantity": f"{item['packages']}x ({needed_g_val}g planned)",
                    "Package_Size": item["package_size"],
                    "Estimated_Price_EUR": f"€{item['estimated_price_eur']:.2f}",
                    "Storage_Note": item["storage_note"]
                })
