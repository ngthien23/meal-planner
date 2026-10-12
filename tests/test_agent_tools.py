import unittest
import os
import shutil
from meal_planner.agent import get_agent_tools, build_system_instruction

class TestAgentTools(unittest.TestCase):
    def test_agent_tools_registered(self):
        tools = get_agent_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertEqual(len(tool_names), 3)
        self.assertIn("tool_save_memory_note", tool_names)
        self.assertIn("tool_update_plans", tool_names)
        self.assertIn("tool_check_meal_plan", tool_names)

        # Legacy separated I/O tools must not be registered
        self.assertNotIn("tool_get_meal_plan", tool_names)
        self.assertNotIn("tool_update_meal_plan", tool_names)
        self.assertNotIn("tool_get_grocery_list", tool_names)
        self.assertNotIn("tool_update_grocery_list", tool_names)
        self.assertNotIn("tool_get_batch_cook", tool_names)
        self.assertNotIn("tool_update_batch_cook", tool_names)

        # Legacy programmatic solvers must not be registered
        self.assertNotIn("tool_generate_meal_plan", tool_names)
        self.assertNotIn("tool_report_meal_deviation", tool_names)
        self.assertNotIn("tool_substitute_ingredient", tool_names)
        self.assertNotIn("tool_catch_up_inventory", tool_names)
        self.assertNotIn("tool_get_inventory", tool_names)

    def test_system_instruction_contains_temporal_context(self):
        prompt = build_system_instruction("Europe/Brussels")
        self.assertIn("Europe/Brussels", prompt)
        self.assertIn("Local Time:", prompt)
        self.assertIn("raw/dry ingredient weights", prompt)
        self.assertNotIn("Dietary Bans:", prompt)
        self.assertIn("MACRONUTRIENT NOTATION (NO GRAMS FOR P/C/F)", prompt)
        self.assertIn("40P", prompt)

    def test_tool_execution_flow(self):
        from meal_planner.tools.artifacts import get_meal_plan_csv, get_batch_cook_csv, get_grocery_list_csv
        test_dir = "tests/test_agent_flow"
        os.makedirs(test_dir, exist_ok=True)
        try:
            tools_map = {t.__name__: t for t in get_agent_tools(data_dir=test_dir)}
            # 1. Save profile to long-term memory
            msg = tools_map["tool_save_memory_note"]("Bodyweight: 65.0 kg | Goal: lean_bulk | Target Calories: 2550 kcal", tier="long_term")
            self.assertIn("Saved to long-term memory", msg)

            # 2. Update meal plan, batch cook, and grocery list in ONE single call!
            update_res = tools_map["tool_update_plans"](
                meal_entries=[{
                    "Date": "2026-10-10",
                    "Meal": "Lunch",
                    "Recipe": "Air Fried Chicken",
                    "Ingredient": "250g Chicken Thighs; 150g Rice",
                    "P": 50,
                    "C": 40,
                    "F": 15,
                    "Calories": 500
                }],
                batch_cook_entries=[{
                    "Dish": "Braised Pork",
                    "Main_Protein": "1000g Pork Belly",
                    "Meals": 3
                }],
                grocery_entries=[{
                    "Run": "2026-10-10 Run",
                    "Category": "meat",
                    "Item": "Chicken Thighs",
                    "Quantity_g": 1000,
                    "Estimated_Price_EUR": 8.50
                }]
            )
            self.assertIn("Meal Plan: Successfully updated", update_res)
            self.assertIn("Batch Cook: Successfully updated batch cook instructions", update_res)
            self.assertIn("Grocery List: Successfully updated", update_res)

            # Verify artifacts on disk
            plan_rows = get_meal_plan_csv(test_dir)
            self.assertTrue(any("Air Fried Chicken" in r.get("Recipe", "") for r in plan_rows))

            batch_rows = get_batch_cook_csv(test_dir)
            self.assertTrue(any("Braised Pork" in r.get("Dish", "") for r in batch_rows))

            grocery_rows = get_grocery_list_csv(test_dir)
            self.assertTrue(any("Chicken Thighs" in r.get("Item", "") for r in grocery_rows))
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

    def test_model_name_resolution(self):
        from meal_planner.cli import get_model_name
        # Default should be gemini-3.8-flash
        old_val = os.environ.pop("GEMINI_MODEL", None)
        try:
            self.assertEqual(get_model_name(), "gemini-3.8-flash")
            os.environ["GEMINI_MODEL"] = "custom-model"
            self.assertEqual(get_model_name(), "custom-model")
        finally:
            if old_val:
                os.environ["GEMINI_MODEL"] = old_val
            else:
                os.environ.pop("GEMINI_MODEL", None)
