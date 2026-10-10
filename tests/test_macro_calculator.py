import unittest
from meal_planner.tools.macro_calculator import calculate_daily_targets, solve_protein_raw_weight, MacroTargets

class TestMacroCalculator(unittest.TestCase):
    def test_calculate_daily_targets_standard(self):
        # 65 kg, 2.3g/kg protein (= 149.5g), 1.0g/kg fat (= 65g), 2550 kcal target
        # Protein kcal = 149.5 * 4 = 598 kcal
        # Fat kcal = 65 * 9 = 585 kcal
        # Remaining kcal = 2550 - 598 - 585 = 1367 kcal -> Carbs = 1367 / 4 = 341.75g
        targets = calculate_daily_targets(65.0, 2.3, 1.0, 2550.0)
        self.assertIsInstance(targets, MacroTargets)
        self.assertAlmostEqual(targets.protein_g, 149.5, places=1)
        self.assertAlmostEqual(targets.fat_g, 65.0, places=1)
        self.assertAlmostEqual(targets.carbs_g, 341.75, places=1)
        self.assertEqual(targets.calories, 2550.0)

    def test_review_focus_macro_deficit_warning(self):
        # Review Focus 2: Target calories too low to sustain protein + fat minimums
        with self.assertRaises(ValueError):
            calculate_daily_targets(80.0, 3.0, 1.0, 1200.0)

    def test_solve_protein_raw_weight(self):
        # Needs 45g protein from chicken breast (density 23.5g per 100g), baseline dish has 5g protein
        # Net needed = 40g -> Raw weight = (40 / 23.5) * 100 = 170.21g
        weight = solve_protein_raw_weight(45.0, 5.0, 23.5)
        self.assertAlmostEqual(weight, 170.2, places=1)
