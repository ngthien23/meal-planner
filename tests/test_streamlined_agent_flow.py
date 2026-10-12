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

        # 2. Agent updates BOTH meal plan and grocery list in ONE single call to tool_update_plans!
        update_plans_fn = self.tools["tool_update_plans"]
        combined_msg = update_plans_fn(
            meal_entries=[
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
            ],
            grocery_entries=[
                {"Run": "2026-10-12 Dynamic Run", "Category": "meat", "Item": "Ground Beef (5% Fat)", "Quantity_g": 1000, "Estimated_Price_EUR": 11.50},
                {"Run": "2026-10-12 Dynamic Run", "Category": "vegetable", "Item": "Broccoli", "Quantity_g": 500, "Estimated_Price_EUR": 2.00}
            ],
            grocery_mode="replace"
        )
        self.assertIn("Meal Plan: Successfully updated", combined_msg)
        self.assertIn("Grocery List: Successfully updated", combined_msg)
        self.assertIn("[AUTOMATIC PLAN VALIDATION]:", combined_msg)

        # Verify meal plan artifact is updated on disk
        from meal_planner.tools.artifacts import get_meal_plan_csv, get_grocery_list_csv
        plan_rows = get_meal_plan_csv(self.test_dir, target_date="2026-10-10")
        self.assertTrue(any("Air Fried Crispy Chicken" in r.get("Recipe", "") for r in plan_rows))
        self.assertTrue(any("Comforting Chicken Soup" in r.get("Recipe", "") for r in plan_rows))

        # Verify grocery list artifact is updated on disk
        grocery_rows = get_grocery_list_csv(self.test_dir)
        self.assertTrue(any("Ground Beef" in r.get("Item", "") and "2026-10-12 Dynamic Run" in r.get("Run", "") for r in grocery_rows))

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
        update_plans_fn = self.tools["tool_update_plans"]
        plan_msg = update_plans_fn(meal_entries=[
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
        self.assertIn("Meal Plan: Successfully updated", plan_msg)

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

    def test_prompt_instructs_short_term_context_and_consolidated_update_tool(self):
        """System prompt must inject all 3 plans into short-term context and enforce tool_update_plans."""
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        # All 3 plans loaded into context:
        self.assertIn("Active Weekly Meal Plan (Full Context):", prompt)
        self.assertIn("Active Batch Cook Instructions (Full Context):", prompt)
        self.assertIn("Active Grocery List (Full Context):", prompt)
        self.assertIn("Chicken Breast", prompt)
        self.assertIn("Broccoli", prompt)

        # Policy guidelines:
        self.assertIn("FULL SHORT-TERM CONTEXT INJECTED", prompt)
        self.assertIn("SINGLE CONSOLIDATED UPDATE TOOL", prompt)
        self.assertIn("tool_update_plans", prompt)
        self.assertIn("AUTOMATIC PLAN VALIDATION", prompt)
        self.assertIn("NO PRE-CHECKS: NEVER call tool_check_meal_plan before updating", prompt)
        self.assertIn("NO POST-UPDATE READS", prompt)

    def test_tool_update_plans_updates_all_three_artifacts_in_single_call(self):
        """tool_update_plans updates meal plan, batch cook, and grocery list in ONE call and returns auto-validation."""
        from meal_planner.tools.artifacts import get_meal_plan_csv, get_batch_cook_csv, get_grocery_list_csv
        update_fn = self.tools["tool_update_plans"]
        msg = update_fn(
            meal_entries=[{
                "Date": "2026-10-10",
                "Meal": "Lunch",
                "Recipe": "Quick Chicken",
                "Ingredient": "200g Chicken",
                "P": 40,
                "C": 0,
                "F": 5,
                "Calories": 220
            }],
            batch_cook_entries=[{
                "Dish": "Braised Pork",
                "Main_Protein": "1000g Pork Belly",
                "Meals": 3
            }],
            grocery_entries=[{
                "Run": "Saturday Run",
                "Category": "meat",
                "Item": "Pork Belly",
                "Quantity_g": 1000,
                "Estimated_Price_EUR": 9.00
            }]
        )
        self.assertIn("Meal Plan: Successfully updated", msg)
        self.assertIn("Batch Cook: Successfully updated", msg)
        self.assertIn("Grocery List: Successfully updated", msg)
        self.assertIn("[AUTOMATIC PLAN VALIDATION]:", msg)
        self.assertIn("Artifacts and memory are saved to disk", msg)

        # Verify all 3 CSVs
        plan_rows = get_meal_plan_csv(self.test_dir)
        self.assertTrue(any("Quick Chicken" in r.get("Recipe", "") for r in plan_rows))

        batch_rows = get_batch_cook_csv(self.test_dir)
        self.assertTrue(any("Braised Pork" in r.get("Dish", "") for r in batch_rows))

        grocery_rows = get_grocery_list_csv(self.test_dir)
        self.assertTrue(any("Pork Belly" in r.get("Item", "") for r in grocery_rows))

    def test_tool_update_plans_with_memory_and_plans_combined(self):
        """tool_update_plans can simultaneously record short-term/long-term notes and update plans in a single call."""
        from meal_planner.tools.artifacts import get_meal_plan_csv, get_grocery_list_csv
        update_fn = self.tools["tool_update_plans"]
        res = update_fn(
            short_term_notes=["[2026-10-10] Stock on hand: 1kg Chicken Wings"],
            long_term_notes=["Athlete bodyweight updated to 68.0 kg"],
            meal_entries=[{
                "Date": "2026-10-10",
                "Meal": "Dinner",
                "Recipe": "Air Fried Wings",
                "Ingredient": "500g Chicken Wings",
                "P": 50,
                "C": 0,
                "F": 35,
                "Calories": 515
            }],
            grocery_entries=[{
                "Run": "2026-10-12 Dynamic Run",
                "Category": "meat",
                "Item": "Chicken Breast",
                "Quantity_g": 1000,
                "Estimated_Price_EUR": 9.50
            }]
        )
        self.assertIn("Short-Term Memory: Saved 1 note(s)", res)
        self.assertIn("Long-Term Memory: Saved 1 note(s)", res)
        self.assertIn("Meal Plan: Successfully updated", res)
        self.assertIn("Grocery List: Successfully updated", res)
        self.assertIn("[AUTOMATIC PLAN VALIDATION]:", res)
        self.assertIn("Artifacts and memory are saved to disk", res)

        # Verify memory files on disk
        mem_ctx = MemoryManager(self.test_dir).get_context()
        self.assertTrue(any("1kg Chicken Wings" in n for n in mem_ctx["weekly"]))
        self.assertTrue(any("68.0 kg" in n for n in mem_ctx["long_term"]))

        # Verify plan files on disk
        plan_rows = get_meal_plan_csv(self.test_dir, target_date="2026-10-10")
        self.assertTrue(any("Air Fried Wings" in r.get("Recipe", "") for r in plan_rows))

        grocery_rows = get_grocery_list_csv(self.test_dir)
        self.assertTrue(any("2026-10-12 Dynamic Run" in r.get("Run", "") for r in grocery_rows))

    def test_tool_update_plans_memory_aliases(self):
        """tool_update_plans accepts alias kwargs like weekly_note, weekly_notes, long_term_note, or raw string."""
        update_fn = self.tools["tool_update_plans"]
        res = update_fn(
            weekly_note="[2026-10-11] Ate out for lunch",
            long_term_note="Target Protein: 160P"
        )
        self.assertIn("Short-Term Memory: Saved 1 note(s)", res)
        self.assertIn("Long-Term Memory: Saved 1 note(s)", res)

        mem_ctx = MemoryManager(self.test_dir).get_context()
        self.assertTrue(any("Ate out for lunch" in n for n in mem_ctx["weekly"]))
        self.assertTrue(any("Target Protein: 160P" in n for n in mem_ctx["long_term"]))

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
