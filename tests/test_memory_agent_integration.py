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

        # Onboard user
        tools_map["tool_onboard_user"](
            "Europe/Brussels", 65.0, "lean_bulk", 2550.0, 2.3, 1.0
        )

        # Generate meal plan
        gen_msg = tools_map["tool_generate_meal_plan"]()
        self.assertIn("_meal_plan.csv", gen_msg)
        self.assertIn("plans", gen_msg)

        # View groceries
        g_msg = tools_map["tool_view_grocery_list"]()
        self.assertIn("Run", g_msg)

        # Meal deviation should update both root and dated plans
        dev_msg = tools_map["tool_report_meal_deviation"](
            "Thursday", "dinner", "Double Whey Shake", 50.0, 300.0
        )
        self.assertIn("Adapted meal plan", dev_msg)
        self.assertIn("_meal_plan.csv", dev_msg)
