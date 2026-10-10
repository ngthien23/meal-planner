import unittest
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock

from meal_planner.models import UserProfile, CURRENCY_SYMBOLS, get_currency_symbol
from meal_planner.tools.onboarding import init_user_profile, load_user_profile
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

    def test_default_preferences_are_empty(self):
        """Default UserProfile should have empty restrictions list for clean new user onboarding."""
        profile = UserProfile()
        self.assertEqual(profile.restrictions, [])
        self.assertEqual(profile.currency, "EUR")
        self.assertEqual(get_currency_symbol("EUR"), "€")
        self.assertEqual(get_currency_symbol("USD"), "$")
        self.assertEqual(get_currency_symbol("GBP"), "£")
        self.assertEqual(get_currency_symbol("VND"), "₫")

    def test_init_user_profile_default_empty_restrictions(self):
        """init_user_profile should persist empty restrictions and currency if not explicitly set."""
        profile = init_user_profile(self.test_dir, {
            "timezone": "UTC",
            "bodyweight_kg": 70.0,
            "currency": "USD"
        })
        self.assertEqual(profile.restrictions, [])
        self.assertEqual(profile.currency, "USD")

        loaded = load_user_profile(self.test_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.restrictions, [])
        self.assertEqual(loaded.currency, "USD")

    def test_quick_setup_wizard_interactive_defaults(self):
        """Quick setup wizard should create .env and profile.json with empty default preferences."""
        # Mock inputs:
        # 1. API key: AIzaSyTestKey123
        # 2. Timezone: Europe/Paris
        # 3. Currency: EUR
        # 4. Week start day: Monday
        # 5. Weeks ahead: 1
        # 6. Bodyweight: 70
        # 7. Goal state: maintenance
        # 8. Target calories: (enter for auto)
        # 9. Protein multiplier: (enter for default 2.0)
        # 10. Fat multiplier: (enter for default 1.0)
        # 11. Restrictions: (enter for none -> empty [])
        simulated_inputs = iter([
            "AIzaSyTestKey123",  # API Key
            "Europe/Paris",      # Timezone
            "EUR",               # Currency
            "Monday",            # Week start day
            "1",                 # Weeks ahead
            "70",                # Bodyweight
            "maintenance",       # Goal state
            "",                  # Target calories (auto)
            "",                  # Protein mult
            "",                  # Fat mult
            "",                  # Restrictions (empty default)
        ])

        env_file = os.path.join(self.test_dir, ".env")
        with patch("builtins.input", side_effect=lambda prompt="": next(simulated_inputs)), \
             patch("meal_planner.cli.ENV_PATH", env_file):
            profile = quick_setup_wizard(data_dir=self.test_dir, force=True)

        self.assertIsNotNone(profile)
        self.assertEqual(profile.timezone, "Europe/Paris")
        self.assertEqual(profile.currency, "EUR")
        self.assertEqual(profile.week_start_day, "Monday")
        self.assertEqual(profile.restrictions, [])
        self.assertAlmostEqual(profile.target_calories, 70 * 32, delta=50)

        # Verify .env was written
        self.assertTrue(os.path.exists(env_file))
        with open(env_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("AIzaSyTestKey123", content)

        # Verify profile was saved to disk
        loaded = load_user_profile(self.test_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.restrictions, [])

    def test_quick_setup_custom_restrictions(self):
        """User can specify custom comma-separated restrictions during quick setup."""
        simulated_inputs = iter([
            "",               # API key skipped
            "UTC",            # Timezone
            "USD",            # Currency
            "Sunday",         # Week start day
            "1",              # Weeks ahead
            "60",             # Bodyweight
            "cut",            # Goal state
            "1800",           # Explicit calories
            "2.2",            # Protein mult
            "0.8",            # Fat mult
            "no peanuts, gluten free", # Restrictions
        ])

        with patch("builtins.input", side_effect=lambda prompt="": next(simulated_inputs)):
            profile = quick_setup_wizard(data_dir=self.test_dir, force=True)

        self.assertEqual(profile.currency, "USD")
        self.assertEqual(profile.restrictions, ["no peanuts", "gluten free"])
        self.assertEqual(profile.target_calories, 1800.0)

    @patch("meal_planner.cli.subprocess.run")
    @patch("meal_planner.cli.webbrowser.open")
    def test_run_meals_shortcut_launches_adk_and_browser(self, mock_browser, mock_subproc):
        """meals shortcut should launch browser and start ADK server."""
        os.environ["GEMINI_API_KEY"] = "fake_test_key"
        init_user_profile(self.test_dir, {"timezone": "UTC", "currency": "EUR"})

        with patch("meal_planner.cli._open_browser_delayed") as mock_open_delayed:
            run_meals_shortcut(args=["--port=8085", "--host=127.0.0.1", self.test_dir])
            mock_open_delayed.assert_called_once_with("http://127.0.0.1:8085/dev-ui/?app=meal_planner")
            mock_subproc.assert_called_once()

    @patch("meal_planner.cli.subprocess.run")
    def test_run_meals_shortcut_no_browser_flag(self, mock_subproc):
        """--no-browser flag should prevent launching the browser."""
        os.environ["GEMINI_API_KEY"] = "fake_test_key"
        init_user_profile(self.test_dir, {"timezone": "UTC", "currency": "EUR"})

        with patch("meal_planner.cli._open_browser_delayed") as mock_open_delayed:
            run_meals_shortcut(args=["--no-browser", "--port=8085", self.test_dir])
            mock_open_delayed.assert_not_called()
            mock_subproc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
