import unittest
from datetime import datetime
import zoneinfo
import os
import shutil
from meal_planner.tools.onboarding import (
    resolve_timezone,
    get_relative_datetime,
    init_user_profile,
    load_user_profile
)

class TestOnboarding(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_onboarding_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_resolve_valid_and_invalid_timezones(self):
        tz = resolve_timezone("Europe/Brussels")
        self.assertEqual(tz.key, "Europe/Brussels")
        # Review Focus 1: Timezone fallback
        fallback_tz = resolve_timezone("Invalid/Zone")
        self.assertEqual(fallback_tz.key, "UTC")

    def test_relative_date_anchoring(self):
        # Reference: Thursday 2026-10-15 14:00:00 Brussels time
        ref = datetime(2026, 10, 15, 14, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        dt, meal_type = get_relative_datetime("tonight", "Europe/Brussels", reference_dt=ref)
        self.assertEqual(dt.strftime("%Y-%m-%d"), "2026-10-15")
        self.assertEqual(meal_type, "dinner")

        dt2, meal_type2 = get_relative_datetime("tomorrow's lunch", "Europe/Brussels", reference_dt=ref)
        self.assertEqual(dt2.strftime("%Y-%m-%d"), "2026-10-16")
        self.assertEqual(meal_type2, "lunch")

    def test_init_and_load_user_profile(self):
        profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 65.0,
            "goal_state": "lean_bulk",
            "target_calories": 2550.0,
            "protein_multiplier": 2.3,
            "fat_multiplier": 1.0
        })
        self.assertEqual(profile.bodyweight_kg, 65.0)
        self.assertEqual(profile.timezone, "Europe/Brussels")
        
        # Verify persistence
        loaded = load_user_profile(self.test_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.bodyweight_kg, 65.0)
        self.assertEqual(loaded.target_calories, 2550.0)
