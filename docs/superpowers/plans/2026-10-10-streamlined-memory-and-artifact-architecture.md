# Streamlined Memory and Artifact Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Overview
Refactor the AI Meal Planner Agent to rely fully on LLM reasoning and reduce the toolbox and persistence layer to pure I/O primitives:
1. Eliminate `profile.json`: User profile, stats, and eating preferences reside in Long-Term Memory (`data/memory/long_term.md`).
2. Eliminate `inventory.json`: On-hand stock is recorded with dates in Short-Term Memory (`data/memory/weekly.md`). Missed calories and meal deviations are also tracked in `weekly.md`.
3. Eliminate all programmatic solvers and sync tools (Section C tools + inventory tools + `tool_onboard_user`). The LLM acts as the chef, planner, and classifier, manipulating visible artifacts directly.
4. Clean up `cli.py` `--setup`: Remove the API key prefix suggestion note and eliminate default preferences / `profile.json` generation.

---

## File Structure & Responsibilities

| File | Changes | Responsibility |
|---|---|---|
| `meal_planner/cli.py` | Modify | Remove API key format note in `quick_setup_wizard`. Remove `profile.json` creation and default preferences. |
| `meal_planner/agent.py` | Modify | Prune tools down to 7 core primitives: `tool_save_memory_note`, `tool_get_meal_plan`, `tool_update_meal_plan`, `tool_get_grocery_list`, `tool_update_grocery_list`, `tool_get_batch_cook`, `tool_update_batch_cook`, and `tool_get_macro_targets`. Update `build_system_instruction` to detect onboarding status from `long_term.md` and instruct LLM to use `tool_save_memory_note` for profile & stock notes. |
| `meal_planner/tools/onboarding.py` | Modify | Update or simplify helpers; remove dependency on `profile.json`. |
| `meal_planner/tools/memory.py` | Maintain | Keep clean Markdown storage for `weekly.md` and `long_term.md`. |
| `tests/` | Modify | Update test suite to assert the streamlined tool set, memory-driven onboarding, and artifact manipulation. |

---

## Tasks

### Task 1: CLI and Setup Simplification
- [ ] Remove the API key prefix suggestion note (`[!] Note: Standard permanent Gemini API keys start with 'AIzaSy' ...`) in `meal_planner/cli.py`.
- [ ] In `quick_setup_wizard`, remove `init_user_profile` call and default profile dictionary creation. If API key is resolved, setup is complete without creating `profile.json`.
- [ ] Write unit test in `tests/test_conversational_onboarding.py` verifying `--setup` does not print the suggestion and does not write `profile.json`.

### Task 2: System Instruction & Memory-Driven Onboarding
- [ ] Update `build_system_instruction` in `meal_planner/agent.py`:
  - Read `MemoryManager(data_dir).get_context()`.
  - If `long_term.md` has no profile stats, lifecycle is `ONBOARDING STATE`: instruct agent to greet user, ask for stats/preferences/budget, and save them via `tool_save_memory_note(note, tier='long_term')`.
  - If `long_term.md` has profile stats, lifecycle is `ACTIVE PLANNING STATE`: direct assistance with meal plans, dated stock, and groceries.
  - Instruct agent that stock on hand is recorded in `weekly.md` with dates (e.g. `[YYYY-MM-DD] Stock on hand: 500g Chicken Wings...`).
  - Instruct agent that skipped meals or eating out are noted in `weekly.md` and the LLM updates `meal_plan.csv` directly via `tool_update_meal_plan`.
  - Instruct agent that weekly calorie differences are noted in `weekly.md`.
  - Remove all hardcoded "default preferences".

### Task 3: Streamlining the Tool Set in `meal_planner/agent.py`
- [ ] In `get_agent_tools(data_dir)`:
  - Keep ONLY:
    1. `tool_save_memory_note(note: str, tier: str = "weekly") -> str`
    2. `tool_get_meal_plan(target_date: Optional[str] = None) -> str`
    3. `tool_update_meal_plan(meal_entries: list[dict]) -> str`
    4. `tool_get_grocery_list() -> str`
    5. `tool_update_grocery_list(grocery_entries: list[dict], mode: str = "merge") -> str`
    6. `tool_get_batch_cook() -> str`
    7. `tool_update_batch_cook(dishes: list[dict]) -> str`
    8. `tool_get_macro_targets(bodyweight_kg: float, target_calories: float, protein_multiplier: float = 2.2, fat_multiplier: float = 1.0) -> str`
  - Remove all programmatic solvers and obsolete tools:
    - `tool_onboard_user`
    - `tool_configure_planning_schedule`
    - `tool_generate_meal_plan`
    - `tool_report_meal_deviation`
    - `tool_substitute_ingredient`
    - `tool_spread_missed_calories`
    - `tool_get_inventory`
    - `tool_update_on_hand_stock`
    - `tool_catch_up_inventory`
    - `tool_report_past_meal_deviation`
    - `tool_lookup_food_catalog`
    - `tool_add_food_item`
    - `tool_log_price_update`
    - `tool_get_analytics`
    - `tool_view_grocery_list`
    - `tool_view_batch_cook_list`

### Task 4: Test Suite Harmonization & Verification
- [ ] Update `tests/test_conversational_onboarding.py`, `tests/test_streamlined_agent_flow.py`, `tests/test_agent_tools.py`, and `tests/test_adk_playground.py` to match the 8 streamlined tools.
- [ ] Run full test suite: `uv run python -m unittest discover -s tests -p "test_*.py"`.
- [ ] Verify clean `data/` directory.
