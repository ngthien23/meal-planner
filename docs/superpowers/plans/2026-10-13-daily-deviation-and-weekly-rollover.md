# Daily Intake Deviation Detection & Weekly Rollover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect daily caloric (~15%) and protein (~10%) deviations against daily targets in `meal_plan.csv`, record one idempotent note per date in short-term memory (`weekly.md`), and carry forward any substantial net weekly difference to the next week upon cycle rollover or start date change.

**Architecture:** Extend `MemoryManager` with `record_daily_deviation` and `rollover_weekly_memory`. In `check_meal_plan_csv`, group meal plan rows by Date, calculate daily intake, compare against baseline daily goals (from long-term memory or defaults), and sync date-keyed deviation notes in `weekly.md`. When a new week/cycle begins or a plan's start date changes, evaluate the previous plan's cumulative net difference and carry it forward into the new short-term memory if substantial.

**Tech Stack:** Python 3.13, unittest, CSV, standard library `re`, `datetime`, `os`.

**Spec:** docs/superpowers/specs/2026-10-12-llm-centric-memory-artifact-architecture-design.md

## Global Constraints

- Daily deviation threshold: >= 15% Calories OR >= 10% Protein against daily target goals.
- Idempotence: Exactly one short-term memory record per deviating date in `weekly.md`; updating plans never produces duplicate lines for the same date.
- Obsolete date cleanup: When a date's meals are modified so they fall within tolerance, its deviation record is removed.
- Rollover condition: Carried forward to the next week's short-term memory if and only if the cumulative net difference is substantial (>= 15% of daily calories or >= 10% of daily protein).
- Existing carryover parsing compatibility: Carried note format `- [Carried from last week] Net weekly deviation: {+X} kcal, {+Y}g P carried forward.` must be directly parseable by existing `check_meal_plan_csv` logic.

## Review Focus

1. Daily tolerance edge case: A day with exactly 14.9% calorie diff and 9.9% protein diff does not trigger a deviation note.
2. Idempotency across runs: Calling `check_meal_plan_csv` repeatedly on unchanged or partially changed plans does not duplicate entries in `weekly.md`.
3. Resolution of deviations: If a date previously deviated and now has adjusted meals within tolerance, the old deviation note is cleanly pruned from `weekly.md`.
4. Net weekly rollover sign preservation: A net calorie deficit (-300 kcal) and protein surplus (+25g P) carry with correct signs into next week's memory and adjust targets accurately.
5. Plan start date change detection: Writing a new meal plan starting on a new date preserves and rolls over the previous plan's substantial net deviation.

---

### Task 1: MemoryManager Daily Deviation & Rollover Methods

**Files:**
- Modify: `meal_planner/tools/memory.py`
- Test: `tests/test_daily_deviation_and_rollover.py`

**Interfaces:**
- Consumes: `MemoryManager._read_notes`, `MemoryManager._write_notes`, `weekly.md`
- Produces:
  - `MemoryManager.record_daily_deviation(date: str, planned_cal: float, target_cal: float, planned_p: float, target_p: float, cal_threshold: float = 0.15, p_threshold: float = 0.10) -> dict`
  - `MemoryManager.rollover_weekly_memory(net_cal: float = 0.0, net_p: float = 0.0, daily_cal_target: float = 2500.0, daily_p_target: float = 150.0, cal_threshold: float = 0.15, p_threshold: float = 0.10) -> dict`

- [ ] **Step 1: Write failing tests for `record_daily_deviation` and `rollover_weekly_memory`**
Write tests in `tests/test_daily_deviation_and_rollover.py`:
- Test recording deviation when cal >= 15% or protein >= 10%.
- Test idempotence (recording twice updates in-place, does not duplicate).
- Test clearing deviation when within tolerance.
- Test rollover carrying forward when substantial, and not carrying when within tolerance.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run python -m unittest tests/test_daily_deviation_and_rollover.py -v`
Expected: FAIL with `AttributeError: 'MemoryManager' object has no attribute 'record_daily_deviation'`

- [ ] **Step 3: Implement `record_daily_deviation` and `rollover_weekly_memory` in `meal_planner/tools/memory.py`**
- Implement `record_daily_deviation`:
  - Calculate `cal_pct = abs(planned_cal - target_cal) / target_cal` if target_cal > 0 else 0
  - Calculate `p_pct = abs(planned_p - target_p) / target_p` if target_p > 0 else 0
  - Pattern to match existing date note: `re.compile(rf"^\[{re.escape(date)}\]\s*Daily\s+deviation:", re.I)`
  - If deviating: format note `[{date}] Daily deviation: {cal_diff:+d} kcal, {p_diff:+d}g P vs target ({int(round(planned_cal))} kcal / {int(round(planned_p))}g P planned vs {int(round(target_cal))} kcal / {int(round(target_p))}g P target)`. If match exists, replace in-place; else append.
  - If not deviating: filter out any note matching the pattern.
- Implement `rollover_weekly_memory`:
  - Determine if substantial: `abs(net_cal) >= daily_cal_target * cal_threshold` or `abs(net_p) >= daily_p_target * p_threshold`.
  - Preserve any long-term or user-pinned notes if applicable, but clear weekly notes.
  - If substantial: add note `[Carried from last week] Net weekly deviation: {int(round(net_cal)):+d} kcal, {int(round(net_p)):+d}g P carried forward.` to `weekly.md`.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run python -m unittest tests/test_daily_deviation_and_rollover.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add meal_planner/tools/memory.py tests/test_daily_deviation_and_rollover.py
git commit -m "feat: add daily deviation recording and rollover in MemoryManager"
```

