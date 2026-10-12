import unittest
import os
import shutil
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.memory import MemoryManager

class TestMemoryAgentIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_agent_mem"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_memory_tool_and_system_instruction(self):
        tools = get_agent_tools(self.test_dir)
        tools_map = {t.__name__: t for t in tools}
        self.assertIn("tool_save_memory_note", tools_map)

        # Save meaningful note
        msg = tools_map["tool_save_memory_note"]("User prefers higher sodium broth in Phở for lifting", "long_term")
        self.assertIn("Saved to long-term memory", msg)

        # Trivial note must be ignored
        msg_trivial = tools_map["tool_save_memory_note"]("Sounds good thanks!", "weekly")
        self.assertIn("ignored", msg_trivial.lower())

        # System instruction must include the memory context and artifact-pointing rule
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("higher sodium broth", prompt)
        self.assertIn("POINT TO THE ARTIFACT FILE", prompt)

    def test_dated_artifact_integration(self):
        from meal_planner.tools.artifacts import get_meal_plan_csv, get_grocery_list_csv
        tools = get_agent_tools(self.test_dir)
        tools_map = {t.__name__: t for t in tools}

        # Onboard athlete via long-term memory note
        save_msg = tools_map["tool_save_memory_note"](
            "Athlete bodyweight: 65.0 kg, Target calories: 2550 kcal, Goal: lean_bulk, Timezone: Europe/Brussels",
            "long_term"
        )
        self.assertIn("Saved to long-term memory", save_msg)

        # Update meal plan and grocery list in ONE consolidated tool call!
        update_plans_msg = tools_map["tool_update_plans"](
            meal_entries=[{
                "Date": "2026-10-15",
                "Meal": "Dinner",
                "Recipe": "Double Whey Shake",
                "Ingredient": "60g ON Whey; 300ml Soy Milk",
                "P": 50,
                "C": 10,
                "F": 4,
                "Calories": 300
            }],
            grocery_entries=[{
                "Run": "2026-10-15 Run",
                "Category": "supplement",
                "Item": "ON Whey Gold Standard",
                "Quantity_g": 900,
                "Estimated_Price_EUR": 35.00
            }]
        )
        self.assertIn("Meal Plan: Successfully updated", update_plans_msg)
        self.assertIn("Grocery List: Successfully updated", update_plans_msg)

        # Verify on disk
        plan_rows = get_meal_plan_csv(self.test_dir, target_date="2026-10-15")
        self.assertTrue(any("Double Whey Shake" in r.get("Recipe", "") for r in plan_rows))

        grocery_rows = get_grocery_list_csv(self.test_dir)
        self.assertTrue(any("ON Whey Gold Standard" in r.get("Item", "") for r in grocery_rows))


if __name__ == "__main__":
    unittest.main()
