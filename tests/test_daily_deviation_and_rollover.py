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


if __name__ == "__main__":
    unittest.main()
