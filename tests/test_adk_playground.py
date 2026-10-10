import unittest
import os
import shutil
import yaml
from meal_planner.agent import root_agent, get_root_agent, build_system_instruction, get_agent_tools
from meal_planner.tools.memory import MemoryManager
from meal_planner.tools.onboarding import init_user_profile

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
        self.assertIn("tool_save_memory_note", tool_names)
        self.assertIn("tool_onboard_user", tool_names)
        self.assertIn("tool_generate_meal_plan", tool_names)
        self.assertIn("tool_report_meal_deviation", tool_names)
        self.assertIn("tool_substitute_ingredient", tool_names)
        self.assertIn("tool_log_price_update", tool_names)
        self.assertIn("tool_get_analytics", tool_names)
        self.assertIn("tool_view_grocery_list", tool_names)

    def test_relevant_startup_hydration_only(self):
        # Setup test data directory with profile, weekly memory, and a pantry file
        mgr = MemoryManager(self.test_dir)
        mgr.add_note("Light back training this Friday", tier="weekly")
        init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 65.0,
            "goal_state": "lean_bulk",
            "target_calories": 2550.0,
            "protein_multiplier": 2.3,
            "fat_multiplier": 1.0
        })
        # Create an unrelated pantry.json and prices.csv
        with open(os.path.join(self.test_dir, "pantry.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.test_dir, "prices.csv"), "w") as f:
            f.write("test")

        records, total_ms = mgr.hydrate(user_timezone="Europe/Brussels")
        loaded_labels = [r[0] for r in records]
        loaded_paths = [r[1] for r in records]

        # Only relevant files should be loaded
        self.assertIn("Athlete Preferences", loaded_labels)
        self.assertIn("Active Weekly Memory", loaded_labels)
        # Unrelated pantry or price files must NOT be in loaded targets
        self.assertFalse(any("pantry.json" in p for p in loaded_paths))
        self.assertFalse(any("prices.csv" in p for p in loaded_paths))

    def test_multimodal_instructions_in_prompt(self):
        init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 65.0,
            "goal_state": "lean_bulk",
            "target_calories": 2550.0,
            "protein_multiplier": 2.3,
            "fat_multiplier": 1.0
        })
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        # Check athlete preferences injection
        self.assertIn("ATHLETE PREFERENCES", prompt)
        self.assertIn("65.0 kg", prompt)
        self.assertIn("2550 kcal", prompt)

        # Check multimodal bill/receipt and meal photo instructions
        self.assertIn("GROCERY BILLS / RECEIPT PHOTOS", prompt)
        self.assertIn("MEAL CONSUMPTION PHOTOS", prompt)
        self.assertIn("tool_log_price_update", prompt)
        self.assertIn("tool_report_meal_deviation", prompt)

    def test_agents_cli_manifest_validity(self):
        manifest_path = "agents-cli-manifest.yaml"
        self.assertTrue(os.path.exists(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
        self.assertEqual(manifest.get("agent_directory"), "meal_planner")
        self.assertEqual(manifest.get("framework"), "google-adk")
        self.assertEqual(manifest.get("language"), "python")
