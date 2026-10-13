import os
import shutil
import tempfile
import unittest

from meal_planner.tools.memory import MemoryManager


class TestMemoryDailyDeviationAndRollover(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mgr = MemoryManager(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_record_daily_deviation_substantial_calorie_deficit(self):
        # Target 2500 kcal, planned 2000 kcal (-500 kcal, -20% >= 15% threshold)
        res = self.mgr.record_daily_deviation(
            date="2026-10-10",
            planned_cal=2000.0,
            target_cal=2500.0,
            planned_p=150.0,
            target_p=150.0,
        )
        self.assertEqual(res["status"], "recorded")
        self.assertTrue(res["deviating"])
        self.assertEqual(res["cal_diff"], -500)
        self.assertEqual(res["p_diff"], 0)

        # Verify weekly.md content
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1)
        self.assertIn("[2026-10-10] Daily deviation:", notes[0])
        self.assertIn("-500 kcal", notes[0])

    def test_record_daily_deviation_substantial_protein_surplus(self):
        # Target 150g P, planned 175g P (+25g, +16.7% >= 10% threshold)
        res = self.mgr.record_daily_deviation(
            date="2026-10-11",
            planned_cal=2500.0,
            target_cal=2500.0,
            planned_p=175.0,
            target_p=150.0,
        )
        self.assertEqual(res["status"], "recorded")
        self.assertTrue(res["deviating"])
        self.assertEqual(res["p_diff"], 25)

        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1)
        self.assertIn("[2026-10-11] Daily deviation:", notes[0])
        self.assertIn("+25g P", notes[0])

    def test_record_daily_deviation_boundary_sub_threshold(self):
        # Target 2500 kcal, 150g P.
        # Calorie diff: 14.9% -> 2500 * (1 - 0.149) = 2127.5 kcal.
        # Protein diff: 9.9% -> 150 * (1 - 0.099) = 135.15g P.
        res = self.mgr.record_daily_deviation(
            date="2026-10-12",
            planned_cal=2128.0,  # 14.88% diff (< 15%)
            target_cal=2500.0,
            planned_p=136.0,   # 9.33% diff (< 10%)
            target_p=150.0,
        )
        self.assertFalse(res["deviating"])
        self.assertEqual(res["status"], "cleared")
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 0, "Sub-threshold deviations (<15% cal and <10% P) must not trigger records")

    def test_record_daily_deviation_idempotence(self):
        # Record once
        self.mgr.record_daily_deviation(
            date="2026-10-10",
            planned_cal=2000.0,
            target_cal=2500.0,
            planned_p=150.0,
            target_p=150.0,
        )
        # Record again with adjusted numbers for the SAME date
        self.mgr.record_daily_deviation(
            date="2026-10-10",
            planned_cal=2100.0,
            target_cal=2500.0,
            planned_p=160.0,
            target_p=150.0,
        )

        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1, "Must have exactly 1 record for 2026-10-10, no duplicates")
        self.assertIn("-400 kcal", notes[0])
        self.assertIn("+10g P", notes[0])

    def test_record_daily_deviation_clears_when_resolved(self):
        # First record a deviation
        self.mgr.record_daily_deviation(
            date="2026-10-10",
            planned_cal=2000.0,
            target_cal=2500.0,
            planned_p=150.0,
            target_p=150.0,
        )
        self.assertEqual(len(self.mgr.get_context()["weekly"]), 1)

        # Now update with values within tolerance (e.g. 2480 kcal [-0.8%], 152g P [+1.3%])
        res = self.mgr.record_daily_deviation(
            date="2026-10-10",
            planned_cal=2480.0,
            target_cal=2500.0,
            planned_p=152.0,
            target_p=150.0,
        )
        self.assertFalse(res["deviating"])
        self.assertEqual(res["status"], "cleared")
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 0, "Obsolete deviation note must be removed once within tolerance")

    def test_rollover_weekly_memory_substantial(self):
        # Old weekly notes present
        self.mgr.add_note("Ate protein shake on Tuesday", tier="weekly")
        self.mgr.add_note("[2026-10-10] Daily deviation: -500 kcal, +0g P", tier="weekly")
        self.assertEqual(len(self.mgr.get_context()["weekly"]), 2)

        # Rollover with substantial deficit: -500 kcal on 2500 target (20% >= 15%)
        res = self.mgr.rollover_weekly_memory(
            net_cal=-500.0,
            net_p=20.0,
            daily_cal_target=2500.0,
            daily_p_target=150.0,
        )
        self.assertTrue(res["carried"])
        self.assertIn("Carried", res["note"])

        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1)
        self.assertIn("[Carried from last week] Net weekly deviation: -500 kcal, +20P carried forward.", notes[0])

    def test_rollover_weekly_memory_not_substantial(self):
        self.mgr.add_note("Ate lunch at 1pm", tier="weekly")

        # Rollover with minor diff: -100 kcal (4% < 15%) and +5g P (3.3% < 10%)
        res = self.mgr.rollover_weekly_memory(
            net_cal=-100.0,
            net_p=5.0,
            daily_cal_target=2500.0,
            daily_p_target=150.0,
        )
        self.assertFalse(res["carried"])
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 0, "Non-substantial deviation should not be carried forward")


