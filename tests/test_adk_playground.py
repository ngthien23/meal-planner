import unittest
import os
import shutil
import yaml
from meal_planner.agent import root_agent, get_root_agent, build_system_instruction, get_agent_tools
from meal_planner.tools.memory import MemoryManager

class TestAdkPlayground(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_adk_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_root_agent_definition(self):
        self.assertIsNotNone(root_agent)
        self.assertEqual(root_agent.name, "meal_planner")
        self.assertEqual(root_agent.model, "gemini-3.8-flash")
        tool_names = [t.__name__ for t in root_agent.tools]
        self.assertEqual(len(root_agent.tools), 3)
        self.assertIn("tool_save_memory_note", tool_names)
        self.assertIn("tool_update_plans", tool_names)
        self.assertIn("tool_check_meal_plan", tool_names)
        self.assertNotIn("tool_update_meal_plan", tool_names)
        self.assertNotIn("tool_update_grocery_list", tool_names)
        self.assertNotIn("tool_update_batch_cook", tool_names)

    def test_relevant_startup_hydration_only(self):
        # Setup test data directory with weekly memory and a long-term note
        mgr = MemoryManager(self.test_dir)
        mgr.add_note("Light back training this Friday", tier="weekly")
        mgr.add_note("Athlete bodyweight: 65.0 kg, Target calories: 2550 kcal", tier="long_term")
        # Create an unrelated pantry.json and prices.csv
        with open(os.path.join(self.test_dir, "pantry.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.test_dir, "prices.csv"), "w") as f:
            f.write("test")

        records, total_ms = mgr.hydrate(user_timezone="Europe/Brussels")
        loaded_labels = [r[0] for r in records]
        loaded_paths = [r[1] for r in records]

        # Only relevant files should be loaded
        self.assertIn("Active Weekly Memory", loaded_labels)
        self.assertIn("Durable Long-term Facts", loaded_labels)
        # Unrelated pantry or price files must NOT be in loaded targets
        self.assertFalse(any("pantry.json" in p for p in loaded_paths))
        self.assertFalse(any("prices.csv" in p for p in loaded_paths))

    def test_multimodal_instructions_in_prompt(self):
        mgr = MemoryManager(self.test_dir)
        mgr.add_note("Athlete bodyweight: 65.0 kg, Target calories: 2550 kcal, Goal: lean_bulk", tier="long_term")
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        # Check athlete memory injection
        self.assertIn("ATHLETE MEMORY", prompt)
        self.assertIn("65.0 kg", prompt)
        self.assertIn("2550 kcal", prompt)

        # Check multimodal bill/receipt and meal photo instructions
        self.assertIn("GROCERY BILLS / RECEIPT PHOTOS", prompt)
        self.assertIn("MEAL CONSUMPTION PHOTOS", prompt)
        self.assertIn("tool_save_memory_note", prompt)
        self.assertIn("tool_update_plans", prompt)

    def test_agents_cli_manifest_validity(self):
        manifest_path = "agents-cli-manifest.yaml"
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        self.assertEqual(manifest.get("agent_directory"), "meal_planner")
        self.assertEqual(manifest.get("framework"), "google-adk")
        self.assertEqual(manifest.get("language"), "python")

if __name__ == "__main__":
    unittest.main()
