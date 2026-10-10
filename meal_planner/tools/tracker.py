import csv
from datetime import datetime
import os
from typing import Optional
from meal_planner.models import load_catalog

def init_bookkeeping_artifacts(data_dir: str) -> None:
    """Initializes prices.csv and meal_logs.csv with header rows and baseline seed data."""
    os.makedirs(data_dir, exist_ok=True)
    prices_path = os.path.join(data_dir, "prices.csv")
    logs_path = os.path.join(data_dir, "meal_logs.csv")

    ingredients, _ = load_catalog()
    today_str = datetime.now().strftime("%Y-%m-%d")

    if not os.path.exists(prices_path):
        with open(prices_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Item_ID", "Item_Name", "Store", "Unit_Price_EUR", "Unit_Type"])
            for ing in ingredients.values():
                writer.writerow([
                    today_str,
                    ing.id,
                    ing.name,
                    "Colruyt",
                    f"{ing.unit_price_eur:.2f}",
                    ing.unit_type
                ])

    if not os.path.exists(logs_path):
        with open(logs_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Meal", "Recipe", "Adherence", "Protein_Cost_EUR", "Calories", "Veg_g", "Fruit_g", "Notes"])

def record_price(
    data_dir: str,
    item_id: str,
    store: str,
    price_eur: float,
    unit_type: str = "per_kg"
) -> None:
    """Appends an observed unit price to prices.csv."""
    init_bookkeeping_artifacts(data_dir)
    prices_path = os.path.join(data_dir, "prices.csv")
    ingredients, _ = load_catalog()
    item_name = ingredients[item_id].name if item_id in ingredients else item_id
    today_str = datetime.now().strftime("%Y-%m-%d")

    with open(prices_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            today_str,
            item_id,
            item_name,
            store,
            f"{price_eur:.2f}",
            unit_type
        ])

def log_meal_consumption(data_dir: str, entry: dict) -> None:
    """Appends a consumed meal log entry to meal_logs.csv with vegetable and fruit tracking."""
    init_bookkeeping_artifacts(data_dir)
    logs_path = os.path.join(data_dir, "meal_logs.csv")
    with open(logs_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            entry.get("date", datetime.now().strftime("%Y-%m-%d")),
            entry.get("meal", "dinner"),
            entry.get("recipe", "custom"),
            entry.get("adherence", "completed"),
            f"{float(entry.get('protein_cost_eur', 0.0)):.2f}",
            f"{int(round(float(entry.get('calories', 0.0) or 0)))}",
            f"{int(round(float(entry.get('veg_g', 0) or 0)))}",
            f"{int(round(float(entry.get('fruit_g', 0) or 0)))}",
            entry.get("notes", "")
        ])

def get_analytics_summary(data_dir: str) -> dict:
    """Aggregates nutritional adherence, vegetable/fruit intake, and grocery protein spending trends."""
    logs_path = os.path.join(data_dir, "meal_logs.csv")
    prices_path = os.path.join(data_dir, "prices.csv")

    if not os.path.exists(logs_path):
        return {
            "total_protein_spend_eur": 0.0,
            "logged_meals_count": 0,
            "adherence_rate_pct": 100.0,
            "average_calories_per_logged_meal": 0.0,
            "total_veg_g": 0,
            "total_fruit_g": 0,
            "average_veg_g_per_logged_meal": 0.0,
            "average_fruit_g_per_logged_meal": 0.0
        }

    total_spend = 0.0
    total_kcal = 0.0
    total_veg = 0.0
    total_fruit = 0.0
    completed_count = 0
    total_count = 0

    with open(logs_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_count += 1
            cost = float(row.get("Protein_Cost_EUR", 0.0) or 0.0)
            kcal = float(row.get("Calories", 0.0) or 0.0)
            veg = float(row.get("Veg_g", 0.0) or 0.0)
            fruit = float(row.get("Fruit_g", 0.0) or 0.0)
            adherence = row.get("Adherence", "completed")

            total_spend += cost
            total_kcal += kcal
            total_veg += veg
            total_fruit += fruit
            if adherence == "completed":
                completed_count += 1

    adherence_pct = (completed_count / total_count * 100.0) if total_count > 0 else 100.0
    avg_kcal = (total_kcal / total_count) if total_count > 0 else 0.0
    avg_veg = (total_veg / total_count) if total_count > 0 else 0.0
    avg_fruit = (total_fruit / total_count) if total_count > 0 else 0.0

    return {
        "total_protein_spend_eur": round(total_spend, 2),
        "logged_meals_count": total_count,
        "adherence_rate_pct": round(adherence_pct, 1),
        "average_calories_per_logged_meal": round(avg_kcal, 1),
        "total_veg_g": int(round(total_veg)),
        "total_fruit_g": int(round(total_fruit)),
        "average_veg_g_per_logged_meal": round(avg_veg, 1),
        "average_fruit_g_per_logged_meal": round(avg_fruit, 1)
    }