class TestCheckMealPlanDailyDeviation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mgr = MemoryManager(self.test_dir)
        # Add athlete profile in long-term memory: 2500 kcal, 150g protein
        self.mgr.add_note("Target calories: 2500 kcal", tier="long_term")
        self.mgr.add_note("Target protein: 150g", tier="long_term")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_sample_plan(self, dates_and_totals: list[dict]):
        from meal_planner.tools.artifacts import update_meal_plan_csv
        updates = []
        for d in dates_and_totals:
            dt = d["Date"]
            cal = d.get("Calories", 2500)
            p = d.get("P", 150)
            updates.append({
                "Date": dt,
                "Meal": "Lunch",
                "Recipe": "Chicken and Rice",
                "Ingredient": "Chicken",
                "P": p,
                "C": 200,
                "F": 50,
                "Calories": cal,
            })
        update_meal_plan_csv(self.test_dir, updates)

    def test_check_meal_plan_records_daily_deviation_and_idempotent(self):
        from meal_planner.tools.artifacts import check_meal_plan_csv
        # 3-day plan: day 1 has -1000 kcal deficit (-40%) and -60g P deficit (-40%)
        days = [
            {"Date": "2026-10-10", "Calories": 1500, "P": 90},
            {"Date": "2026-10-11", "Calories": 2500, "P": 150},
            {"Date": "2026-10-12", "Calories": 2500, "P": 150},
        ]
        self._create_sample_plan(days)

        # Run check
        res = check_meal_plan_csv(self.test_dir)
        self.assertIn("daily_deviations", res)
        self.assertEqual(len(res["daily_deviations"]), 1)
        self.assertEqual(res["daily_deviations"][0]["date"], "2026-10-10")

        # Check weekly.md has exactly 1 note for 2026-10-10
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1)
        self.assertIn("[2026-10-10] Daily deviation:", notes[0])
        self.assertIn("-1000 kcal", notes[0])
        self.assertIn("-60g P", notes[0])

        # Run check AGAIN (idempotency check)
        check_meal_plan_csv(self.test_dir)
        notes_again = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes_again), 1, "Idempotence failed: duplicate lines created")

        # Now fix the deviating day
        days[0] = {"Date": "2026-10-10", "Calories": 2480, "P": 152}
        self._create_sample_plan(days)
        res_fixed = check_meal_plan_csv(self.test_dir)
        self.assertEqual(len(res_fixed["daily_deviations"]), 0)

        # Deviation note must be cleared from weekly.md
        notes_cleared = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes_cleared), 0, "Obsolete deviation note was not removed")

    def test_check_meal_plan_clears_notes_for_removed_dates(self):
        from meal_planner.tools.artifacts import check_meal_plan_csv, update_meal_plan_csv
        # Plan for 2026-10-10 that deviates
        self._create_sample_plan([{"Date": "2026-10-10", "Calories": 1500, "P": 90}])
        check_meal_plan_csv(self.test_dir)
        self.assertEqual(len(self.mgr.get_context()["weekly"]), 1)

        # Now replace plan with different dates completely (e.g. 2026-10-15 only)
        import os, shutil
        shutil.rmtree(os.path.join(self.test_dir, "plans"), ignore_errors=True)
        root_csv = os.path.join(self.test_dir, "meal_plan.csv")
        if os.path.exists(root_csv):
            os.remove(root_csv)
        self._create_sample_plan([{"Date": "2026-10-15", "Calories": 2500, "P": 150}])
        check_meal_plan_csv(self.test_dir)

        # The 2026-10-10 note should be pruned since 2026-10-10 is no longer in the plan
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 0)


