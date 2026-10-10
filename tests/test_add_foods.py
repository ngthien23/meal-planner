import unittest
import os
import shutil
import csv
from meal_planner.models import load_catalog, Ingredient, UserProfile
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.tracker import init_bookkeeping_artifacts

class TestAddFoods(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_add_foods_data"
        os.makedirs(self.test_dir, exist_ok=True)
        init_bookkeeping_artifacts(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_add_food_tool_persists_catalog_and_price(self):
        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        self.assertIn("tool_add_food_item", tools_map)

        res = tools_map["tool_add_food_item"](
            name="Colruyt Skim Skyr",
            category="dairy",
            protein_per_100g=11.0,
            fat_per_100g=0.2,
            carbs_per_100g=4.0,
            package_size_g=500.0,
            unit_price_eur=1.89,
            perishable=True,
            unit_type="per_tub",
            store="Colruyt"
        )
        self.assertIn("Added 'Colruyt Skim Skyr'", res)
        self.assertIn("colruyt_skim_skyr", res)

        # Check that load_catalog includes the new food
        ingredients, _ = load_catalog(data_dir=self.test_dir)
        self.assertIn("colruyt_skim_skyr", ingredients)
        skyr = ingredients["colruyt_skim_skyr"]
        self.assertEqual(skyr.name, "Colruyt Skim Skyr")
        self.assertEqual(skyr.protein_per_100g, 11.0)
        self.assertEqual(skyr.package_size_g, 500.0)
        self.assertEqual(skyr.unit_price_eur, 1.89)

        # Check prices.csv recorded the entry
        prices_csv = os.path.join(self.test_dir, "prices.csv")
        self.assertTrue(os.path.exists(prices_csv))
        with open(prices_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        skyr_price_rows = [r for r in rows if r["Item_ID"] == "colruyt_skim_skyr"]
        self.assertEqual(len(skyr_price_rows), 1)
        self.assertEqual(skyr_price_rows[0]["Store"], "Colruyt")
        self.assertEqual(skyr_price_rows[0]["Unit_Price_EUR"], "1.89")

    def test_new_food_usable_in_substitutions(self):
        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        # Onboard user and generate plan
        tools_map["tool_onboard_user"]("Europe/Brussels", 65.0, "lean_bulk", 2550.0, 2.3, 1.0)
        tools_map["tool_generate_meal_plan"]()

        # Add a new protein food
        tools_map["tool_add_food_item"](
            name="Cottage Cheese Low Fat",
            category="dairy",
            protein_per_100g=12.5,
            fat_per_100g=1.5,
            carbs_per_100g=2.5,
            package_size_g=400.0,
            unit_price_eur=1.75
        )

        # Substitute chicken breast with the new cottage cheese
        sub_res = tools_map["tool_substitute_ingredient"](
            original_id="chicken_breast",
            new_ingredient_id="cottage_cheese_low_fat",
            new_price_eur=1.75
        )
        self.assertIn("Substituted chicken_breast with cottage_cheese_low_fat", sub_res)

    def test_system_instruction_mandates_confirmation_before_adding_new_foods(self):
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("NEW FOOD DETECTION & CONFIRMATION", prompt)
        self.assertIn("DO NOT add it immediately or silently", prompt)
        self.assertIn("FIRST, explicitly ask the user for confirmation", prompt)
        self.assertIn("tool_add_food_item", prompt)