---

### Task 2: Daily Deviation Detection in `check_meal_plan_csv`

**Files:**
- Modify: `meal_planner/tools/artifacts.py:459-736`
- Test: `tests/test_daily_deviation_and_rollover.py`

**Interfaces:**
- Consumes: `MemoryManager.record_daily_deviation`
- Produces:
  - Updated `check_meal_plan_csv` returning `'daily_deviations'` in result dict and syncing with `weekly.md`.

- [ ] **Step 1: Write failing tests for `check_meal_plan_csv` daily deviation recording**
In `tests/test_daily_deviation_and_rollover.py`:
- Test that checking a plan with a deviating day (e.g. 2000 kcal vs 2500 kcal target, -20%) writes one deviation record to `weekly.md`.
- Test that checking twice keeps only one record.
- Test that updating the meal plan to normal calories removes the record from `weekly.md`.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run python -m unittest tests/test_daily_deviation_and_rollover.py -v`
Expected: FAIL (no daily deviation recorded in `weekly.md` by `check_meal_plan_csv`).

- [ ] **Step 3: Implement daily grouping and memory recording in `check_meal_plan_csv`**
In `meal_planner/tools/artifacts.py`:
- Group rows by `Date`.
- For each date:
  - Sum `Calories` and `P`.
  - Call `mem_mgr.record_daily_deviation(d, day_cal, daily_calories, day_p, daily_p)`.
  - Track deviating days in `daily_deviations` list.
- Clean up any dates in `weekly.md` that are no longer in the plan.
- Include `daily_deviations` in return dictionary and summarize in check message.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run python -m unittest tests/test_daily_deviation_and_rollover.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add meal_planner/tools/artifacts.py tests/test_daily_deviation_and_rollover.py
git commit -m "feat: integrate daily deviation detection and memory sync in check_meal_plan_csv"
```

---

### Task 3: Automatic Rollover on Start Date Change and Cycle Transition

**Files:**
- Modify: `meal_planner/tools/artifacts.py:96-196`
- Modify: `meal_planner/agent.py`
- Test: `tests/test_daily_deviation_and_rollover.py`

**Interfaces:**
- Consumes: `MemoryManager.rollover_weekly_memory`, `check_meal_plan_csv`
- Produces:
  - Automatic detection and carryover when `update_meal_plan_csv` creates a plan with a new start date or when cycle rolls over.

- [ ] **Step 1: Write failing test for start date change & cycle rollover carryover**
In `tests/test_daily_deviation_and_rollover.py`:
- Test that when an existing plan has a substantial cumulative deficit (e.g. -1500 kcal net over the week), and `update_meal_plan_csv` or `tool_update_plans` creates meals for a new start date (e.g. starting next week), `weekly.md` gets the carryover note: `- [Carried from last week] Net weekly deviation: -1500 kcal, ... carried forward.`.
- Test that if cumulative diff is not substantial (e.g. -100 kcal on a 2500 kcal/day target), no carryover note is created.

- [ ] **Step 2: Run test to verify it fails**
Run: `uv run python -m unittest tests/test_daily_deviation_and_rollover.py -v`
Expected: FAIL

- [ ] **Step 3: Implement start date change detection & rollover in `update_meal_plan_csv`**
In `meal_planner/tools/artifacts.py`:
- In `update_meal_plan_csv`:
  - Inspect `existing_rows` before modifying.
  - Determine `existing_dates = {r.get("Date") for r in existing_rows if r.get("Date")}`.
  - Determine `new_dates = {str(item.get("Date")).strip() for item in updates if item.get("Date")}`.
  - If `existing_dates` exists and `new_dates` is completely disjoint from `existing_dates` and `min(new_dates) > min(existing_dates)` (or new cycle prefix):
    - Calculate previous plan's net difference against targets (`daily_calories`, `daily_p`).
    - Trigger `mem_mgr.rollover_weekly_memory(net_cal, net_p, daily_calories, daily_p)`.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run python -m unittest tests/test_daily_deviation_and_rollover.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite to ensure zero regression**
Run: `uv run python -m unittest discover -s tests -p "test_*.py"`
Expected: All 64+ tests PASS

- [ ] **Step 6: Commit**
```bash
git add meal_planner/tools/artifacts.py meal_planner/agent.py tests/test_daily_deviation_and_rollover.py
git commit -m "feat: add automatic weekly rollover on start date change and cycle transition"
```
