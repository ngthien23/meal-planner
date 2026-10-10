import unittest
import os
import shutil
from meal_planner.agent import get_agent_tools, build_system_instruction

class TestAgentTools(unittest.TestCase):
    def test_agent_tools_registered(self):
        tools = get_agent_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("tool_onboard_user", tool_names)
        self.assertIn("tool_generate_meal_plan", tool_names)
        self.assertIn("tool_report_meal_deviation", tool_names)
        self.assertIn("tool_substitute_ingredient", tool_names)
        self.assertIn("tool_get_analytics", tool_names)

    def test_system_instruction_contains_temporal_context(self):
        prompt = build_system_instruction("Europe/Brussels")
        self.assertIn("Europe/Brussels", prompt)
        self.assertIn("soft, liquid, or broth-based", prompt)
        self.assertIn("raw/dry ingredient weights", prompt)

    def test_tool_execution_flow(self):
        test_dir = "tests/test_agent_flow"
        os.makedirs(test_dir, exist_ok=True)
        try:
            tools_map = {t.__name__: t for t in get_agent_tools(data_dir=test_dir)}
            # 1. Onboard
            msg = tools_map["tool_onboard_user"]("Europe/Brussels", 65.0, "lean_bulk", 2550.0, 2.3, 1.0)
            self.assertIn("Profile created", msg)
            
            # 2. Generate plan
            plan_msg = tools_map["tool_generate_meal_plan"]()
            self.assertIn("Generated 7-day meal plan", plan_msg)

            # 3. Report deviation
            dev_msg = tools_map["tool_report_meal_deviation"]("Thursday", "dinner", "Double Whey Shake", 50.0, 300.0)
            self.assertIn("Adapted meal plan", dev_msg)
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
