import unittest
import os
import shutil
import tempfile
from datetime import datetime
import zoneinfo

from meal_planner.models import UserProfile
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts, get_current_cycle_prefix
from meal_planner.tools.inventory import load_inventory_state
from meal_planner.agent import get_agent_tools

class TestStreamlinedAgentFlow(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True,
            "week_start_day": "Saturday"
        })
        ensure_weekly_plan_artifacts(self.profile, self.test_dir)
        self.tools_list = get_agent_tools(self.test_dir)
        self.tools = {fn.__name__: fn for fn in self.tools_list}

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_record_on_hand_stock_and_update_artifacts(self):
        # 1. User reports on-hand stock: 500g wings and 500g chicken thighs
        update_stock_fn = self.tools["tool_update_on_hand_stock"]
        msg = update_stock_fn([
            {"name": "Chicken Wings", "quantity_g": 500.0},
            {"name": "Chicken Thigh Quarters", "quantity_g": 500.0}
        ])
        self.assertIn("Updated actual stock", msg)

        # Verify inventory state
        inv = load_inventory_state(self.test_dir)
        actual_items = [i for i in inv.items if i.status == "actual"]
        self.assertEqual(len(actual_items), 2)
        total_qty = sum(i.quantity_g for i in actual_items)
        self.assertEqual(total_qty, 1000.0)

        # 2. Agent checks inventory and macro targets
        get_inv_fn = self.tools["tool_get_inventory"]
        inv_str = get_inv_fn()
        self.assertIn("Chicken Wings: 500g", inv_str)
        self.assertIn("Chicken Thigh Quarters: 500g", inv_str)

        get_macros_fn = self.tools["tool_get_macro_targets"]
        macros_str = get_macros_fn()
        self.assertIn("2500 kcal", macros_str)
        self.assertIn("Rough Targets", macros_str)

        # 3. Agent updates meal plan:
        # Next meal (Saturday Lunch) -> Air Fried Chicken craving (250g wings, 250g thighs)
        # Saturday Dinner -> Chicken Soup (250g wings) to respect soft dinner texture
        # Sunday Lunch -> Remaining chicken (250g thighs)
        update_meal_plan_fn = self.tools["tool_update_meal_plan"]
        plan_update_msg = update_meal_plan_fn([
            {
                "Date": "2026-10-10",
                "Meal": "Lunch",
                "Recipe": "Air Fried Crispy Chicken",
                "Ingredient": "250g Chicken Wings; 250g Chicken Thigh Quarters; 150g Jasmine Rice",
                "P": 60,
                "C": 45,
                "F": 20,
                "Calories": 600
            },
            {
                "Date": "2026-10-10",
                "Meal": "Dinner",
                "Recipe": "Comforting Chicken Soup with Rice Noodles",
                "Ingredient": "250g Chicken Wings; 100g Rice Noodles; 50g Greens",
                "P": 35,
                "C": 40,
                "F": 12,
                "Calories": 410
            },
            {
                "Date": "2026-10-11",
                "Meal": "Lunch",
                "Recipe": "Pan-Seared Thigh Quarters with Sweet Potato",
                "Ingredient": "250g Chicken Thigh Quarters; 200g Sweet Potato",
                "P": 45,
                "C": 45,
                "F": 15,
                "Calories": 495
            }
        ])
        self.assertIn("Successfully updated", plan_update_msg)

        # Verify meal plan artifact is updated
        get_plan_fn = self.tools["tool_get_meal_plan"]
        sat_plan = get_plan_fn(target_date="2026-10-10")
        self.assertIn("Air Fried Crispy Chicken", sat_plan)
        self.assertIn("Comforting Chicken Soup", sat_plan)

        # 4. Agent dynamically shifts grocery run to D_exhaust (Sunday evening / Monday)
        update_grocery_fn = self.tools["tool_update_grocery_list"]
        grocery_msg = update_grocery_fn([
            {"Run": "2026-10-12 Dynamic Run", "Category": "meat", "Item": "Ground Beef (5% Fat)", "Quantity_g": 1000, "Estimated_Price_EUR": 11.50},
            {"Run": "2026-10-12 Dynamic Run", "Category": "vegetable", "Item": "Broccoli", "Quantity_g": 500, "Estimated_Price_EUR": 2.00}
        ], mode="replace")
        self.assertIn("Successfully updated grocery list", grocery_msg)

        get_grocery_fn = self.tools["tool_get_grocery_list"]
        grocery_str = get_grocery_fn()
        self.assertIn("2026-10-12 Dynamic Run", grocery_str)
        self.assertIn("Ground Beef", grocery_str)

    def test_retrospective_skipped_meal_and_eating_out_workflow(self):
        # 1. User reports skipping breakfast
        report_dev_fn = self.tools["tool_report_past_meal_deviation"]
        res_skip = report_dev_fn("2026-10-10", "breakfast", "skipped")
        self.assertIn("skipped", res_skip.lower())

        # Verify stock was restored in inventory and carried deficit exists
        inv = load_inventory_state(self.test_dir)
        self.assertGreater(inv.carried_calories, 0)
        self.assertTrue(any(i.quantity_g > 0 for i in inv.items))

        # 2. User reports eating out for lunch
        res_eatout = report_dev_fn(
            "2026-10-10", "lunch", "eat_out",
            actual_calories=850.0, actual_protein_g=45.0,
            notes="Vietnamese Pho Ga restaurant"
        )
        self.assertIn("eat_out", res_eatout.lower())

        # Verify catch-up does not deduct the home stock for skipped or eaten-out slots
        catch_up_fn = self.tools["tool_catch_up_inventory"]
        catch_up_msg = catch_up_fn()
        self.assertTrue(len(catch_up_msg) > 0)

        # Food items still in inventory
        inv2 = load_inventory_state(self.test_dir)
        self.assertTrue(any(i.quantity_g > 0 for i in inv2.items))
