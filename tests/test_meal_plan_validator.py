import unittest
import os
import shutil
from meal_planner.tools.artifacts import update_meal_plan_csv, check_meal_plan_csv
from meal_planner.tools.memory import MemoryManager
from meal_planner.agent import get_agent_tools

class TestMealPlanValidator(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_validator_env"
        os.makedirs(self.test_dir, exist_ok=True)
        self.mem_mgr = MemoryManager(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_check_meal_plan_empty(self):
        """Verifies that an empty or missing meal plan returns [NEEDS FIXING]."""
        res = check_meal_plan_csv(self.test_dir)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["status"], "NEEDS_FIXING")
        self.assertIn("[NEEDS FIXING]", res["message"])
        self.assertIn("No meal plan found", res["message"])

    def test_check_meal_plan_accepted_when_matching_goals(self):
        """Verifies that plan is [ACCEPTED] when planned calories and macros match targets within tolerance."""
        # Setup long-term memory with targets
        self.mem_mgr.add_note("Bodyweight: 65.0 kg | Goal: lean_bulk | Target Calories: 2500 kcal", tier="long_term")
        self.mem_mgr.add_note("Target Macros: 150g protein, 280g carbs, 70g fat", tier="long_term")

        # Create 7 days of meals (daily 2500 kcal, 150g P, 280g C, 70g F)
        # Weekly: 17,500 kcal, 1050g P, 1960g C, 490g F
        meals = []
        for i in range(12, 19):
            date_str = f"2026-10-{i}"
            # Breakfast
            meals.append({"Date": date_str, "Meal": "Breakfast", "Recipe": "Eggs & Toast", "Ingredient": "3 eggs", "P": 25, "C": 40, "F": 15, "Calories": 400})
            # Lunch
            meals.append({"Date": date_str, "Meal": "Lunch", "Recipe": "Chicken Rice Bowl", "Ingredient": "250g chicken", "P": 55, "C": 90, "F": 18, "Calories": 800})
            # Dinner
            meals.append({"Date": date_str, "Meal": "Dinner", "Recipe": "Beef Noodles", "Ingredient": "200g beef", "P": 45, "C": 100, "F": 25, "Calories": 850})
            # Snack
            meals.append({"Date": date_str, "Meal": "Snack", "Recipe": "Whey Shake & Oats", "Ingredient": "1 scoop whey", "P": 25, "C": 50, "F": 12, "Calories": 450})

        update_meal_plan_csv(self.test_dir, meals)

        res = check_meal_plan_csv(self.test_dir)
        self.assertTrue(res["accepted"])
        self.assertEqual(res["status"], "ACCEPTED")
        self.assertIn("[ACCEPTED]", res["message"])
        self.assertIn("matches nutritional goals within acceptable approximation", res["message"])
        self.assertIn("Everything checked. The meal plan is approved.", res["message"])

    def test_check_meal_plan_needs_fixing_on_calorie_and_protein_deficit(self):
        """Verifies [NEEDS FIXING] when planned calories/protein fall below the approximation tolerance."""
        self.mem_mgr.add_note("Bodyweight: 70.0 kg | Target Calories: 2600 kcal", tier="long_term")
        self.mem_mgr.add_note("Protein: 160g, Carbs: 300g, Fat: 70g", tier="long_term")

        # Create 7 days with severe deficit (only 1200 kcal/day, 60g P/day)
        meals = []
        for i in range(12, 19):
            date_str = f"2026-10-{i}"
            meals.append({"Date": date_str, "Meal": "Lunch", "Recipe": "Salad", "Ingredient": "Tuna", "P": 60, "C": 50, "F": 15, "Calories": 1200})

        update_meal_plan_csv(self.test_dir, meals)

        res = check_meal_plan_csv(self.test_dir)
        self.assertFalse(res["accepted"])
        self.assertEqual(res["status"], "NEEDS_FIXING")
        self.assertIn("[NEEDS FIXING]", res["message"])
        self.assertIn("Calories too low", res["message"])
        self.assertIn("Protein too low", res["message"])
        self.assertIn("Request: Please adjust the meal plan using tool_update_plans", res["message"])

    def test_check_meal_plan_with_carried_deficit_from_last_week(self):
        """Verifies that carried deficit from last week in weekly memory increases the target calories & protein to be eaten."""
        self.mem_mgr.add_note("Target Calories: 2500 kcal", tier="long_term")
        self.mem_mgr.add_note("Protein: 150g, Carbs: 280g, Fat: 70g", tier="long_term")

        # Note in weekly memory: Carried deficit from last week
        self.mem_mgr.add_note("[2026-10-12] Carried deficit from last week: +1000 kcal, +70g protein to eat", tier="weekly")

        # Base weekly is 17,500 kcal, 1050g P. With carried deficit to eat, target is 18,500 kcal, 1120g P.
        # Plan without the carried deficit (17,500 kcal, 1050g P):
        meals = []
        for i in range(12, 19):
            date_str = f"2026-10-{i}"
            meals.append({"Date": date_str, "Meal": "Lunch", "Recipe": "Meal", "Ingredient": "Food", "P": 150, "C": 280, "F": 70, "Calories": 2500})
        update_meal_plan_csv(self.test_dir, meals)

        res_unadjusted = check_meal_plan_csv(self.test_dir)
        self.assertFalse(res_unadjusted["accepted"])
        self.assertIn("Calories too low", res_unadjusted["message"])

        # Now update plan to include the carried calories & protein (extra 1000 kcal, 70g P spread or added)
        # e.g. total 18,500 kcal, 1120g P
        meals.append({"Date": "2026-10-18", "Meal": "Snack", "Recipe": "Extra Shake & Oats", "Ingredient": "Whey & Oats", "P": 70, "C": 100, "F": 15, "Calories": 1000})
        update_meal_plan_csv(self.test_dir, meals)

        res_adjusted = check_meal_plan_csv(self.test_dir)
        self.assertTrue(res_adjusted["accepted"])
        self.assertIn("[ACCEPTED]", res_adjusted["message"])
        self.assertIn("Carried adjustment from last week: +1000 kcal, +70P", res_adjusted["message"])

    def test_check_meal_plan_with_carried_pcf_notation_without_grams(self):
        """Verifies that carried deficit with P/C/F notation (e.g. +70P, +50C, +20F) in weekly memory parses correctly."""
        self.mem_mgr.add_note("Target Calories: 2500 kcal", tier="long_term")
        self.mem_mgr.add_note("Protein: 150g, Carbs: 280g, Fat: 70g", tier="long_term")

        # Note in weekly memory with direct P/C/F notation (no grams)
        self.mem_mgr.add_note("[2026-10-12] Carried deficit from last week: +1000 kcal, +70P, +50C, +20F to eat", tier="weekly")

        meals = []
        for i in range(12, 19):
            date_str = f"2026-10-{i}"
            meals.append({"Date": date_str, "Meal": "Lunch", "Recipe": "Meal", "Ingredient": "Food", "P": 150, "C": 280, "F": 70, "Calories": 2500})
        # Add carried deficit to meals
        meals.append({"Date": "2026-10-18", "Meal": "Snack", "Recipe": "Extra", "Ingredient": "Whey & Oats", "P": 70, "C": 50, "F": 20, "Calories": 1000})
        update_meal_plan_csv(self.test_dir, meals)

        res = check_meal_plan_csv(self.test_dir)
        self.assertTrue(res["accepted"])
        self.assertIn("[ACCEPTED]", res["message"])
        self.assertIn("+1000 kcal, +70P, +50C, +20F", res["message"])


    def test_check_meal_plan_with_carried_surplus_to_cut_from_last_week(self):
        """Verifies that carried surplus from last week in weekly memory decreases the target calories to be cut."""
        self.mem_mgr.add_note("Target Calories: 2500 kcal", tier="long_term")
        self.mem_mgr.add_note("Protein: 150g, Carbs: 280g, Fat: 70g", tier="long_term")

        # Note in weekly memory: Surplus from last week to cut
        self.mem_mgr.add_note("[2026-10-12] Surplus from last week: 1000 kcal to cut", tier="weekly")

        # Base weekly is 17,500 kcal. With 1000 kcal to cut, target is 16,500 kcal.
        # If planned is unadjusted at 17,500 kcal:
        meals = []
        for i in range(12, 19):
            date_str = f"2026-10-{i}"
            meals.append({"Date": date_str, "Meal": "Lunch", "Recipe": "Normal Meal", "Ingredient": "Chicken & Rice", "P": 150, "C": 280, "F": 70, "Calories": 2500})
        update_meal_plan_csv(self.test_dir, meals)

        res_unadjusted = check_meal_plan_csv(self.test_dir)
        self.assertFalse(res_unadjusted["accepted"])
        self.assertIn("Calories too high", res_unadjusted["message"])

        # When adjusted to cut the 1000 kcal (e.g. 7 * ~2357 kcal = ~16,500 kcal)
        meals = []
        for i in range(12, 19):
            date_str = f"2026-10-{i}"
            meals.append({"Date": date_str, "Meal": "Lunch", "Recipe": "Lean Bowl", "Ingredient": "Chicken & Rice", "P": 150, "C": 260, "F": 65, "Calories": 2357})
        update_meal_plan_csv(self.test_dir, meals)

        res = check_meal_plan_csv(self.test_dir)
        self.assertTrue(res["accepted"])
        self.assertIn("[ACCEPTED]", res["message"])
        self.assertIn("Carried adjustment from last week: -1000 kcal", res["message"])

    def test_tool_check_meal_plan_registered_and_executable(self):
        """Verifies that tool_check_meal_plan is in get_agent_tools and returns formatted response."""
        tools = get_agent_tools(data_dir=self.test_dir)
        tool_dict = {t.__name__: t for t in tools}
        self.assertIn("tool_check_meal_plan", tool_dict)

        # Execute tool on empty dir
        out = tool_dict["tool_check_meal_plan"]()
        self.assertIn("[NEEDS FIXING]", out)
