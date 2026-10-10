import unittest
from meal_planner.models import load_catalog, Ingredient, Recipe

class TestCatalog(unittest.TestCase):
    def test_catalog_loads_ingredients_and_recipes(self):
        ingredients, recipes = load_catalog()
        self.assertIn("chicken_breast", ingredients)
        self.assertIn("pho_beef", recipes)
        
        # Check raw nutrient density
        chicken = ingredients["chicken_breast"]
        self.assertIsInstance(chicken, Ingredient)
        self.assertGreater(chicken.protein_per_100g, 20.0)
        self.assertTrue(chicken.perishable)

        # Check recipe texture rules
        pho = recipes["pho_beef"]
        self.assertIsInstance(pho, Recipe)
        self.assertEqual(pho.texture, "broth")
        self.assertEqual(pho.meal_type, "dinner")
