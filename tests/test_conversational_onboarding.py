import unittest
import os
import shutil
import tempfile
from unittest.mock import patch

from meal_planner.models import UserProfile
from meal_planner.tools.onboarding import init_user_profile, load_user_profile
from meal_planner.cli import quick_setup_wizard, serve_adk_playground
from meal_planner.agent import build_system_instruction, get_agent_tools


class TestConversationalOnboarding(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_env = dict(os.environ)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_quick_setup_wizard_minimal_only_asks_api_key_if_missing(self):
        """Quick setup wizard should only ask for API key with minimal text, leaving the rest to the agent."""
        env_file = os.path.join(self.test_dir, ".env")
        inputs = iter(["my-secret-key-123"])

        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file):
            profile = quick_setup_wizard(data_dir=self.test_dir, force=True)

        self.assertIsNotNone(profile)
        self.assertFalse(profile.is_onboarded)
        self.assertEqual(profile.bodyweight_kg, 0.0)
        self.assertEqual(profile.target_calories, 0.0)
        self.assertEqual(profile.restrictions, [])

        # Verify no plan files were pre-generated
        plans_dir = os.path.join(self.test_dir, "plans")
        if os.path.exists(plans_dir):
            self.assertEqual(os.listdir(plans_dir), [])

        # Verify .env has API key
        self.assertTrue(os.path.exists(env_file))
        with open(env_file, "r", encoding="utf-8") as f:
            self.assertIn("my-secret-key-123", f.read())

    def test_quick_setup_wizard_skips_when_api_key_already_present(self):
        """When API key is already in environment on first launch, wizard asks nothing and initializes un-onboarded profile."""
        os.environ["GEMINI_API_KEY"] = "already-configured-key"
        mock_input = unittest.mock.MagicMock()

        profile = quick_setup_wizard(data_dir=self.test_dir, input_fn=mock_input, force=False)
        mock_input.assert_not_called()
        self.assertFalse(profile.is_onboarded)

    def test_quick_setup_wizard_allows_editing_api_key_when_forced(self):
        """When force=True (e.g. meals --setup), wizard prompts to edit or update API key even if one is already present."""
        os.environ["GEMINI_API_KEY"] = "old-key-123"
        env_file = os.path.join(self.test_dir, ".env")
        inputs = iter(["new-replacement-key-456"])

        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file):
            profile = quick_setup_wizard(data_dir=self.test_dir, force=True)

        self.assertIsNotNone(profile)
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "new-replacement-key-456")
        with open(env_file, "r", encoding="utf-8") as f:
            self.assertIn("new-replacement-key-456", f.read())

    def test_system_instruction_first_chat_instructs_onboarding(self):
        """When athlete is not onboarded, system instruction guides the agent to ask preferences and generate plans."""
        init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "is_onboarded": False,
            "bodyweight_kg": 0.0,
            "target_calories": 0.0
        })

        instruction = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("ONBOARDING STATE", instruction)
        self.assertIn("tool_onboard_user", instruction)
        self.assertIn("tool_generate_meal_plan", instruction)
        self.assertNotIn("ACTIVE PLANNING STATE", instruction)

    def test_system_instruction_subsequent_chat_assists_planning(self):
        """When athlete is already onboarded, system instruction guides the agent to assist directly without re-asking."""
        init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "is_onboarded": True,
            "bodyweight_kg": 65.0,
            "target_calories": 2550.0,
            "goal_state": "lean_bulk"
        })

        instruction = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("ACTIVE PLANNING STATE", instruction)
        self.assertNotIn("ONBOARDING STATE", instruction)
        self.assertIn("65.0 kg", instruction)

    def test_tool_onboard_user_marks_is_onboarded_true(self):
        """Calling tool_onboard_user updates profile and sets is_onboarded to True."""
        init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "is_onboarded": False
        })

        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        msg = tools_map["tool_onboard_user"]("Europe/Brussels", 70.0, "lean_bulk", 2600.0, 2.0, 1.0)
        self.assertIn("Profile initialized", msg)

        updated_profile = load_user_profile(self.test_dir)
        self.assertTrue(updated_profile.is_onboarded)
        self.assertEqual(updated_profile.bodyweight_kg, 70.0)
        self.assertEqual(updated_profile.target_calories, 2600.0)


if __name__ == "__main__":
    unittest.main()
