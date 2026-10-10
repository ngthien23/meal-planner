import unittest
import os
import shutil
import tempfile
from datetime import datetime, time
import zoneinfo

from meal_planner.tools.inventory import (
    InventoryState,
    InventoryItem,
    save_inventory_state,
    load_inventory_state,
    reconcile_inventory_state,
)
from meal_planner.models import UserProfile
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts


class TestInventoryReconciliation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True
        })

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_chat_time_catchup_advances_past_meals_and_deducts_stock(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        # Simulate state last reconciled at 07:00 on Saturday 2026-10-10
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 7, 0, tzinfo=tz).isoformat(),
            items=[InventoryItem("chicken_breast", "Chicken Breast", 1000.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)

        # Chat happens at 15:00 on Saturday (Breakfast cutoff 10:00 and Lunch cutoff 14:30 have passed)
        chat_dt = datetime(2026, 10, 10, 15, 0, tzinfo=tz)
        new_state, actions = reconcile_inventory_state(self.test_dir, current_dt=chat_dt, user_tz="Europe/Brussels")
        self.assertEqual(new_state.last_reconciled_at, chat_dt.isoformat())
        self.assertTrue(any("consumed" in a.lower() for a in actions))

        # Check chicken breast was deducted for Lunch
        chicken_item = next(i for i in new_state.items if i.food_id == "chicken_breast")
        self.assertLess(chicken_item.quantity_g, 1000.0)

    def test_anchor_cutoffs_boundaries(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        ensure_weekly_plan_artifacts(self.profile, self.test_dir, reference_dt=datetime(2026, 10, 10, 6, 0, tzinfo=tz))

        # 1. 09:59 - before Breakfast cutoff (10:00)
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 6, 0, tzinfo=tz).isoformat(),
            items=[]
        )
        save_inventory_state(self.test_dir, state)
        st1, act1 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 9, 59, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertFalse(any("breakfast consumed" in a.lower() for a in act1))

        # 2. 10:01 - after Breakfast cutoff (10:00)
        st2, act2 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 10, 1, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertTrue(any("breakfast consumed" in a.lower() for a in act2))
        self.assertFalse(any("lunch consumed" in a.lower() for a in act2))

        # 3. 14:29 - before Lunch cutoff (14:30)
        st3, act3 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 14, 29, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertFalse(any("lunch consumed" in a.lower() for a in act3))

        # 4. 14:31 - after Lunch cutoff (14:30)
        st4, act4 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 14, 31, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertTrue(any("lunch consumed" in a.lower() for a in act4))
        self.assertFalse(any("dinner consumed" in a.lower() for a in act4))

        # 5. 20:59 - before Dinner cutoff (21:00)
        st5, act5 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 20, 59, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertFalse(any("dinner consumed" in a.lower() for a in act5))

        # 6. 21:01 - after Dinner cutoff (21:00)
        st6, act6 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 21, 1, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertTrue(any("dinner consumed" in a.lower() for a in act6))

    def test_scheduled_grocery_run_assumed_on_or_before_current_date(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        # Empty inventory at 06:00 on Saturday
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 6, 0, tzinfo=tz).isoformat(),
            items=[]
        )
        save_inventory_state(self.test_dir, state)

        # Chat at 09:00 on Saturday (Run date 2026-10-10 <= 2026-10-10)
        st, actions = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 9, 0, tzinfo=tz), user_tz="Europe/Brussels")
        # Saturday run items should be added with status="assumed"
        self.assertTrue(any("saturday run" in a.lower() for a in actions))
        assumed_items = [i for i in st.items if i.status == "assumed"]
        self.assertGreater(len(assumed_items), 0)

        # Wednesday run items should NOT be added yet
        self.assertFalse(any("wednesday run" in a.lower() for a in actions))

    def test_grocery_run_not_reassumed_on_subsequent_chat(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 6, 0, tzinfo=tz).isoformat(),
            items=[]
        )
        save_inventory_state(self.test_dir, state)

        st1, act1 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 9, 0, tzinfo=tz), user_tz="Europe/Brussels")
        num_items_1 = len(st1.items)

        # Subsequent chat at 09:30 on same day
        st2, act2 = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 9, 30, tzinfo=tz), user_tz="Europe/Brussels")
        self.assertEqual(len(st2.items), num_items_1)
        self.assertFalse(any("saturday run" in a.lower() for a in act2))

    def test_actual_stock_not_overwritten_by_assumed_run(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        # User explicitly reported 600g actual chicken breast
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 6, 0, tzinfo=tz).isoformat(),
            items=[InventoryItem("chicken_breast", "Chicken Breast Fillet", 600.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)

        st, actions = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 9, 0, tzinfo=tz), user_tz="Europe/Brussels")
        chicken = next(i for i in st.items if i.food_id == "chicken_breast")
        self.assertEqual(chicken.status, "actual")
        self.assertEqual(chicken.quantity_g, 600.0)

    def test_item_runs_out_clamped_to_zero(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        # User only has 50g chicken breast (less than the ~220g needed for Lunch)
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 11, 0, tzinfo=tz).isoformat(),
            items=[InventoryItem("chicken_breast", "Chicken Breast", 50.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)

        # Chat at 15:00 after Lunch cutoff
        st, actions = reconcile_inventory_state(self.test_dir, current_dt=datetime(2026, 10, 10, 15, 0, tzinfo=tz), user_tz="Europe/Brussels")
        chicken = next(i for i in st.items if i.food_id == "chicken_breast")
        self.assertEqual(chicken.quantity_g, 0.0)

    def test_initial_reconciliation_when_last_reconciled_at_is_none(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        # Inventory file exists but last_reconciled_at is None
        state = InventoryState(
            last_reconciled_at=None,
            items=[InventoryItem("chicken_breast", "Chicken Breast", 1000.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)

        chat_dt = datetime(2026, 10, 10, 15, 0, tzinfo=tz)
        st, actions = reconcile_inventory_state(self.test_dir, current_dt=chat_dt, user_tz="Europe/Brussels")
        self.assertEqual(st.last_reconciled_at, chat_dt.isoformat())
        self.assertTrue(any("consumed" in a.lower() for a in actions))
