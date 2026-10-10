import unittest
import os
import shutil
from datetime import datetime
import zoneinfo
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import (
    get_current_cycle_prefix,
    ensure_weekly_plan_artifacts
)

class TestDatedArtifacts(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_dated_data"
        os.makedirs(self.test_dir, exist_ok=True)
        self.profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_cycle_prefix_calculation(self):
        # Reference date: Thursday 2026-10-15
        # The Saturday of this cycle was 2026-10-10 -> YYMMDD is "261010"
        ref = datetime(2026, 10, 15, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        prefix = get_current_cycle_prefix("Europe/Brussels", reference_dt=ref)
        self.assertEqual(prefix, "261010")

    def test_ensure_weekly_plan_creates_and_reuses(self):
        ref = datetime(2026, 10, 15, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        # First call: should create 261010_meal_plan.csv
        plan_csv, grocery_csv, created = ensure_weekly_plan_artifacts(
            self.profile, self.test_dir, reference_dt=ref
        )
        self.assertTrue(created)
        self.assertTrue(os.path.exists(plan_csv))
        self.assertIn("261010_meal_plan.csv", plan_csv)
        self.assertTrue(os.path.exists(grocery_csv))
        self.assertIn("261010_grocery_list.csv", grocery_csv)

        # Second call: should detect existing file and NOT recreate
        plan_csv2, grocery_csv2, created2 = ensure_weekly_plan_artifacts(
            self.profile, self.test_dir, reference_dt=ref
        )
        self.assertFalse(created2)
        self.assertEqual(plan_csv, plan_csv2)
