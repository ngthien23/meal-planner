import unittest
import os
import shutil
import tempfile
from unittest.mock import patch

from meal_planner.cli import quick_setup_wizard
from meal_planner.agent import build_system_instruction, get_agent_tools
from meal_planner.tools.memory import MemoryManager


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
        """Quick setup wizard should only ask for API key with minimal text, without profile.json or suggestion notes."""
        env_file = os.path.join(self.test_dir, ".env")
        inputs = iter(["my-secret-key-123"])

        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file):
            quick_setup_wizard(data_dir=self.test_dir, force=True)

        # Verify profile.json is NOT created
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "profile.json")))

        # Verify no plan files were pre-generated
        plans_dir = os.path.join(self.test_dir, "plans")
        if os.path.exists(plans_dir):
            self.assertEqual(os.listdir(plans_dir), [])

        # Verify .env has API key
        self.assertTrue(os.path.exists(env_file))
        with open(env_file, "r", encoding="utf-8") as f:
            self.assertIn("my-secret-key-123", f.read())

    def test_quick_setup_wizard_skips_when_api_key_already_present(self):
        """When API key is already in environment on first launch, wizard asks nothing."""
        os.environ["GEMINI_API_KEY"] = "already-configured-key"
        mock_input = unittest.mock.MagicMock()

        quick_setup_wizard(data_dir=self.test_dir, input_fn=mock_input, force=False)
        mock_input.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, "profile.json")))

    def test_quick_setup_wizard_allows_editing_api_key_when_forced(self):
        """When force=True (e.g. meals --setup), wizard prompts to edit or update API key without suggestion notes."""
        os.environ["GEMINI_API_KEY"] = "old-key-123"
        env_file = os.path.join(self.test_dir, ".env")
        inputs = iter(["new-replacement-key-456"])

        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file):
            quick_setup_wizard(data_dir=self.test_dir, force=True)

        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "new-replacement-key-456")
        with open(env_file, "r", encoding="utf-8") as f:
            self.assertIn("new-replacement-key-456", f.read())

    def test_system_instruction_first_chat_instructs_onboarding(self):
        """When long_term.md has no profile stats, system instruction guides the agent to ask preferences."""
        instruction = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("ONBOARDING STATE", instruction)
        self.assertIn("tool_save_memory_note", instruction)
        self.assertIn("Weekly budget for protein", instruction)
        self.assertNotIn("ACTIVE PLANNING STATE", instruction)

    def test_system_instruction_subsequent_chat_assists_planning(self):
        """When long_term.md has profile stats, system instruction guides the agent to assist directly without re-asking."""
        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        tools_map["tool_save_memory_note"](
            "Bodyweight: 65.0 kg | Goal: lean_bulk | Target Calories: 2550 kcal | Weekly Protein Budget: EUR 45.00",
            tier="long_term"
        )

        instruction = build_system_instruction(user_timezone="Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("ACTIVE PLANNING STATE", instruction)
        self.assertNotIn("ONBOARDING STATE", instruction)
        self.assertIn("65.0 kg", instruction)

    def test_tool_save_memory_note_records_onboarding(self):
        """Calling tool_save_memory_note saves profile facts to long_term.md."""
        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        msg = tools_map["tool_save_memory_note"]("Bodyweight: 70.0 kg | Target Calories: 2600 kcal", tier="long_term")
        self.assertIn("Saved to long-term memory", msg)

        ctx = MemoryManager(self.test_dir).get_context()
        self.assertTrue(any("70.0 kg" in n for n in ctx["long_term"]))


if __name__ == "__main__":
    unittest.main()
