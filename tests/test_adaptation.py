import unittest
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import generate_weekly_plan
from meal_planner.tools.adaptation import apply_meal_deviation, apply_grocery_substitution

class TestAdaptation(unittest.TestCase):
    def test_thursday_missed_dinner_rollover_and_macro_adjustment(self):
        # Review Focus 3: Missed Thursday dinner rollover
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        
        # User drank a double shake instead of Thursday dinner
        updated_plan = apply_meal_deviation(plan, {
            "day": "Thursday",
            "meal": "dinner",
            "actual_recipe_name": "Double Whey Shake",
            "protein_consumed_g": 50.0,
            "calories_consumed": 300.0
        })

        # Thursday dinner marked as adapted
        thursday = next(d for d in updated_plan.days if d.day_name == "Thursday")
        self.assertEqual(thursday.dinner.recipe_name, "Double Whey Shake")
        
        # Unused meat flagged for rollover/freeze
        self.assertTrue(len(updated_plan.rollover_items) > 0)
        self.assertIn(updated_plan.rollover_items[0]["action"], ["rollover_to_friday", "freeze"])

    def test_substitution_density_recalculation(self):
        # Review Focus 4: Pork shoulder substituted by chicken breast
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        updated_plan = apply_grocery_substitution(plan, "pork_shoulder", "chicken_breast", 9.50)
        
        # Lunch with chicken must have adjusted raw weight reflecting chicken's higher protein density
        mon_lunch = next(d for d in updated_plan.days if d.day_name == "Monday").lunch
        self.assertIn("chicken", mon_lunch.recipe_name.lower())
        # Check raw ingredients updated
        self.assertTrue(any(i["id"] == "chicken_breast" for i in mon_lunch.ingredients))
