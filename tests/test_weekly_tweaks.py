import unittest
import os
import shutil
import csv
from datetime import datetime
import zoneinfo

from meal_planner.models import UserProfile, load_catalog
from meal_planner.tools.meal_generator import (
    generate_weekly_plan,
    export_meal_plan_csv,
    export_batch_cook_csv,
    ensure_weekly_plan_artifacts,
    get_current_cycle_prefix
)
from meal_planner.tools.grocery_planner import (
    PantryState,
    generate_split_groceries,
    export_grocery_list_csv
)
from meal_planner.tools.tracker import (
    init_bookkeeping_artifacts,
    log_meal_consumption,
    get_analytics_summary
)
from meal_planner.agent import get_agent_tools

class TestWeeklyTweaks(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_tweaks_data"
        os.makedirs(self.test_dir, exist_ok=True)
        self.profile = UserProfile(
            timezone="Europe/Brussels",
            bodyweight_kg=65.0,
            goal_state="lean_bulk",
            target_calories=2550.0,
            protein_multiplier=2.3,
            fat_multiplier=1.0,
            week_start_day="Saturday",
            weeks_ahead=1
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_configurable_week_start_day(self):
        # 1. Saturday start (default)
        sat_plan = generate_weekly_plan(self.profile, start_date="2026-10-10")
        self.assertEqual(sat_plan.days[0].day_name, "Saturday")
        self.assertEqual(sat_plan.days[6].day_name, "Friday")

        # 2. Monday start
        self.profile.week_start_day = "Monday"
        mon_plan = generate_weekly_plan(self.profile, start_date="2026-10-12")
        self.assertEqual(mon_plan.days[0].day_name, "Monday")
        self.assertEqual(mon_plan.days[6].day_name, "Sunday")

        # Cycle prefix calculation with Monday
        ref = datetime(2026, 10, 15, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        prefix_mon = get_current_cycle_prefix("Europe/Brussels", reference_dt=ref, week_start_day="Monday")
        # Thursday 2026-10-15 -> Monday of that week was 2026-10-12 -> YYMMDD is "261012"
        self.assertEqual(prefix_mon, "261012")

    def test_weeks_ahead_and_retention_window_pruning(self):
        ref = datetime(2026, 10, 15, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        plans_dir = os.path.join(self.test_dir, "plans")
        os.makedirs(plans_dir, exist_ok=True)

        # Plant an obsolete file from past cycle (e.g. 260901)
        obsolete_file = os.path.join(plans_dir, "260901_meal_plan.csv")
        with open(obsolete_file, "w") as f:
            f.write("dummy")
        self.assertTrue(os.path.exists(obsolete_file))

        # Ensure weekly artifacts with weeks_ahead=1
        self.profile.weeks_ahead = 1
        ensure_weekly_plan_artifacts(self.profile, self.test_dir, reference_dt=ref)

        # Obsolete file must be pruned!
        self.assertFalse(os.path.exists(obsolete_file))

        # Current week (261010) and next week (261017) must exist
        cur_plan = os.path.join(plans_dir, "261010_meal_plan.csv")
        next_plan = os.path.join(plans_dir, "261017_meal_plan.csv")
        cur_batch = os.path.join(plans_dir, "261010_batch_cook.csv")
        next_batch = os.path.join(plans_dir, "261017_batch_cook.csv")
        cur_grocery = os.path.join(plans_dir, "261010_grocery_list.csv")
        next_grocery = os.path.join(plans_dir, "261017_grocery_list.csv")

        self.assertTrue(os.path.exists(cur_plan))
        self.assertTrue(os.path.exists(next_plan))
        self.assertTrue(os.path.exists(cur_batch))
        self.assertTrue(os.path.exists(next_batch))
        self.assertTrue(os.path.exists(cur_grocery))
        self.assertTrue(os.path.exists(next_grocery))

    def test_strict_weekly_plan_csv_columns_and_integer_grams(self):
        plan = generate_weekly_plan(self.profile, start_date="2026-10-10")
        csv_path = os.path.join(self.test_dir, "test_strict_plan.csv")
        export_meal_plan_csv(plan, csv_path)

        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)

        # Strictly [Date, Meal, Recipe, Ingredient, P, C, F, Calories]
        expected_fields = ["Date", "Meal", "Recipe", "Ingredient", "P", "C", "F", "Calories"]
        self.assertEqual(fieldnames, expected_fields)
        self.assertEqual(len(rows), 21)

        for row in rows:
            # Check numbers have no decimals
            self.assertTrue(row["P"].isdigit() or row["P"].lstrip("-").isdigit(), f"P has decimals: {row['P']}")
            self.assertTrue(row["C"].isdigit() or row["C"].lstrip("-").isdigit(), f"C has decimals: {row['C']}")
            self.assertTrue(row["F"].isdigit() or row["F"].lstrip("-").isdigit(), f"F has decimals: {row['F']}")
            self.assertTrue(row["Calories"].isdigit(), f"Calories has decimals: {row['Calories']}")
            # In Ingredient column, gram quantities are rounded integers
            self.assertNotIn(".0g", row["Ingredient"])
            self.assertNotIn(".1g", row["Ingredient"])

    def test_separated_batch_cook_file(self):
        plan = generate_weekly_plan(self.profile, start_date="2026-10-10")
        batch_path = os.path.join(self.test_dir, "test_batch_cook.csv")
        export_batch_cook_csv(plan, batch_path)

        self.assertTrue(os.path.exists(batch_path))
        with open(batch_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            expected_fields = ["Dish", "Main_Protein", "Meals"]
            self.assertEqual(reader.fieldnames, expected_fields)
            rows = list(reader)

        self.assertGreater(len(rows), 0)
        # Check that Thịt kho tàu is present with main protein and meal count
        thit_kho_rows = [r for r in rows if "Thịt Kho" in r["Dish"]]
        self.assertEqual(len(thit_kho_rows), 1)
        r = thit_kho_rows[0]
        self.assertIn("Pork", r["Main_Protein"])
        self.assertTrue(any(c.isdigit() for c in r["Main_Protein"]))
        self.assertEqual(r["Meals"], "3")
        self.assertNotIn("Grocery_Run", r)
        self.assertNotIn("Prep_Day", r)
        self.assertNotIn("Days_Served", r)

        # Check that Gà xào sả ớt is present with main protein and meal count
        ga_xao_rows = [r for r in rows if "Gà Xào" in r["Dish"]]
        self.assertEqual(len(ga_xao_rows), 1)
        r2 = ga_xao_rows[0]
        self.assertIn("Chicken Breast", r2["Main_Protein"])
        self.assertEqual(r2["Meals"], "2")
        self.assertNotIn("Grocery_Run", r2)
        self.assertNotIn("Prep_Day", r2)
        self.assertNotIn("Days_Served", r2)

    def test_vegetable_and_fruit_macro_tracking(self):
        plan = generate_weekly_plan(self.profile, start_date="2026-10-10")
        for day in plan.days:
            self.assertGreater(day.total_veg_g, 0, f"No veg tracked for {day.day_name}")
            self.assertGreater(day.total_fruit_g, 0, f"No fruit tracked for {day.day_name}")
            self.assertIsInstance(day.total_veg_g, int)
            self.assertIsInstance(day.total_fruit_g, int)

        # Log consumption to tracker
        init_bookkeeping_artifacts(self.test_dir)
        log_meal_consumption(self.test_dir, {
            "date": "2026-10-10",
            "meal": "lunch",
            "recipe": "Gà Xào Sả Ớt",
            "adherence": "completed",
            "protein_cost_eur": 2.50,
            "calories": 650,
            "veg_g": 80,
            "fruit_g": 0
        })
        log_meal_consumption(self.test_dir, {
            "date": "2026-10-10",
            "meal": "breakfast",
            "recipe": "ON Whey Soy Shake",
            "adherence": "completed",
            "protein_cost_eur": 1.50,
            "calories": 400,
            "veg_g": 0,
            "fruit_g": 50
        })

        summary = get_analytics_summary(self.test_dir)
        self.assertEqual(summary["total_veg_g"], 80)
        self.assertEqual(summary["total_fruit_g"], 50)
        self.assertEqual(summary["average_veg_g_per_logged_meal"], 40.0)
        self.assertEqual(summary["average_fruit_g_per_logged_meal"], 25.0)

    def test_grocery_run_column_date_only(self):
        plan = generate_weekly_plan(self.profile, start_date="2026-10-10")
        pantry = PantryState(items={"jasmine_rice": 5000.0, "on_whey": 200.0})
        groceries = generate_split_groceries(plan, pantry)

        csv_path = os.path.join(self.test_dir, "test_grocery_dates.csv")
        export_grocery_list_csv(groceries, csv_path)

        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertGreater(len(rows), 0)
        valid_runs = ["Saturday", "Wednesday", "Pantry"]
        for r in rows:
            self.assertIn(r["Run"], valid_runs, f"Run column contains unexpected value: {r['Run']}")
            # Ensure no decimals in package size or planned grams
            self.assertNotIn(".0g", r["Package_Size"])
            self.assertNotIn(".1g", r["Quantity"])

        # Verify strict grouping by [Run, Category]
        # Categories within each run must be grouped together (no interleaved categories)
        seen_run_cats = []
        for r in rows:
            run_cat = (r["Run"], r["Category"])
            if not seen_run_cats or seen_run_cats[-1] != run_cat:
                seen_run_cats.append(run_cat)
        # Every (Run, Category) tuple must appear at most once in seen_run_cats
        self.assertEqual(len(seen_run_cats), len(set(seen_run_cats)), f"Categories not grouped by [Run, Category]: {seen_run_cats}")

    def test_tool_save_schedule_and_batch_cook(self):
        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        # Save planning schedule preference in long-term memory
        res = tools_map["tool_save_memory_note"]("Planning schedule: Week starts on Monday, planning 2 weeks ahead", "long_term")
        self.assertIn("Saved to long-term memory", res)

        # Update batch cook instructions
        update_res = tools_map["tool_update_batch_cook"]([
            {
                "Dish": "Thịt Kho Tàu",
                "Main_Protein": "1000g Pork Belly",
                "Meals": 3
            }
        ])
        self.assertIn("Successfully updated batch cook instructions", update_res)

        # View batch cook list
        batch_summary = tools_map["tool_get_batch_cook"]()
        self.assertIn("Thịt Kho Tàu", batch_summary)
        self.assertIn("1000g Pork Belly", batch_summary)
        self.assertIn("3", batch_summary)
        self.assertNotIn("Sunday", batch_summary)
        self.assertNotIn("Prep Day", batch_summary)