class TestStartDateChangeAndWeekRollover(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mgr = MemoryManager(self.test_dir)
        self.mgr.add_note("Target calories: 2500 kcal", tier="long_term")
        self.mgr.add_note("Target protein: 150g", tier="long_term")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_update_meal_plan_start_date_change_substantial_rollover(self):
        from meal_planner.tools.artifacts import update_meal_plan_csv, check_meal_plan_csv

        # Plan 1: 2026-10-10 to 2026-10-16 (7 days).
        # Daily: 2000 kcal (-500 kcal, -20%), 120g P (-30g, -20%).
        # Weekly: planned 14000 kcal vs 17500 target (net -3500 kcal), 840g P vs 1050 target (net -210g P).
        plan1 = []
        for i in range(10, 17):
            plan1.append({
                "Date": f"2026-10-{i}",
                "Meal": "Lunch",
                "Recipe": "Chicken and Rice",
                "Ingredient": "Chicken",
                "P": 120,
                "C": 200,
                "F": 50,
                "Calories": 2000,
            })
        update_meal_plan_csv(self.test_dir, plan1)

        # Plan 2 starting next week: 2026-10-17 to 2026-10-23
        plan2 = []
        for i in range(17, 24):
            plan2.append({
                "Date": f"2026-10-{i}",
                "Meal": "Lunch",
                "Recipe": "Steak and Potatoes",
                "Ingredient": "Steak",
                "P": 150,
                "C": 200,
                "F": 50,
                "Calories": 2500,
            })
        update_meal_plan_csv(self.test_dir, plan2)

        # weekly.md must have the carried deviation note from plan 1
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1)
        self.assertIn("[Carried from last week] Net weekly deviation: -3500 kcal, -210P carried forward.", notes[0])

        # check_meal_plan_csv on plan 2 must incorporate the carried deficit into the target
        res = check_meal_plan_csv(self.test_dir)
        # Base: 17500 kcal + 3500 carried = 21000 kcal target
        self.assertEqual(res["target"]["calories"], 21000.0)
        self.assertEqual(res["target"]["P"], 1260.0)

    def test_update_meal_plan_start_date_change_not_substantial_no_rollover(self):
        from meal_planner.tools.artifacts import update_meal_plan_csv

        # Plan 1: 2026-10-10 to 2026-10-16.
        # Planned: 2450 kcal (-50 kcal/day, -2% < 15%), 148g P (-2g/day, -1.3% < 10%).
        plan1 = []
        for i in range(10, 17):
            plan1.append({
                "Date": f"2026-10-{i}",
                "Meal": "Lunch",
                "Recipe": "Chicken and Rice",
                "Ingredient": "Chicken",
                "P": 148,
                "C": 200,
                "F": 50,
                "Calories": 2450,
            })
        update_meal_plan_csv(self.test_dir, plan1)

        # Plan 2 starting 2026-10-17
        plan2 = [{
            "Date": "2026-10-17",
            "Meal": "Lunch",
            "Recipe": "Fish",
            "Ingredient": "Fish",
            "P": 150,
            "C": 200,
            "F": 50,
            "Calories": 2500,
        }]
        update_meal_plan_csv(self.test_dir, plan2)

        # weekly.md should not carry non-substantial difference
        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 0)

    def test_check_and_apply_week_rollover_cycle_transition(self):
        from meal_planner.tools.artifacts import update_meal_plan_csv, check_and_apply_week_rollover

        # Save older cycle plan: 261010_meal_plan.csv with substantial deficit
        plan_old = [{
            "Date": "2026-10-10",
            "Meal": "Lunch",
            "Recipe": "Meal",
            "Ingredient": "Food",
            "P": 100,  # -50g P
            "C": 100,
            "F": 30,
            "Calories": 1500,  # -1000 kcal
        }]
        update_meal_plan_csv(self.test_dir, plan_old, prefix="261010")

        # Now trigger check_and_apply_week_rollover for new cycle 261017
        res = check_and_apply_week_rollover(self.test_dir, current_prefix="261017")
        self.assertTrue(res["rolled_over"])
        self.assertTrue(res["carried"])

        notes = self.mgr.get_context()["weekly"]
        self.assertEqual(len(notes), 1)
        self.assertIn("[Carried from last week] Net weekly deviation: -1000 kcal, -50P carried forward.", notes[0])


if __name__ == "__main__":
    unittest.main()
