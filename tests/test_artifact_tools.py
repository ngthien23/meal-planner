import unittest
import os
import shutil
import tempfile
from meal_planner.tools.artifacts import (
    get_meal_plan_csv,
    update_meal_plan_csv,
    get_grocery_list_csv,
    update_grocery_list_csv,
    get_batch_cook_csv,
    update_batch_cook_csv
)

class TestArtifactTools(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        update_meal_plan_csv(self.test_dir, [
            {"Date": "2026-10-10", "Meal": "Breakfast", "Recipe": "Oatmeal", "Ingredient": "100g Oats", "P": 15, "C": 60, "F": 10, "Calories": 390},
            {"Date": "2026-10-10", "Meal": "Lunch", "Recipe": "Chicken Rice", "Ingredient": "200g Chicken; 150g Rice", "P": 50, "C": 45, "F": 15, "Calories": 515},
            {"Date": "2026-10-10", "Meal": "Dinner", "Recipe": "Beef Stew", "Ingredient": "200g Beef", "P": 45, "C": 20, "F": 20, "Calories": 440},
        ])
        update_grocery_list_csv(self.test_dir, [
            {"Run": "Saturday Run", "Category": "meat", "Item": "Chicken Breast", "Quantity_g": 1000, "Estimated_Price_EUR": 9.50},
            {"Run": "Saturday Run", "Category": "produce", "Item": "Broccoli", "Quantity_g": 500, "Estimated_Price_EUR": 2.00},
        ])

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_get_and_update_meal_plan_csv(self):
        # 1. Read initial plan
        initial_rows = get_meal_plan_csv(self.test_dir)
        self.assertGreater(len(initial_rows), 0)

        # 2. Update Saturday Lunch with Air Fried Chicken craving
        update_data = [{
            "Date": "2026-10-10",
            "Meal": "Lunch",
            "Recipe": "Air Fried Crispy Chicken",
            "Ingredient": "250g Chicken Wings; 250g Chicken Thighs; 150g Jasmine Rice",
            "P": 55,
            "C": 45,
            "F": 18,
            "Calories": 560
        }]
        res = update_meal_plan_csv(self.test_dir, update_data)
        self.assertTrue(res["success"])

        # 3. Verify update took effect in CSV
        updated_rows = get_meal_plan_csv(self.test_dir, target_date="2026-10-10")
        lunch_row = next((r for r in updated_rows if r["Meal"].lower() == "lunch"), None)
        self.assertIsNotNone(lunch_row)
        self.assertEqual(lunch_row["Recipe"], "Air Fried Crispy Chicken")
        self.assertIn("Chicken Wings", lunch_row["Ingredient"])
        self.assertEqual(int(lunch_row["Calories"]), 560)

    def test_append_extra_snack_to_meal_plan(self):
        # Allow adding a snack without wiping 3 core meals
        snack_entry = [{
            "Date": "2026-10-10",
            "Meal": "Snack",
            "Recipe": "Evening Whey Shake",
            "Ingredient": "30g ON Whey; 250ml Soy Milk",
            "P": 30,
            "C": 5,
            "F": 3,
            "Calories": 165
        }]
        res = update_meal_plan_csv(self.test_dir, snack_entry)
        self.assertTrue(res["success"])

        day_rows = get_meal_plan_csv(self.test_dir, target_date="2026-10-10")
        # Now day has breakfast, lunch, dinner + snack
        meals = [r["Meal"].lower() for r in day_rows]
        self.assertIn("snack", meals)
        self.assertIn("lunch", meals)

    def test_get_and_update_grocery_list_csv(self):
        # 1. Read initial grocery list
        groceries = get_grocery_list_csv(self.test_dir)
        self.assertGreater(len(groceries), 0)
        chicken_item = next(g for g in groceries if "Chicken Breast" in g["Item"])
        self.assertGreater(int(chicken_item["Quantity_g"]), 100)

        # 2. Shift next run to dynamic date (e.g. 2026-10-13) and prune redundant meat
        new_runs = [
            {"Run": "2026-10-13 Dynamic Run", "Category": "meat", "Item": "Chicken Breast", "Quantity_g": 1000, "Estimated_Price_EUR": 9.50},
            {"Run": "2026-10-13 Dynamic Run", "Category": "vegetable", "Item": "Broccoli", "Quantity_g": 500, "Estimated_Price_EUR": 2.00}
        ]
        res = update_grocery_list_csv(self.test_dir, new_runs, mode="replace")
        self.assertTrue(res["success"])

        # 3. Verify groceries replaced with shifted run
        updated_groceries = get_grocery_list_csv(self.test_dir)
        self.assertEqual(len(updated_groceries), 2)
        self.assertEqual(updated_groceries[0]["Run"], "2026-10-13 Dynamic Run")

    def test_merge_into_baseline_grocery_list_does_not_crash(self):
        # Baseline grocery_list.csv has columns: Run, Category, Item, Quantity, Package_Size, Estimated_Price_EUR, Storage_Note
        # Merging with Quantity_g must succeed and normalize fieldnames
        update_items = [
            {"Run": "Saturday Run", "Category": "meat", "Item": "Chicken Breast", "Quantity_g": 1200, "Estimated_Price_EUR": 11.40}
        ]
        res = update_grocery_list_csv(self.test_dir, update_items, mode="merge")
        self.assertTrue(res["success"])

        # Check updated grocery rows
        groceries = get_grocery_list_csv(self.test_dir)
        cb = next((g for g in groceries if "Chicken Breast" in g.get("Item", "") and g.get("Run") == "Saturday Run"), None)
        self.assertIsNotNone(cb)
        self.assertEqual(cb.get("Quantity_g"), "1200")

    def test_get_and_update_batch_cook_csv(self):
        # 1. Update batch cook with simplified schema
        batch_entries = [
            {"Dish": "Thịt Kho Tàu", "Main_Protein": "1000g Pork Belly", "Meals": 3},
            {"Dish": "Gà Xào Sả Ớt", "Main_Protein": "800g Chicken Breast", "Meals": 2}
        ]
        res = update_batch_cook_csv(self.test_dir, batch_entries)
        self.assertTrue(res["success"])

        # 2. Read back
        rows = get_batch_cook_csv(self.test_dir)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Dish"], "Thịt Kho Tàu")
        self.assertEqual(rows[0]["Main_Protein"], "1000g Pork Belly")
        self.assertEqual(rows[0]["Meals"], "3")
        self.assertNotIn("Grocery_Run", rows[0])
        self.assertNotIn("Prep_Day", rows[0])
        self.assertNotIn("Days_Served", rows[0])

    def test_update_grocery_list_post_processes_by_sorting_run_and_category(self):
        disordered_items = [
            {"Run": "Wednesday", "Category": "vegetable", "Item": "Broccoli", "Quantity_g": 300},
            {"Run": "Saturday", "Category": "vegetable", "Item": "Bok Choy", "Quantity_g": 500},
            {"Run": "Saturday", "Category": "meat", "Item": "Chicken Breast", "Quantity_g": 1000},
            {"Run": "Wednesday", "Category": "meat", "Item": "Lean Beef", "Quantity_g": 400},
            {"Run": "Saturday", "Category": "meat", "Item": "Beef Flank", "Quantity_g": 500},
            {"Run": "Pantry", "Category": "supplement", "Item": "ON Whey", "Quantity_g": 900},
        ]
        res = update_grocery_list_csv(self.test_dir, disordered_items, mode="replace")
        self.assertTrue(res["success"])

        rows = get_grocery_list_csv(self.test_dir)
        runs = [r["Run"] for r in rows]
        sat_indices = [i for i, run in enumerate(runs) if run == "Saturday"]
        wed_indices = [i for i, run in enumerate(runs) if run == "Wednesday"]
        pantry_indices = [i for i, run in enumerate(runs) if run == "Pantry"]

        # Saturday before Wednesday before Pantry
        self.assertTrue(max(sat_indices) < min(wed_indices))
        self.assertTrue(max(wed_indices) < min(pantry_indices))

        # Check Category grouping within Saturday
        sat_rows = [r for r in rows if r["Run"] == "Saturday"]
        sat_categories = [r["Category"] for r in sat_rows]
        seen_cats = []
        for c in sat_categories:
            if not seen_cats or seen_cats[-1] != c:
                seen_cats.append(c)
        self.assertEqual(len(seen_cats), len(set(seen_cats)))
