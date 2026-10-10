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
        self.assertEqual(ctx["weekly"][0], "Feeling lower back fatigue this week, keep Friday dinner light")
        self.assertEqual(ctx["long_term"][0], "Severe intolerance to dairy whey, only ON Whey tolerated")

        # Verify storage format is Markdown (.md) and contains no timestamps
        weekly_file = os.path.join(self.test_dir, "memory", "weekly.md")
        long_term_file = os.path.join(self.test_dir, "memory", "long_term.md")
        self.assertTrue(os.path.exists(weekly_file))
        self.assertTrue(os.path.exists(long_term_file))

        with open(weekly_file, "r", encoding="utf-8") as f:
            weekly_content = f.read()
        self.assertTrue(weekly_content.startswith("- "))
        self.assertNotIn("timestamp", weekly_content.lower())
        self.assertNotIn("{", weekly_content)

        with open(long_term_file, "r", encoding="utf-8") as f:
            long_term_content = f.read()
        self.assertTrue(long_term_content.startswith("- "))
        self.assertNotIn("timestamp", long_term_content.lower())
        self.assertNotIn("{", long_term_content)

    def test_startup_hydration_benchmarking(self):
        mgr = MemoryManager(self.test_dir)
        mgr.add_note("Tendon stiffness this week", tier="weekly")
        
        records, total_ms = mgr.hydrate()
        self.assertGreater(len(records), 0)
        self.assertGreaterEqual(total_ms, 0.0)
        file_paths = [r[1] for r in records]
        self.assertTrue(any("weekly.md" in fp for fp in file_paths))
