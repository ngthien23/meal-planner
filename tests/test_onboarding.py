import unittest
from meal_planner.tools.onboarding import resolve_timezone

class TestOnboarding(unittest.TestCase):
    def test_resolve_valid_and_invalid_timezones(self):
        tz = resolve_timezone("Europe/Brussels")
        self.assertEqual(tz.key, "Europe/Brussels")
        # Timezone fallback
        fallback_tz = resolve_timezone("Invalid/Zone")
        self.assertEqual(fallback_tz.key, "UTC")
        # Common aliases
        cet_tz = resolve_timezone("CET")
        self.assertEqual(cet_tz.key, "Europe/Brussels")
