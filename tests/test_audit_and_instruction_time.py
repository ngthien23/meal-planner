import unittest
import os
import shutil
import tempfile
import time
from unittest.mock import patch, MagicMock

from meal_planner.agent import (
    build_system_instruction,
    get_agent_tools,
    get_recorded_time,
    reset_recorded_time,
    root_agent,
    get_root_agent,
)
from meal_planner.cli import ensure_api_key, quick_setup_wizard
from meal_planner.tools.artifacts import get_meal_plan_csv


class TestAuditAndInstructionTime(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        reset_recorded_time()

    def tearDown(self):
        reset_recorded_time()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_current_time_recorded_once(self):
        """Current time should be recorded once and remain constant across repeated calls."""
        reset_recorded_time()
        inst1 = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)
        time.sleep(0.05)
        inst2 = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)

        # Extract 'Local Time: ...' line from both instructions
        time_line1 = next(line for line in inst1.splitlines() if "Local Time:" in line)
        time_line2 = next(line for line in inst2.splitlines() if "Local Time:" in line)
        self.assertEqual(time_line1, time_line2)

    def test_root_agent_instruction_is_static_string(self):
        """Agent instruction must be a static string rather than a callable to avoid multiple System Instruction turns in ADK."""
        agent = get_root_agent(self.test_dir)
        self.assertIsNotNone(agent)
        self.assertIsInstance(agent.instruction, str)
        self.assertFalse(callable(agent.instruction))

    def test_all_tools_are_strictly_memory_and_artifact_helpers(self):
        """Tools must only interact with memory and artifacts, not do planning or deciding."""
        tools = get_agent_tools(self.test_dir)
        tool_names = set(t.__name__ for t in tools)
        expected_tools = {
            "tool_save_memory_note",
            "tool_update_plans",
            "tool_check_meal_plan",
        }
        self.assertEqual(tool_names, expected_tools)

        # No programmatic calculators or solvers
        self.assertNotIn("tool_get_macro_targets", tool_names)
        self.assertNotIn("tool_generate_meal_plan", tool_names)
        self.assertNotIn("tool_report_meal_deviation", tool_names)
        self.assertNotIn("tool_substitute_ingredient", tool_names)

    def test_get_meal_plan_csv_does_not_generate_plan_if_missing(self):
        """Pure artifact reader should return empty list when missing, without invoking programmatic planning."""
        empty_dir = os.path.join(self.test_dir, "empty_plans")
        rows = get_meal_plan_csv(empty_dir)
        self.assertEqual(rows, [])
        plans_dir = os.path.join(empty_dir, "plans")
        if os.path.exists(plans_dir):
            self.assertEqual(os.listdir(plans_dir), [])

    def test_no_default_preferences_in_system_instruction(self):
        """Verify no default preferences, texture bans, or dietary bans in the system prompt."""
        prompt = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)
        self.assertNotIn("Dietary Bans:", prompt)
        self.assertNotIn("Fortified soy milk only", prompt)
        self.assertNotIn("Texture rules: Breakfast & Dinner strictly soft", prompt)
        self.assertNotIn("~2.2g per kg bodyweight", prompt)
        self.assertNotIn("powerlifting athlete", prompt)

    def test_api_key_prompting_has_no_suggestions(self):
        """Prompts for API key must simply ask 'Enter Gemini API key: ' without suggestions or masked placeholders."""
        prompts_seen = []

        def capture_input(prompt=""):
            prompts_seen.append(prompt)
            return "test-key-789"

        # 1. Test ensure_api_key with no key in env
        orig_key = os.environ.pop("GEMINI_API_KEY", None)
        orig_google = os.environ.pop("GOOGLE_API_KEY", None)
        orig_keys = os.environ.pop("GEMINI_API_KEYS", None)
        test_env_file = os.path.join(self.test_dir, ".env")
        try:
            with patch("meal_planner.cli.ENV_PATH", test_env_file):
                ensure_api_key(input_fn=capture_input)
                self.assertEqual(prompts_seen[0], "Enter Gemini API key: ")

                # 2. Test quick_setup_wizard with force=True (already has key)
                quick_setup_wizard(data_dir=self.test_dir, input_fn=capture_input, force=True)
                self.assertIn("Enter Gemini API key: ", prompts_seen)
                for p in prompts_seen:
                    self.assertNotIn("keep current", p)
                    self.assertNotIn("***", p)
        finally:
            if orig_key:
                os.environ["GEMINI_API_KEY"] = orig_key
            if orig_google:
                os.environ["GOOGLE_API_KEY"] = orig_google
            if orig_keys:
                os.environ["GEMINI_API_KEYS"] = orig_keys


if __name__ == "__main__":
    unittest.main()
