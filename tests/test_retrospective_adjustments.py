import unittest
import os
import shutil
import tempfile
import csv
from datetime import datetime
import zoneinfo

from meal_planner.tools.inventory import (
    InventoryState,
    InventoryItem,
    save_inventory_state,
    load_inventory_state,
    reconcile_past_meal_deviation,
    reconcile_inventory_state,
)
from meal_planner.tools.adaptation import spread_missed_calories
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import (
    ensure_weekly_plan_artifacts,
    get_current_cycle_prefix,
)


class TestRetrospectiveAdjustments(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tz = zoneinfo.ZoneInfo("Europe/Brussels")
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True,
            "week_start_day": "Saturday",
        })
        # Generate weekly plan starting Saturday 2026-10-10
        ref_dt = datetime(2026, 10, 10, 8, 0, tzinfo=self.tz)
        ensure_weekly_plan_artifacts(self.profile, self.test_dir, reference_dt=ref_dt)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_skipped_breakfast_restores_stock_and_rolls_over_deficit(self):
        # 1. State where ingredients were deducted
        state = InventoryState(last_reconciled_at="2026-10-10T12:00:00+02:00", items=[])
        save_inventory_state(self.test_dir, state)

        # 2. User reports skipping breakfast
        result = reconcile_past_meal_deviation(
            self.test_dir,
            target_date="2026-10-10",
            slot_name="breakfast",
            deviation_type="skipped",
            roll_over_difference=True,
            user_tz="Europe/Brussels",
        )
        self.assertTrue(result["success"])
        self.assertGreater(result["restored_items_count"], 0)
        self.assertGreater(result["carried_calories"], 0)

        # Verify stock was restored in inventory.json
        inv = load_inventory_state(self.test_dir)
        self.assertGreater(inv.carried_calories, 0)
        self.assertTrue(any(i.quantity_g > 0 for i in inv.items))

        # Verify logged to meal_logs.csv with adherence='skipped'
        logs_path = os.path.join(self.test_dir, "meal_logs.csv")
        self.assertTrue(os.path.exists(logs_path))
        with open(logs_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            self.assertTrue(any(
                r["Date"] == "2026-10-10" and r["Meal"].lower() == "breakfast" and r["Adherence"] == "skipped"
                for r in reader
            ))

    def test_eating_out_does_not_deduct_home_stock(self):
        result = reconcile_past_meal_deviation(
            self.test_dir,
            target_date="2026-10-10",
            slot_name="lunch",
            deviation_type="eat_out",
            actual_calories=800.0,
            actual_protein_g=40.0,
            user_tz="Europe/Brussels",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["actual_calories"], 800.0)

        # Verify meal_logs.csv records eat_out
        logs_path = os.path.join(self.test_dir, "meal_logs.csv")
        with open(logs_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            self.assertTrue(any(
                r["Date"] == "2026-10-10" and r["Meal"].lower() == "lunch" and r["Adherence"] == "eat_out"
                for r in reader
            ))

    def test_eating_out_rolls_over_deficit_when_actual_less_than_planned(self):
        # When restaurant meal has fewer calories than planned meal
        result = reconcile_past_meal_deviation(
            self.test_dir,
            target_date="2026-10-10",
            slot_name="lunch",
            deviation_type="eat_out",
            actual_calories=300.0,
            actual_protein_g=20.0,
            roll_over_difference=True,
            user_tz="Europe/Brussels",
        )
        self.assertTrue(result["success"])
        self.assertGreater(result["carried_calories"], 0)

        inv = load_inventory_state(self.test_dir)
        self.assertGreater(inv.carried_calories, 0)

    def test_skipped_meal_without_rollover(self):
        result = reconcile_past_meal_deviation(
            self.test_dir,
            target_date="2026-10-10",
            slot_name="breakfast",
            deviation_type="skipped",
            roll_over_difference=False,
            user_tz="Europe/Brussels",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["carried_calories"], 0.0)

        inv = load_inventory_state(self.test_dir)
        self.assertEqual(inv.carried_calories, 0.0)
        # But ingredients were still restored
        self.assertTrue(any(i.quantity_g > 0 for i in inv.items))

    def test_spread_missed_calories_across_future_days_capped(self):
        # Seed carried calories: 600 kcal and 45g protein
        state = InventoryState(
            last_reconciled_at="2026-10-10T12:00:00+02:00",
            carried_calories=600.0,
            carried_protein_g=45.0,
            items=[]
        )
        save_inventory_state(self.test_dir, state)

        # Distribute with current time set to Saturday noon (2026-10-10 12:00)
        cur_dt = datetime(2026, 10, 10, 12, 0, tzinfo=self.tz)
        res = spread_missed_calories(
            self.test_dir,
            max_daily_calories=200.0,
            max_daily_protein_g=15.0,
            reference_dt=cur_dt,
            user_tz="Europe/Brussels",
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["distributed"])
        self.assertLessEqual(res["daily_calorie_increase"], 200.0)
        self.assertLessEqual(res["daily_protein_increase_g"], 15.0)
        self.assertGreater(res["days_affected"], 0)

        # Carried calories in inventory should be reduced by distributed amount
        inv = load_inventory_state(self.test_dir)
        expected_remaining = round(600.0 - (res["daily_calorie_increase"] * res["days_affected"]), 2)
        self.assertAlmostEqual(inv.carried_calories, expected_remaining, places=1)

        # Verify meal plan CSV for future days shows increased Breakfast calories
        prefix = get_current_cycle_prefix("Europe/Brussels", reference_dt=cur_dt, week_start_day="Saturday")
        plan_csv = os.path.join(self.test_dir, "plans", f"{prefix}_meal_plan.csv")
        with open(plan_csv, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            # Sunday breakfast should have adjusted calories
            sunday_b = next((r for r in reader if r["Date"] == "2026-10-11" and r["Meal"].lower() == "breakfast"), None)
            self.assertIsNotNone(sunday_b)
            self.assertGreater(float(sunday_b["Calories"]), 400.0)

    def test_spread_missed_calories_no_op_when_zero(self):
        state = InventoryState(carried_calories=0.0, carried_protein_g=0.0, items=[])
        save_inventory_state(self.test_dir, state)

        res = spread_missed_calories(self.test_dir)
        self.assertTrue(res["success"])
        self.assertFalse(res["distributed"])
        self.assertEqual(res["daily_calorie_increase"], 0.0)

    def test_subsequent_chat_catchup_does_not_rededuct_restored_stock(self):
        # Setup initial stock
        state = InventoryState(last_reconciled_at="2026-10-10T12:00:00+02:00", items=[])
        save_inventory_state(self.test_dir, state)

        # Reconcile skipped breakfast on 2026-10-10
        result = reconcile_past_meal_deviation(
            self.test_dir,
            target_date="2026-10-10",
            slot_name="breakfast",
            deviation_type="skipped",
            roll_over_difference=True,
            user_tz="Europe/Brussels",
        )
        self.assertTrue(result["success"])

        inv_after_skip = load_inventory_state(self.test_dir)
        restored_item = next((i for i in inv_after_skip.items if "whey" in i.food_id.lower() or "soy" in i.food_id.lower()), None)
        self.assertIsNotNone(restored_item)
        restored_qty = restored_item.quantity_g
        self.assertGreater(restored_qty, 0)

        # Subsequent chat reconciliation runs at 15:00
        new_state, actions = reconcile_inventory_state(
            self.test_dir,
            current_dt=datetime(2026, 10, 10, 15, 0, tzinfo=self.tz),
            user_tz="Europe/Brussels",
        )
        item_after_catchup = next((i for i in new_state.items if i.food_id == restored_item.food_id), None)
        self.assertIsNotNone(item_after_catchup)
        # Quantity must NOT have been re-deducted
        self.assertEqual(item_after_catchup.quantity_g, restored_qty)

    def test_reconcile_past_meal_deviation_is_idempotent(self):
        state = InventoryState(last_reconciled_at="2026-10-10T12:00:00+02:00", items=[])
        save_inventory_state(self.test_dir, state)

        # First report
        res1 = reconcile_past_meal_deviation(
            self.test_dir, target_date="2026-10-10", slot_name="breakfast",
            deviation_type="skipped", roll_over_difference=True, user_tz="Europe/Brussels"
        )
        self.assertTrue(res1["success"])
        inv1 = load_inventory_state(self.test_dir)
        initial_qty = sum(i.quantity_g for i in inv1.items)

        # Second report of same skipped meal
        res2 = reconcile_past_meal_deviation(
            self.test_dir, target_date="2026-10-10", slot_name="breakfast",
            deviation_type="skipped", roll_over_difference=True, user_tz="Europe/Brussels"
        )
        self.assertTrue(res2["success"])
        inv2 = load_inventory_state(self.test_dir)
        second_qty = sum(i.quantity_g for i in inv2.items)

        # Stock must NOT be double-incremented
        self.assertEqual(initial_qty, second_qty)

    def test_reconcile_future_meal_does_not_restore_stock_before_cutoff(self):
        state = InventoryState(last_reconciled_at="2026-10-10T09:00:00+02:00", items=[])
        save_inventory_state(self.test_dir, state)

        # Reporting dinner at 10:00 AM (dinner cutoff 21:00 has NOT passed yet)
        res = reconcile_past_meal_deviation(
            self.test_dir, target_date="2026-10-10", slot_name="dinner",
            deviation_type="skipped", roll_over_difference=True, user_tz="Europe/Brussels",
            reference_dt=datetime(2026, 10, 10, 10, 0, tzinfo=self.tz)
        )
        self.assertTrue(res["success"])
        inv = load_inventory_state(self.test_dir)
        # Because dinner cutoff hasn't passed, ingredients were never deducted, so 0 items should be restored to stock!
        self.assertEqual(res["restored_items_count"], 0)
        self.assertEqual(len(inv.items), 0)
