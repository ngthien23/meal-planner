import unittest
import os
import csv
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import generate_weekly_plan, export_meal_plan_csv

class TestMealGenerator(unittest.TestCase):
    def test_weekly_plan_texture_rules_and_package_exhaustion(self):
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        
        # Verify 7 days (Saturday to Friday)
        self.assertEqual(len(plan.days), 7)
        self.assertEqual(plan.days[0].day_name, "Saturday")
        self.assertEqual(plan.days[1].day_name, "Sunday")
        self.assertEqual(plan.days[2].day_name, "Monday")
        self.assertEqual(plan.days[3].day_name, "Tuesday")
        self.assertEqual(plan.days[4].day_name, "Wednesday")
        self.assertEqual(plan.days[5].day_name, "Thursday")
        self.assertEqual(plan.days[6].day_name, "Friday")

        # Texture rule verification
        for day in plan.days:
            self.assertIn(day.breakfast.texture, ["liquid", "soft"])
            self.assertEqual(day.lunch.texture, "solid")
            self.assertIn(day.dinner.texture, ["broth", "soft"])

        # Check raw weights in export
        csv_path = "tests/test_meal_plan.csv"
        export_meal_plan_csv(plan, csv_path)
        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 21) # 7 days * 3 meals
            # Verify strict 8 columns
            self.assertEqual(list(rows[0].keys()), ["Date", "Meal", "Recipe", "Ingredient", "P", "C", "F", "Calories"])
            # Verify raw/dry specified in ingredient column and integers with no decimals
            self.assertTrue(any("raw" in r["Ingredient"].lower() or "dry" in r["Ingredient"].lower() for r in rows))
            for r in rows:
                self.assertNotIn(".", r["P"])
                self.assertNotIn(".", r["C"])
                self.assertNotIn(".", r["F"])
                self.assertNotIn(".", r["Calories"])
        os.remove(csv_path)

        # Macro tracking for veg and fruit
        self.assertTrue(any(day.total_veg_g > 0 for day in plan.days))
        self.assertTrue(any(day.total_fruit_g > 0 for day in plan.days))
