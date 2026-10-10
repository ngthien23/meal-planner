import unittest
import os
import csv
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import generate_weekly_plan
from meal_planner.tools.grocery_planner import (
    PantryState,
    generate_split_groceries,
    export_grocery_list_csv,
    SplitGroceryList
)

class TestGroceryPlanner(unittest.TestCase):
    def test_split_grocery_runs_and_pantry_restock(self):
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        
        # Review Focus 5: Pantry threshold test
        # Pantry with plenty of rice (4000g), but low whey (150g, threshold 300g)
        pantry = PantryState(items={"jasmine_rice": 4000.0, "on_whey": 150.0, "cooking_oil": 800.0})
        
        groceries = generate_split_groceries(plan, pantry)
        self.assertIsInstance(groceries, SplitGroceryList)
        
        # Saturday run must contain fresh meat for Sat-Tue only
        sat_names = [item["name"] for item in groceries.saturday_run]
        wed_names = [item["name"] for item in groceries.wednesday_run]
        restock_names = [item["name"] for item in groceries.pantry_restock]

        # Whey must be in restock, Jasmine Rice must NOT be restocked
        self.assertTrue(any("Whey" in name for name in restock_names))
        self.assertFalse(any("Jasmine Rice" in name for name in restock_names))

        # Check export
        csv_path = "tests/test_groceries.csv"
        export_grocery_list_csv(groceries, csv_path)
        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertGreater(len(rows), 0)
            self.assertTrue(any(r["Run"] == "Saturday Run" for r in rows))
            self.assertTrue(any(r["Run"] == "Wednesday Run" for r in rows))
        os.remove(csv_path)
