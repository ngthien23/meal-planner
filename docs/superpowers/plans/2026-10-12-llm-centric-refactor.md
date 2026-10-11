# LLM-Centric Memory & Artifact Architecture Refactor Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the codebase to eliminate all legacy rule-based solver modules and hardcoded catalogs, leaving a clean architecture where the LLM makes decisions using 7 pure I/O tools interacting with Markdown memories and CSV artifacts.

**Architecture:** Deletes legacy programmatic solvers (`inventory.py`, `adaptation.py`, `meal_generator.py`, `macro_calculator.py`, `grocery_planner.py`, `tracker.py`, and `catalog/`). Consolidates the runtime into pure CSV artifact manipulation (`artifacts.py`), Markdown memory management (`memory.py`), Google ADK agent definition with static instruction and single-time recording (`agent.py`), and CLI/ADK runner (`cli.py`).

**Tech Stack:** Python 3.10+, Google ADK (`google-adk`), Google GenAI SDK (`google-genai`), unittest.

**Spec:** `docs/superpowers/specs/2026-10-12-llm-centric-memory-artifact-architecture-design.md`

## Global Constraints
- Target daily protein, budget, and meals are planned entirely by LLM reasoning, not Python algorithmic heuristics.
- All on-hand fridge stock tracking in `weekly.md` is strictly protein-only with dates.
- Weekly grocery list includes all food types and is sorted by `[Run, Category]`.
- The agent must always ask the user for confirmation before executing `tool_update_grocery_list`.
- The current local time is recorded once at session initialization; system instructions are passed as a static string.
- All tools must strictly interact with memory or artifacts (8 tools: 7 pure I/O primitives + 1 meal plan verification tool).

## Review Focus
1. Independence from deleted modules: Ensure remaining files (`agent.py`, `cli.py`, `artifacts.py`, `memory.py`) have zero imports from deleted legacy modules.
2. Artifact purity: Verify `get_meal_plan_csv` never triggers programmatic plan creation if files do not exist.
3. Test suite green: Ensure all tests pass cleanly with 100% success without relying on legacy solver fixtures.
4. Clean CLI startup: Ensure `meals`, `meals --setup`, and `meals --cli` run cleanly without legacy references.
5. No memory or artifact schema corruption: CSV headers and Markdown bullet formats strictly adhere to requirements.

---

### Task 1: Decouple Core Runtime & Move Cycle Prefix Logic to Artifacts

**Files:**
- Modify: `meal_planner/tools/artifacts.py`
- Modify: `meal_planner/models.py`
- Modify: `meal_planner/tools/onboarding.py`
- Test: `tests/test_artifact_tools.py`

- [x] **Step 1: Move `get_current_cycle_prefix` into `meal_planner/tools/artifacts.py`**
  - Implement `get_current_cycle_prefix(user_timezone: str = "Europe/Brussels", reference_dt: Optional[datetime] = None, week_start_day: str = "Saturday") -> str` inside `artifacts.py`.
  - Remove imports from `meal_planner.tools.meal_generator` and `meal_planner.tools.onboarding.load_user_profile`.
- [x] **Step 2: Streamline `meal_planner/models.py` and `meal_planner/tools/onboarding.py`**
  - In `models.py`, retain `CURRENCY_SYMBOLS` and `get_currency_symbol`. Remove legacy `Ingredient`, `Recipe`, `InventoryItem`, `InventoryState`, `UserProfile`.
  - In `onboarding.py`, retain `resolve_timezone`. Remove `load_user_profile`, `init_user_profile`, `get_relative_datetime`.
- [x] **Step 3: Update `meal_planner/agent.py` and `meal_planner/cli.py` imports**
  - Import `get_current_cycle_prefix` directly from `meal_planner.tools.artifacts`.
- [x] **Step 4: Verify core unit tests pass**
  - Run `python -m unittest tests/test_artifact_tools.py tests/test_agent_tools.py`.
- [x] **Step 5: Commit changes**
  - `git add meal_planner/ tests/; git commit -m "refactor: decouple artifacts and prune legacy model definitions"`

---

### Task 2: Delete Obsolete Rule-Based Solver Modules & Catalogs

**Files:**
- Delete: `meal_planner/tools/inventory.py`
- Delete: `meal_planner/tools/adaptation.py`
- Delete: `meal_planner/tools/grocery_planner.py`
- Delete: `meal_planner/tools/macro_calculator.py`
- Delete: `meal_planner/tools/meal_generator.py`
- Delete: `meal_planner/tools/tracker.py`
- Delete: `meal_planner/catalog/ingredients.json`
- Delete: `meal_planner/catalog/recipes.json`

- [x] **Step 1: Remove legacy rule-based modules from `meal_planner/tools/`**
  - Remove `inventory.py`, `adaptation.py`, `grocery_planner.py`, `macro_calculator.py`, `meal_generator.py`, `tracker.py`.
- [x] **Step 2: Remove catalog files**
  - Remove `meal_planner/catalog/ingredients.json` and `recipes.json`.
- [x] **Step 3: Check codebase for any lingering imports**
  - Run `git grep "meal_generator"` and `git grep "inventory"` in `meal_planner/`.
  - Verify `meal_planner/` is completely clean of legacy solver references.
- [x] **Step 4: Commit deletion**
  - `git rm meal_planner/tools/inventory.py meal_planner/tools/adaptation.py meal_planner/tools/grocery_planner.py meal_planner/tools/macro_calculator.py meal_planner/tools/meal_generator.py meal_planner/tools/tracker.py meal_planner/catalog/ingredients.json meal_planner/catalog/recipes.json; git commit -m "refactor: delete legacy rule-based solvers and catalog files"`

---

### Task 3: Refactor Test Suite to Pure Memory & Artifact Architecture

**Files:**
- Delete: Obsolete legacy test files (`test_inventory_state.py`, `test_inventory_reconciliation.py`, `test_retrospective_adjustments.py`, `test_weekly_tweaks.py`, `test_pantry_and_splits.py`, `test_dynamic_adaptation.py`, `test_meal_generator.py`, `test_macro_calculator.py`, `test_price_tracking.py`, `test_grocery_planner.py`, `test_add_foods.py`, `test_profile_and_macros.py`).
- Modify: `tests/test_streamlined_agent_flow.py` (remove legacy `init_user_profile` fixture).
- Modify: `tests/test_artifact_tools.py` (remove legacy `init_user_profile` fixture).
- Modify: `tests/test_conversational_onboarding.py` (verify clean onboarding).

- [x] **Step 1: Update test fixtures in `tests/test_artifact_tools.py` and `tests/test_streamlined_agent_flow.py`**
  - Replace `init_user_profile` with direct memory/artifact setup.
- [x] **Step 2: Delete obsolete legacy test files**
  - Remove tests that tested deleted rule-based functions.
- [x] **Step 3: Run full test suite**
  - Run `python -m unittest discover -s tests -p "test_*.py" -v`.
- [x] **Step 4: Verify 100% green test suite**
  - Confirm all remaining tests pass.
- [x] **Step 5: Commit changes**
  - `git commit -m "test: prune legacy solver tests and align test suite with LLM-centric architecture"`

---

### Task 4: System Integration Verification & Final Audit

**Files:**
- Verify: `meal_planner/`
- Verify: `tests/`
- Verify: `README.md`
- Verify: `meal-planner-requirements.md`

- [x] **Step 1: Verify CLI runner and setup**
  - Run `python main.py --help`.
  - Run `python -m unittest discover -s tests -p "test_*.py"`.
- [x] **Step 2: Verify git status is clean and push to remote**
  - `git push origin main`.
