import unittest
import os
import shutil
import tempfile
from datetime import datetime
import zoneinfo

from meal_planner.tools.artifacts import (
    get_current_cycle_prefix,
    update_meal_plan_csv,
    update_grocery_list_csv
)
from meal_planner.tools.memory import MemoryManager
from meal_planner.agent import get_agent_tools, build_system_instruction

class TestStreamlinedAgentFlow(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        mem = MemoryManager(self.test_dir)
        mem.add_note("Bodyweight: 70.0 kg | Goal: lean_bulk | Target Calories: 2500 kcal", tier="long_term")
        update_meal_plan_csv(self.test_dir, [
            {"Date": "2026-10-10", "Meal": "Breakfast", "Recipe": "Oatmeal", "Ingredient": "100g Oats", "P": 15, "C": 60, "F": 10, "Calories": 390},
            {"Date": "2026-10-10", "Meal": "Lunch", "Recipe": "Chicken Rice", "Ingredient": "200g Chicken; 150g Rice", "P": 50, "C": 45, "F": 15, "Calories": 515},
            {"Date": "2026-10-10", "Meal": "Dinner", "Recipe": "Beef Stew", "Ingredient": "200g Beef", "P": 45, "C": 20, "F": 20, "Calories": 440},
        ])
        update_grocery_list_csv(self.test_dir, [
            {"Run": "Saturday Run", "Category": "meat", "Item": "Chicken Breast", "Quantity_g": 1000, "Estimated_Price_EUR": 9.50},
            {"Run": "Saturday Run", "Category": "produce", "Item": "Broccoli", "Quantity_g": 500, "Estimated_Price_EUR": 2.00},
        ])
        self.tools_list = get_agent_tools(self.test_dir)
        self.tools = {fn.__name__: fn for fn in self.tools_list}

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_record_on_hand_stock_and_update_artifacts(self):
        # 1. User reports on-hand stock: 500g wings and 500g chicken thighs
        # Agent records dated stock in Short-Term Memory (weekly.md)
        save_mem_fn = self.tools["tool_save_memory_note"]
        msg = save_mem_fn("- [2026-10-10] Stock on hand: 500g Chicken Wings, 500g Chicken Thigh Quarters", tier="weekly")
        self.assertIn("Saved to weekly memory", msg)

        # Verify memory manager has recorded the note
        mem_ctx = MemoryManager(self.test_dir).get_context()
        self.assertTrue(any("Chicken Wings" in n and "500g" in n for n in mem_ctx["weekly"]))

        # 2. Agent updates meal plan:
        # Next meal (Saturday Lunch) -> Air Fried Chicken craving (250g wings, 250g thighs)
        # Saturday Dinner -> Chicken Soup (250g wings) to respect soft dinner texture
        # Sunday Lunch -> Remaining chicken (250g thighs)
        update_meal_plan_fn = self.tools["tool_update_meal_plan"]
        plan_update_msg = update_meal_plan_fn([
            {
                "Date": "2026-10-10",
                "Meal": "Lunch",
                "Recipe": "Air Fried Crispy Chicken",
                "Ingredient": "250g Chicken Wings; 250g Chicken Thigh Quarters; 150g Jasmine Rice",
                "P": 60,
                "C": 45,
                "F": 20,
                "Calories": 600
            },
            {
                "Date": "2026-10-10",
                "Meal": "Dinner",
                "Recipe": "Comforting Chicken Soup with Rice Noodles",
                "Ingredient": "250g Chicken Wings; 100g Rice Noodles; 50g Greens",
                "P": 35,
                "C": 40,
                "F": 12,
                "Calories": 410
            },
            {
                "Date": "2026-10-11",
                "Meal": "Lunch",
                "Recipe": "Pan-Seared Thigh Quarters with Sweet Potato",
                "Ingredient": "250g Chicken Thigh Quarters; 200g Sweet Potato",
                "P": 45,
                "C": 45,
                "F": 15,
                "Calories": 495
            }
        ])
        self.assertIn("Successfully updated", plan_update_msg)

        # Verify meal plan artifact is updated
        get_plan_fn = self.tools["tool_get_meal_plan"]
        sat_plan = get_plan_fn(target_date="2026-10-10")
        self.assertIn("Air Fried Crispy Chicken", sat_plan)
        self.assertIn("Comforting Chicken Soup", sat_plan)

        # 4. Agent dynamically shifts grocery run to D_exhaust (Sunday evening / Monday)
        update_grocery_fn = self.tools["tool_update_grocery_list"]
        grocery_msg = update_grocery_fn([
            {"Run": "2026-10-12 Dynamic Run", "Category": "meat", "Item": "Ground Beef (5% Fat)", "Quantity_g": 1000, "Estimated_Price_EUR": 11.50},
            {"Run": "2026-10-12 Dynamic Run", "Category": "vegetable", "Item": "Broccoli", "Quantity_g": 500, "Estimated_Price_EUR": 2.00}
        ], mode="replace")
        self.assertIn("Successfully updated grocery list", grocery_msg)

        get_grocery_fn = self.tools["tool_get_grocery_list"]
        grocery_str = get_grocery_fn()
        self.assertIn("2026-10-12 Dynamic Run", grocery_str)
        self.assertIn("Ground Beef", grocery_str)

    def test_retrospective_skipped_meal_and_eating_out_workflow(self):
        save_mem_fn = self.tools["tool_save_memory_note"]
        # 1. User reports skipping breakfast
        res_skip = save_mem_fn("- [2026-10-10] Skipped Breakfast; rolled over 400 kcal and 25g protein to weekly deficit", tier="weekly")
        self.assertIn("Saved to weekly memory", res_skip)

        # 2. User reports eating out for lunch
        res_eatout = save_mem_fn("- [2026-10-10] Ate out for Lunch at Vietnamese Pho Ga restaurant (est. 850 kcal, 45g protein); home lunch ingredients remained unused", tier="weekly")
        self.assertIn("Saved to weekly memory", res_eatout)

        # Verify memory records both deviations
        mem_ctx = MemoryManager(self.test_dir).get_context()
        self.assertTrue(any("Skipped Breakfast" in n for n in mem_ctx["weekly"]))
        self.assertTrue(any("Ate out for Lunch" in n for n in mem_ctx["weekly"]))

        # Agent updates meal plan for dinner or upcoming days to account for carried deficit
        update_meal_plan_fn = self.tools["tool_update_meal_plan"]
        plan_msg = update_meal_plan_fn([
            {
                "Date": "2026-10-10",
                "Meal": "Dinner",
                "Recipe": "Comforting Chicken Soup with Extra Whey Shake",
                "Ingredient": "250g Chicken Wings; 100g Rice Noodles; 30g ON Whey",
                "P": 60,
                "C": 45,
                "F": 12,
                "Calories": 530
            }
        ])
        self.assertIn("Successfully updated", plan_msg)

    def test_agent_prompt_train_of_thought_and_guidelines(self):
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        
        # Verify 3-step meal planning train of thought
        self.assertIn("Step 1: Consider the Budget", prompt)
        self.assertIn("weekly budget for protein", prompt)
        self.assertIn("Step 2: Allocate the Budget by Roughly Balancing Needs and Preferences", prompt)
        self.assertIn("Step 3: Be Aware of Nuances Relating to Nutrition Facts", prompt)
        self.assertIn("Raw vs. cooked weight yields", prompt)
        self.assertIn("Bone-in and skin-on vs. boneless and skinless", prompt)
        self.assertIn("NO RIGID LOCAL NUTRITION OR PRICE BOOKKEEPING", prompt)
        
        # Verify grocery receipt guideline and scope distinction
        self.assertIn("PRIMARY PURPOSE: Note purchased protein stock in Short-Term Memory", prompt)
        self.assertIn("IGNORE non-protein items", prompt)
        self.assertIn("STOCK TRACKING VS. GROCERY LIST SCOPE", prompt)
        self.assertIn("On-Hand Stock Tracking in Short-Term Memory", prompt)
        self.assertIn("tracks PROTEIN ONLY", prompt)
        self.assertIn("Weekly Grocery List", prompt)
        self.assertIn("MUST comprehensively include ALL food types", prompt)

    def test_grocery_list_update_guidelines_in_prompt(self):
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertNotIn("USER CONFIRMATION REQUIRED", prompt)
        self.assertNotIn("ask the user for confirmation", prompt)
        self.assertIn("tool_get_grocery_list", prompt)
        self.assertIn("tool_update_grocery_list", prompt)
        self.assertIn("sorted by [Run, Category]", prompt)

    def test_grocery_list_summary_only_and_run_filter(self):
        get_grocery_fn = self.tools["tool_get_grocery_list"]
        # 1. Full table (default)
        full_res = get_grocery_fn()
        self.assertIn("| Run | Category | Item |", full_res)
        self.assertIn("Chicken Breast", full_res)
        self.assertIn("Broccoli", full_res)

        # 2. summary_only=True returns 1-line compact summary saving tokens
        summary_res = get_grocery_fn(summary_only=True)
        self.assertNotIn("|---|", summary_res)
        self.assertIn("Grocery list exists (2 items across 1 run(s): Saturday Run)", summary_res)

        # 3. run_name filter
        filtered_res = get_grocery_fn(run_name="Saturday Run")
        self.assertIn("Chicken Breast", filtered_res)
        not_found_res = get_grocery_fn(run_name="Wednesday Run")
        self.assertIn("No items found for run 'Wednesday Run'", not_found_res)

    def test_prompt_instructs_no_redundant_reads_or_meal_plan_validator_for_groceries(self):
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("Do NOT call tool_get_grocery_list or re-read", prompt)
        self.assertIn("NEVER call tool_check_meal_plan when updating groceries", prompt)
        self.assertIn("summary_only=True", prompt)

    def test_prompt_instructs_no_redundant_reads_or_prechecks_for_meal_plan(self):
        """System prompt must enforce injected weekly context, direct update, and automatic validation."""
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("Active Weekly Meal Plan (Full Context):", prompt)
        self.assertIn("FULL WEEK CONTEXT INJECTED", prompt)
        self.assertIn("DIRECT UPDATE", prompt)
        self.assertIn("AUTOMATIC PLAN VALIDATION", prompt)
        self.assertIn("NO PRE-CHECKS: NEVER call tool_check_meal_plan before updating", prompt)
        self.assertIn("NO POST-UPDATE READS", prompt)
        self.assertIn("Do NOT call tool_get_meal_plan", prompt)

    def test_tool_update_meal_plan_explicitly_mentions_disk_persistence_and_no_reread(self):
        """tool_update_meal_plan output informs LLM that file is on disk, does not need re-read, and includes automatic validation."""
        update_fn = self.tools["tool_update_meal_plan"]
        msg = update_fn([{
            "Date": "2026-10-10",
            "Meal": "Lunch",
            "Recipe": "Quick Chicken",
            "Ingredient": "200g Chicken",
            "P": 40,
            "C": 0,
            "F": 5,
            "Calories": 220
        }])
        self.assertIn("Artifact is saved to disk", msg)
        self.assertIn("Do NOT call tool_get_meal_plan", msg)
        self.assertIn("[AUTOMATIC PLAN VALIDATION]:", msg)

    def test_tool_check_meal_plan_caches_unchanged_plan_to_prevent_duplicate_checks(self):
        """Repeated consecutive calls to tool_check_meal_plan without modifying plan return cached completion note."""
        check_fn = self.tools["tool_check_meal_plan"]
        first_call = check_fn(target_calories=1345, target_p=110, target_c=125, target_f=45)
        self.assertIn("[ACCEPTED]", first_call)

        second_call = check_fn(target_calories=1345, target_p=110, target_c=125, target_f=45)
        self.assertIn("[ACCEPTED]", second_call)
        self.assertIn("was already verified and has not changed", second_call)
        self.assertIn("Do NOT call tool_check_meal_plan again", second_call)


if __name__ == "__main__":
    unittest.main()
