# First Launch Conversational Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable a seamless two-stage first-run experience where the terminal setup wizard configures system settings without generating plans, the first chat conversation prompts the user for nutrition preferences and generates the plans, and subsequent chats immediately assist the user with established plans.

**Architecture:** Add `is_onboarded` flag to `UserProfile`. On fresh launch, `quick_setup_wizard` saves system settings (`timezone`, `currency`, `week_start_day`) with `is_onboarded=False` and zero plan artifacts. `build_system_instruction` adapts dynamically: in the first chat it instructs the Gemini agent to ask for athlete preferences and invoke `tool_onboard_user` + `tool_generate_meal_plan`; in subsequent chats it loads existing preferences and active plans to assist directly.

**Tech Stack:** Python 3.10+, Google ADK, Google GenAI SDK (`gemini-3.8-flash`), standard library `unittest`.

**Spec:** User request: "at the first fresh launch, the setup wizard should run, then open chat (instead of opening straight to chat). At this point the agent does not have any plans, it should ask for preferences and generate plans. When the user initiate a new chat, the preferences and plans should already exist, and the agent can now assist the user with planning requests."

## Global Constraints
- Do not pre-generate meal plan or grocery CSVs during the terminal quick setup wizard.
- On fresh launch, browser must open to ADK Playground with clean unconfigured state.
- In first chat session, agent must proactively ask for athlete preferences and generate plans via tools.
- In subsequent chats, agent must recognize existing preferences/plans and assist directly without re-asking.
- All 51 existing unit tests must remain passing with 100% backward compatibility.

## Review Focus
1. Fresh launch wizard leaves `data/plans/` clean and empty without pre-generating CSVs.
2. `is_onboarded=False` prevents `serve_adk_playground` from auto-generating plans before the user chats.
3. System instruction in first chat directs agent to ask for preferences and call `tool_onboard_user` + `tool_generate_meal_plan`.
4. Subsequent chats detect `is_onboarded=True` and existing plan CSVs, directing agent to assist with planning requests.
5. `tool_onboard_user` marks `is_onboarded=True` and persists to `profile.json`.

---

### Task 1: Update `UserProfile` and `onboarding.py` with `is_onboarded` Flag

**Files:**
- Modify: `meal_planner/models.py`
- Modify: `meal_planner/tools/onboarding.py`
- Test: `tests/test_conversational_onboarding.py`

**Interfaces:**
- Produces: `UserProfile.is_onboarded: bool = True` (defaults to True for backward compatibility in existing tests, set to False on fresh setup wizard).
- Updates: `init_user_profile(..., is_onboarded=...)` and `tool_onboard_user(...)` to persist `is_onboarded=True`.

- [ ] **Step 1: Write failing tests in `tests/test_conversational_onboarding.py`**
  Assert `UserProfile` supports `is_onboarded`, `init_user_profile` persists it, and `tool_onboard_user` sets `is_onboarded=True`.

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest tests/test_conversational_onboarding.py -v`
  Expected: FAIL with attribute error or assertion error.

- [ ] **Step 3: Implement `is_onboarded` in `meal_planner/models.py` and `meal_planner/tools/onboarding.py`**
  Add field `is_onboarded: bool = True` to `UserProfile`.
  Support `is_onboarded` in `init_user_profile` and set `is_onboarded=True` in `tool_onboard_user`.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m unittest tests/test_conversational_onboarding.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  Run: `git add meal_planner/models.py meal_planner/tools/onboarding.py tests/test_conversational_onboarding.py`
  `git commit -m "feat: add is_onboarded flag to UserProfile and onboarding tool"`

---

### Task 2: Refactor `quick_setup_wizard` to System-Only Setup without Plan Pre-Generation

**Files:**
- Modify: `meal_planner/cli.py`
- Test: `tests/test_quick_setup.py`
- Test: `tests/test_conversational_onboarding.py`

**Interfaces:**
- `quick_setup_wizard`: prompts for API key, timezone, currency, week start day; saves `profile.json` with `is_onboarded=False` and empty athlete preferences; does NOT create plans.
- `serve_adk_playground`: checks `if profile and profile.is_onboarded: ensure_weekly_plan_artifacts(...)`.

- [ ] **Step 1: Write failing test in `tests/test_conversational_onboarding.py`**
  Test that `quick_setup_wizard` creates `profile.json` with `is_onboarded=False` and does not generate any plan files in `data/plans/`.

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest tests/test_conversational_onboarding.py -v`
  Expected: FAIL

