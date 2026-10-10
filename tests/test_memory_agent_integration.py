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
        tools = get_agent_tools(self.test_dir)
        tools_map = {t.__name__: t for t in tools}

        # Onboard athlete via long-term memory note
        save_msg = tools_map["tool_save_memory_note"](
            "Athlete bodyweight: 65.0 kg, Target calories: 2550 kcal, Goal: lean_bulk, Timezone: Europe/Brussels",
            "long_term"
        )
        self.assertIn("Saved to long-term memory", save_msg)

        # Update meal plan
        update_plan_msg = tools_map["tool_update_meal_plan"]([
            {
                "Date": "2026-10-15",
                "Meal": "Dinner",
                "Recipe": "Double Whey Shake",
                "Ingredient": "60g ON Whey; 300ml Soy Milk",
                "P": 50,
                "C": 10,
                "F": 4,
                "Calories": 300
            }
        ])
        self.assertIn("Successfully updated", update_plan_msg)

        # Get meal plan
        plan_str = tools_map["tool_get_meal_plan"](target_date="2026-10-15")
        self.assertIn("Double Whey Shake", plan_str)
        self.assertIn("300", plan_str)

        # Update grocery list
        update_groc_msg = tools_map["tool_update_grocery_list"]([
            {
                "Run": "2026-10-15 Run",
                "Category": "supplement",
                "Item": "ON Whey Gold Standard",
                "Quantity_g": 900,
                "Estimated_Price_EUR": 35.00
            }
        ])
        self.assertIn("Successfully updated grocery list", update_groc_msg)

        # View groceries
        g_msg = tools_map["tool_get_grocery_list"]()
        self.assertIn("ON Whey Gold Standard", g_msg)
        self.assertIn("900g", g_msg)


if __name__ == "__main__":
    unittest.main()
