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
            "fat_multiplier": 1.0,
            "eating_preferences": "Prefer Vietnamese food, broth-based, noodle. Usually buys Thai jasmine rice."
        })
        self.assertEqual(profile.bodyweight_kg, 65.0)
        self.assertEqual(profile.timezone, "Europe/Brussels")
        
        # Verify persistence and lack of overkill texture fields
        loaded = load_user_profile(self.test_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.bodyweight_kg, 65.0)
        self.assertEqual(loaded.target_calories, 2550.0)

        # Check raw json
        import json
        with open(os.path.join(self.test_dir, "profile.json"), "r", encoding="utf-8") as f:
            raw_json = json.load(f)
        self.assertNotIn("texture_rules", raw_json)
        self.assertNotIn("batch_prep_days", raw_json)

        # Check long term memory persistence
        from meal_planner.tools.memory import MemoryManager
        mem = MemoryManager(self.test_dir).get_context()
        self.assertTrue(any("Vietnamese food" in note for note in mem["long_term"]))