- [ ] **Step 3: Update `quick_setup_wizard` and `serve_adk_playground` in `meal_planner/cli.py`**
  Streamline wizard to ask API key, timezone, currency, week start day.
  Set `is_onboarded=False`, `bodyweight_kg=0.0`, `target_calories=0.0`, `goal_state=""`, `restrictions=[]`.
  Do not call `ensure_weekly_plan_artifacts` in wizard.
  In `serve_adk_playground`, only call `ensure_weekly_plan_artifacts` if `profile.is_onboarded`.

- [ ] **Step 4: Run tests to verify they pass**
  Run: `python -m unittest tests/test_quick_setup.py tests/test_conversational_onboarding.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  Run: `git commit -am "feat: streamline setup wizard to system config without pre-generating plans"`

---

### Task 3: Dual-Mode System Instructions in `meal_planner/agent.py`

**Files:**
- Modify: `meal_planner/agent.py`
- Test: `tests/test_conversational_onboarding.py`

**Interfaces:**
- `build_system_instruction(user_timezone, data_dir)`:
  - If `not profile or not profile.is_onboarded`: outputs first-chat onboarding prompt directing the agent to greet the user, ask for bodyweight, goal, target calories, and restrictions, and invoke `tool_onboard_user` + `tool_generate_meal_plan`.
  - If `profile and profile.is_onboarded`: outputs active planning prompt with loaded athlete preferences and active artifact paths, directing agent to assist with planning requests.

- [ ] **Step 1: Write failing test in `tests/test_conversational_onboarding.py`**
  Test `build_system_instruction` with `is_onboarded=False` contains onboarding directives, and with `is_onboarded=True` contains active planning directives.

- [ ] **Step 2: Run test to verify it fails**
  Run: `python -m unittest tests/test_conversational_onboarding.py -v`
  Expected: FAIL

- [ ] **Step 3: Implement dual-mode instructions in `meal_planner/agent.py`**
  Check `is_onboarded` and presence of active plan CSV.
  Format system prompt accordingly for first-chat vs subsequent chats.
  Ensure `tool_onboard_user` updates `is_onboarded=True`.

- [ ] **Step 4: Run test to verify it passes**
  Run: `python -m unittest tests/test_conversational_onboarding.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  Run: `git commit -am "feat: dual-mode agent system instruction for first-chat onboarding vs subsequent planning"`

---

### Task 4: Full Suite Verification & End-to-End Integration Test

**Files:**
- Test: `tests/test_conversational_onboarding.py`
- Run: all tests in `tests/`

- [ ] **Step 1: Add end-to-end integration test in `tests/test_conversational_onboarding.py`**
  Simulate:
  1. Fresh launch setup -> `is_onboarded=False`, 0 plans.
  2. First chat prompt generation -> instructs onboarding.
  3. User provides preferences -> agent invokes `tool_onboard_user` and `tool_generate_meal_plan` -> `is_onboarded=True`, plan files exist.
  4. Subsequent chat prompt generation -> recognizes onboarded athlete with active plans, assists directly.

- [ ] **Step 2: Run entire test suite**
  Run: `python -m unittest discover -s tests -p "test_*.py" -v`
  Expected: All tests pass with 0 failures.

- [ ] **Step 3: Commit and verify git clean**
  Run: `git commit -am "test: verify end-to-end first launch and subsequent chat lifecycle"`
