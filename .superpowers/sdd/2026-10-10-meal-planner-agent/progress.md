# SDD ledger — plan: docs/superpowers/plans/2026-10-10-meal-planner-agent.md

Pre-flight scan:
- Task 1 produces `Ingredient`, `Recipe`, `load_catalog` -> consumed by Tasks 3, 4, 5, 6, 7, 8
- Task 2 produces `UserProfile`, timezone utils -> consumed by Tasks 3, 4, 5, 6, 7, 8
- Task 3 produces `MacroTargets`, `calculate_daily_targets`, `solve_protein_raw_weight` -> consumed by Tasks 4, 7, 8
- Task 4 produces `WeeklyPlan`, `export_meal_plan_csv` -> consumed by Tasks 5, 7, 8
- Task 5 produces `SplitGroceryList`, `PantryState`, `export_grocery_list_csv` -> consumed by Tasks 7, 8
- Task 6 produces tracker & analytics functions -> consumed by Task 8
- Task 7 produces adaptation functions -> consumed by Task 8
- Task 8 integrates ADK agent & CLI -> consumes all
Interfaces are consistent and clean.
