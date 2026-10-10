import unittest
from datetime import datetime
import zoneinfo
from meal_planner.models import UserProfile, load_catalog
from meal_planner.tools.meal_generator import generate_weekly_plan, export_meal_plan_csv
from meal_planner.tools.grocery_planner import PantryState, generate_split_groceries
from meal_planner.tools.adaptation import apply_meal_deviation, apply_grocery_substitution
from meal_planner.tools.onboarding import get_relative_datetime, resolve_timezone

class TestCodeReviewFixes(unittest.TestCase):
    def setUp(self):
        self.profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )

    def test_substitution_respects_baseline_protein_and_updates_macros(self):
        plan = generate_weekly_plan(self.profile)
        # Monday lunch has Thịt kho tàu (pork + eggs + rice)
        mon_lunch_before = next(d for d in plan.days if d.day_name == "Monday").lunch
        target_p = mon_lunch_before.protein_g
        fat_before = mon_lunch_before.fat_g

        # Substitute pork shoulder with chicken breast
        updated = apply_grocery_substitution(plan, "pork_shoulder", "chicken_breast", 9.50)
        mon_lunch_after = next(d for d in updated.days if d.day_name == "Monday").lunch

        # Total protein should stay accurate to target, NOT inflated +41%
        self.assertAlmostEqual(mon_lunch_after.protein_g, target_p, delta=3.0)
        # Fat should be lower because chicken breast has far less fat than pork shoulder
        self.assertLess(mon_lunch_after.fat_g, fat_before)
        # Day total protein and calories should be updated
        mon_day = next(d for d in updated.days if d.day_name == "Monday")
        self.assertEqual(mon_day.total_protein_g, round(mon_day.breakfast.protein_g + mon_lunch_after.protein_g + mon_day.dinner.protein_g, 1))

    def test_wednesday_lunch_included_in_saturday_grocery_run(self):
        plan = generate_weekly_plan(self.profile)
        pantry = PantryState(items={"jasmine_rice": 5000.0, "on_whey": 2000.0, "cooking_oil": 800.0})
        groceries = generate_split_groceries(plan, pantry)

        # Pork shoulder is for Mon, Tue, Wed lunches (3 x ~158g = ~475g).
        # Since Sunday evening batch cooks all 3 lunches, all pork shoulder must be in Saturday Run!
        sat_pork = [item for item in groceries.saturday_run if item["id"] == "pork_shoulder"]
        wed_pork = [item for item in groceries.wednesday_run if item["id"] == "pork_shoulder"]
        self.assertEqual(len(sat_pork), 1)
        self.assertGreaterEqual(sat_pork[0]["needed_g"], 400.0) # covers all 3 batch lunches
        self.assertEqual(len(wed_pork), 0) # none in Wednesday run

    def test_frozen_shrimp_single_package_in_saturday_run(self):
        plan = generate_weekly_plan(self.profile)
        pantry = PantryState(items={"jasmine_rice": 5000.0, "on_whey": 2000.0, "cooking_oil": 800.0})
        groceries = generate_split_groceries(plan, pantry)

        # 1kg frozen shrimp bag should NOT be duplicated into two 1kg bags
        shrimp_sat = [item for item in groceries.saturday_run if item["id"] == "frozen_shrimp"]
        shrimp_wed = [item for item in groceries.wednesday_run if item["id"] == "frozen_shrimp"]
        self.assertEqual(len(shrimp_sat), 1)
        self.assertEqual(shrimp_sat[0]["packages"], 1) # exactly one 1kg bag
        self.assertEqual(len(shrimp_wed), 0) # zero in wednesday run

    def test_relative_datetime_prioritizes_dinner_over_shake(self):
        ref = datetime(2026, 10, 15, 14, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        # Phrase containing both "shake" and "dinner"
        dt, meal = get_relative_datetime("I drank a double shake instead of Thursday dinner", "Europe/Brussels", reference_dt=ref)
        self.assertEqual(meal, "dinner")

    def test_prep_type_stored_on_meal_slot(self):
        plan = generate_weekly_plan(self.profile)
        mon_lunch = next(d for d in plan.days if d.day_name == "Monday").lunch
        self.assertEqual(mon_lunch.prep_type, "batch_reheatable")

    def test_all_pantry_items_evaluated_for_restock(self):
        plan = generate_weekly_plan(self.profile)
        # Pantry with cooking oil low (50g, threshold 200g)
        pantry = PantryState(items={"cooking_oil": 50.0})
        groceries = generate_split_groceries(plan, pantry)
        restock_ids = [item["id"] for item in groceries.pantry_restock]
        self.assertIn("cooking_oil", restock_ids)
