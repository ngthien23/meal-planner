import unittest
import os
import shutil
from meal_planner.tools.memory import MemoryManager, add_memory_note, get_memory_context

class TestMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_memory_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_memory_discrimination_and_storage(self):
        mgr = MemoryManager(self.test_dir)

        # Review Focus 1: Trivial chatter must be ignored
        res_trivial = mgr.add_note("Okay sounds good thanks!", tier="weekly")
        self.assertEqual(res_trivial["status"], "ignored")

        # Meaningful weekly note
        res_weekly = mgr.add_note("Feeling lower back fatigue this week, keep Friday dinner light", tier="weekly")
        self.assertEqual(res_weekly["status"], "saved")
        self.assertEqual(res_weekly["tier"], "weekly")

        # Meaningful long-term note
        res_long = mgr.add_note("Severe intolerance to dairy whey, only ON Whey tolerated", tier="long_term")
        self.assertEqual(res_long["status"], "saved")
        self.assertEqual(res_long["tier"], "long_term")

        # Check retrieval context
        ctx = mgr.get_context()
        self.assertEqual(len(ctx["weekly"]), 1)
        self.assertEqual(len(ctx["long_term"]), 1)

    def test_startup_hydration_benchmarking(self):
        mgr = MemoryManager(self.test_dir)
        mgr.add_note("Tendon stiffness this week", tier="weekly")
        
        records, total_ms = mgr.hydrate()
        self.assertGreater(len(records), 0)
        self.assertGreaterEqual(total_ms, 0.0)
        file_paths = [r[1] for r in records]
        self.assertTrue(any("weekly.json" in fp for fp in file_paths))
