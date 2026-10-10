import unittest
import os
import shutil
from meal_planner.models import load_catalog, Ingredient, add_ingredient_to_catalog
from meal_planner.agent import get_agent_tools, build_system_instruction

class TestAddFoods(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_add_foods_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_add_food_to_catalog(self):
        # Directly test models catalog addition
        new_ing = Ingredient(
            id="colruyt_skim_skyr",
            name="Colruyt Skim Skyr",
            category="dairy",
            protein_per_100g=11.0,
            fat_per_100g=0.2,
            carbs_per_100g=4.0,
            calories_per_100g=62.0,
            package_size_g=500.0,
            unit_price_eur=1.89,
            perishable=True
        )
        add_ingredient_to_catalog(new_ing, data_dir=self.test_dir)

        # Check that load_catalog includes the new food
        ingredients, _ = load_catalog(data_dir=self.test_dir)
        self.assertIn("colruyt_skim_skyr", ingredients)
        skyr = ingredients["colruyt_skim_skyr"]
        self.assertEqual(skyr.name, "Colruyt Skim Skyr")
        self.assertEqual(skyr.protein_per_100g, 11.0)
        self.assertEqual(skyr.package_size_g, 500.0)
        self.assertEqual(skyr.unit_price_eur, 1.89)

    def test_new_food_preference_saved_to_long_term_memory(self):
        tools_map = {t.__name__: t for t in get_agent_tools(data_dir=self.test_dir)}
        # Agent saves new food or brand preferences in long-term memory
        res = tools_map["tool_save_memory_note"]("User regularly buys Colruyt Skim Skyr for breakfast protein", "long_term")
        self.assertIn("Saved to long-term memory", res)

    def test_system_instruction_mandates_no_rigid_nutrition_or_price_bookkeeping(self):
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("NO RIGID LOCAL NUTRITION OR PRICE BOOKKEEPING", prompt)
        self.assertIn("LLM estimation and web-browsing capabilities handle pricing context and nutritional facts naturally", prompt)
        self.assertIn("Qualitative eating preferences", prompt)


if __name__ == "__main__":
    unittest.main()
