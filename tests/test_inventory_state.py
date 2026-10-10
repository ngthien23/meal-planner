import unittest
import os
import shutil
import tempfile
from meal_planner.models import InventoryItem as ModelInventoryItem, InventoryState as ModelInventoryState
from meal_planner.tools.inventory import (
    InventoryState,
    InventoryItem,
    load_inventory_state,
    save_inventory_state,
    record_actual_stock,
)

class TestInventoryState(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_models_exported_correctly(self):
        self.assertIs(InventoryItem, ModelInventoryItem)
        self.assertIs(InventoryState, ModelInventoryState)

    def test_load_nonexistent_inventory_returns_default_empty_state(self):
        state = load_inventory_state(self.test_dir)
        self.assertIsNone(state.last_reconciled_at)
        self.assertEqual(state.carried_calories, 0.0)
        self.assertEqual(state.carried_protein_g, 0.0)
        self.assertEqual(state.items, [])

    def test_save_and_load_inventory(self):
        state = InventoryState(
            last_reconciled_at="2026-10-10T18:00:00+02:00",
            carried_calories=150.0,
            carried_protein_g=12.0,
            items=[InventoryItem("chicken_wings", "Chicken Wings", 500.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)
        loaded = load_inventory_state(self.test_dir)
        self.assertEqual(loaded.last_reconciled_at, "2026-10-10T18:00:00+02:00")
        self.assertEqual(loaded.carried_calories, 150.0)
        self.assertEqual(loaded.carried_protein_g, 12.0)
        self.assertEqual(len(loaded.items), 1)
        self.assertEqual(loaded.items[0].food_id, "chicken_wings")
        self.assertEqual(loaded.items[0].name, "Chicken Wings")
        self.assertEqual(loaded.items[0].quantity_g, 500.0)
        self.assertEqual(loaded.items[0].status, "actual")
        self.assertEqual(loaded.items[0].source, "user_report")
        self.assertEqual(loaded.items[0].purchased_date, "2026-10-10")

    def test_record_actual_stock_overwrites_matching_and_sets_actual(self):
        state = record_actual_stock(self.test_dir, [
            {"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 500.0},
            {"food_id": "chicken_thigh_quarter", "name": "Chicken Thigh Quarter", "quantity_g": 500.0}
        ])
        self.assertEqual(len(state.items), 2)
        self.assertTrue(all(item.status == "actual" for item in state.items))
        self.assertTrue(all(item.source == "user_report" for item in state.items))

        # Overwrite chicken_wings quantity and append a third item
        updated = record_actual_stock(self.test_dir, [
            {"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 350.0},
            {"food_id": "eggs", "name": "Whole Eggs", "quantity_g": 300.0}
        ])
        self.assertEqual(len(updated.items), 3)
        wings_item = next(item for item in updated.items if item.food_id == "chicken_wings")
        self.assertEqual(wings_item.quantity_g, 350.0)
        self.assertEqual(wings_item.status, "actual")

        # Verify persisted state matches
        loaded = load_inventory_state(self.test_dir)
        self.assertEqual(len(loaded.items), 3)

    def test_record_actual_stock_clears_unbought_run_meats(self):
        # Initial state with an assumed perishable meat and an actual item
        initial_state = InventoryState(
            last_reconciled_at="2026-10-10T12:00:00+02:00",
            carried_calories=0.0,
            carried_protein_g=0.0,
            items=[
                InventoryItem("chicken_breast", "Chicken Breast Fillet", 1000.0, "assumed", "planned_run", "2026-10-10"),
                InventoryItem("rolled_oats", "Rolled Oats", 500.0, "actual", "user_report", "2026-10-09"),
            ]
        )
        save_inventory_state(self.test_dir, initial_state)

        # Record actual stock of chicken wings with clear_unbought_run_meats=True
        state = record_actual_stock(
            self.test_dir,
            [{"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 500.0}],
            clear_unbought_run_meats=True
        )

        item_ids = [item.food_id for item in state.items]
        # Assumed perishable chicken_breast should be removed
        self.assertNotIn("chicken_breast", item_ids)
        # Actual rolled oats should remain
        self.assertIn("rolled_oats", item_ids)
        # Actual chicken wings should be present
        self.assertIn("chicken_wings", item_ids)
