# Design Specification: LLM-Centric Memory & Artifact Architecture

**Date:** 2026-10-12  
**Status:** Approved for Implementation Planning

---

## 1. Intent & The Why
The original system attempted to combine algorithmic solvers (combinatorial recipe solvers, macro calculators, shelf-life interval schedulers, implicit inventory deduction engines, price databases) with an LLM chat agent. This created rigid constraints, unnecessary code bloat, fragile state reconciliation, and bypassed the primary strength of modern LLMs: holistic, flexible reasoning.

This architecture completely eliminates algorithmic solvers from Python. The LLM (Gemini via Google ADK) is the sole planner, chef, and decision maker. The Python codebase acts strictly as a lightweight persistence runtime providing:
1. Two-tier Markdown memory storage (`data/memory/long_term.md` and `data/memory/weekly.md`).
2. Three structured CSV artifact stores (`meal_plan.csv`, `batch_cook.csv`, `grocery_list.csv`).
3. Seven pure I/O tool primitives with zero business logic.
4. Google ADK integration with single-instance session time recording.

---

## 2. Architecture & Component Decomposition

```
meal_planner/
├── __init__.py
├── agent.py          # Google ADK Agent setup, static system prompt, 7 pure I/O tools
├── cli.py            # 'meals' CLI / ADK Web Playground runner, setup wizard
├── models.py         # Minimal shared types/constants (currency symbols)
└── tools/
    ├── __init__.py
    ├── artifacts.py  # Pure CSV I/O for meal_plan, batch_cook, grocery_list
    ├── memory.py     # Pure Markdown I/O for weekly.md & long_term.md with noise filter
    └── onboarding.py # Timezone resolution helper
```

### Components Eliminated:
- `meal_planner/tools/inventory.py` (legacy 1000-line rule-based consumption & stock reconciliation engine)
- `meal_planner/tools/adaptation.py` (legacy meal deviation & grocery substitution solver)
- `meal_planner/tools/grocery_planner.py` (legacy grocery list generator)
- `meal_planner/tools/macro_calculator.py` (legacy math solver)
- `meal_planner/tools/meal_generator.py` (legacy combinatorial meal schedule generator)
- `meal_planner/tools/tracker.py` (legacy price tracker & consumption logging database)
- `meal_planner/catalog/` (`ingredients.json` and `recipes.json`)

---

## 3. Data Contracts

### 3.1 Memory Files (Markdown)
- **`data/memory/long_term.md`**:
  ```markdown
  - Bodyweight: 65.0 kg | Goal: lean_bulk | Target Calories: 2550 kcal
  - Weekly Protein Budget: €45.00
  - Qualitative Preferences: Prefers savory meals, broth-based soups, and jasmine rice
  - Intolerances: None
  ```
- **`data/memory/weekly.md`**:
  ```markdown
  - [2026-10-12] Stock on hand: 600g Chicken Breast, 400g Ground Beef
  - [2026-10-13] Skipped Dinner; 200g chicken breasts remain in fridge
  ```

### 3.2 Artifact Files (CSV)
- **`meal_plan.csv`**:
  ```csv
  Date,Meal,Recipe,Ingredient,P,C,F,Calories
  2026-10-12,Breakfast,Scrambled Eggs on Toast,3 Eggs; 2 Slices Sourdough,24,30,15,350
  2026-10-12,Lunch,Air Fried Chicken Rice Bowl,250g Chicken Breast; 150g Jasmine Rice,60,45,8,500
  ```
- **`batch_cook.csv`**:
  ```csv
  Dish,Main_Protein,Meals
  Thịt Kho Tàu,1000g Pork Belly,3
  Gà Xào Sả Ớt,1kg Chicken Thighs,3
  ```
- **`grocery_list.csv`**:
  ```csv
  Run,Category,Item,Quantity_g,Estimated_Price_EUR
  Saturday Run,meat,Chicken Breast,1000,9.50
  Saturday Run,produce,Broccoli,500,2.00
  Wednesday Run,meat,Ground Beef,800,8.00
  ```
  *(Post-processed: sorted by `[Run, Category]`)*

---

## 4. Agent Tools (7 Pure I/O Primitives)
1. `tool_save_memory_note(note: str, tier: str = "weekly") -> str`: Saves note to `weekly.md` or `long_term.md`.
2. `tool_get_meal_plan(target_date: Optional[str] = None) -> str`: Reads active `meal_plan.csv`.
3. `tool_update_meal_plan(meal_entries: list[dict]) -> str`: Updates active `meal_plan.csv`.
4. `tool_get_grocery_list() -> str`: Reads active `grocery_list.csv`.
5. `tool_update_grocery_list(grocery_entries: list[dict], mode: str = "merge") -> str`: Updates active `grocery_list.csv` (sorted by Run, Category).
6. `tool_get_batch_cook() -> str`: Reads active `batch_cook.csv`.
7. `tool_update_batch_cook(dishes: list[dict]) -> str`: Updates active `batch_cook.csv`.

---

## 5. System Prompt & Temporal Execution
- `get_recorded_time()` records the current time once upon agent initialization.
- Static `build_system_instruction()` string passed to Google ADK `Agent(instruction=...)`.
- System instruction includes:
  - Onboarding guidance (stats, goal, protein budget, eating preferences).
  - Train of thought: Budget -> Needs vs. Preferences -> Nutrition Nuances.
  - User confirmation mandate before running `tool_update_grocery_list`.
  - Batch cook schema: `Dish, Main_Protein, Meals`.
  - Stock tracking strictly for protein items in `weekly.md`.
