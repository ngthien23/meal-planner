import unittest
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from meal_planner.models import CURRENCY_SYMBOLS, get_currency_symbol
from meal_planner.cli import quick_setup_wizard, run_meals_shortcut


class TestQuickSetupAndShortcut(unittest.TestCase):
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

    def test_currency_symbols(self):
        """Verifies currency symbol resolution."""
        self.assertEqual(get_currency_symbol("EUR"), "€")
        self.assertEqual(get_currency_symbol("USD"), "$")
        self.assertEqual(get_currency_symbol("GBP"), "£")
        self.assertEqual(get_currency_symbol("VND"), "₫")

    def test_quick_setup_wizard_interactive_defaults(self):
        """Quick setup wizard should prompt for API key and save to .env without creating profile.json."""
        env_file = os.path.join(self.test_dir, ".env")
        inputs = iter(["AIzaSyTestKey123"])

        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file):
            quick_setup_wizard(data_dir=self.test_dir, force=True)

        # Verify .env was written
        self.assertTrue(os.path.exists(env_file))
        with open(env_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("AIzaSyTestKey123", content)

        # Verify profile.json was NOT created
        profile_file = os.path.join(self.test_dir, "profile.json")
        self.assertFalse(os.path.exists(profile_file))

        # Verify no plan files were pre-generated
        plans_dir = os.path.join(self.test_dir, "plans")
        if os.path.exists(plans_dir):
            self.assertEqual(os.listdir(plans_dir), [])


    @patch("meal_planner.cli.subprocess.run")
    @patch("meal_planner.cli.webbrowser.open")
    def test_run_meals_shortcut_launches_adk_and_browser(self, mock_browser, mock_subproc):
        """meals shortcut should launch browser and start ADK server."""
        os.environ["GEMINI_API_KEY"] = "fake_test_key"

        with patch("meal_planner.cli._open_browser_delayed") as mock_open_delayed:
            run_meals_shortcut(args=["--port=8085", "--host=127.0.0.1", self.test_dir])
            mock_open_delayed.assert_called_once_with("http://127.0.0.1:8085/dev-ui/?app=meal_planner")
            mock_subproc.assert_called_once()

    @patch("meal_planner.cli.subprocess.run")
    def test_run_meals_shortcut_no_browser_flag(self, mock_subproc):
        """--no-browser flag should prevent launching the browser."""
        os.environ["GEMINI_API_KEY"] = "fake_test_key"

        with patch("meal_planner.cli._open_browser_delayed") as mock_open_delayed:
            run_meals_shortcut(args=["--no-browser", "--port=8085", self.test_dir])
            mock_open_delayed.assert_not_called()
            mock_subproc.assert_called_once()

    @patch("meal_planner.cli.subprocess.run")
    def test_run_meals_shortcut_setup_flag_runs_wizard_and_does_not_launch_server(self, mock_subproc):
        """meals --setup should run setup wizard and exit without launching the ADK server."""
        inputs = iter(["new-test-key"])
        env_file = os.path.join(self.test_dir, ".env")
        with patch("builtins.input", side_effect=lambda prompt="": next(inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file), \
             patch("meal_planner.cli._open_browser_delayed") as mock_open_delayed:
            run_meals_shortcut(args=["--setup", self.test_dir])
            mock_open_delayed.assert_not_called()
            mock_subproc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
