import unittest
import os
import shutil
from meal_planner.tools.tracker import (
    init_bookkeeping_artifacts,
    record_price,
    log_meal_consumption,
    get_analytics_summary
)

class TestTracker(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_tracker_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_price_tracking_and_analytics(self):
        init_bookkeeping_artifacts(self.test_dir)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "prices.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "meal_logs.csv")))

        record_price(self.test_dir, "chicken_breast", "Colruyt", 9.50, "per_kg")
        log_meal_consumption(self.test_dir, {
            "date": "2026-10-10", "meal": "lunch", "recipe": "ga_xao_sa_ot",
            "adherence": "completed", "protein_cost_eur": 1.90, "calories": 650
        })

        summary = get_analytics_summary(self.test_dir)
        self.assertAlmostEqual(summary["total_protein_spend_eur"], 1.90)
        self.assertEqual(summary["logged_meals_count"], 1)
