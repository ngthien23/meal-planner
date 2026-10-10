# Simplify Memory to Markdown & Streamline Agent Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor memory storage to plain Markdown text files without timestamps, remove local price and nutrition fact tracking in favor of LLM estimation and web search, and add the three train-of-thought meal planning guidelines to the agent prompt.

**Architecture:** Replace JSON memory serialization with plain `.md` bulleted text files (`long_term.md` and `weekly.md`) without timestamps. Remove `prices.csv`, `tool_log_price_update`, `tool_add_food_item`, `tool_get_analytics`, and `tool_lookup_food_catalog` from the agent toolbox. Embed explicit chain-of-thought guidelines for meal planning (budget consideration, balancing needs/preferences, and nutrition nuances like raw vs. cooked and bone-in/skin-on) directly into the agent system instructions.

**Tech Stack:** Python 3.13, Google ADK / Gemini API, unittest

**Spec:** User directives from 2026-10-10: simplify memory to markdown without timestamps, eliminate nutrition facts and price bookkeeping, and embed 3-point meal planning train of thoughts.

## Global Constraints
- Memory files must be Markdown (`weekly.md` and `long_term.md`) without timestamps, formatted as simple readable bullet points (`- Note text`).
- No local `prices.csv` or rigid nutrition fact database required for agent reasoning; LLM uses internal estimation and web search.
- System prompt must guide the agent through the 3 train-of-thought principles: 1) consider budget, 2) balance needs and preferences, 3) nutrition nuances (raw vs cooked, bone-in/skin-on).
- All unit and integration tests must pass cleanly.

## Review Focus
1. Memory persistence: notes are cleanly saved and retrieved from `weekly.md` and `long_term.md` without timestamps or JSON syntax.
2. Memory deduplication: identical notes are not duplicated in the markdown files.
3. Clean startup: starting with an empty `data/` directory does not crash on missing `prices.csv`.
4. Tool suite cleanliness: `get_agent_tools()` only exposes bookkeeping, macro reference, schedule, and artifact manipulation tools.
5. System instruction completeness: the 3-step meal planning thought process is clearly articulated in the system prompt.

---

### Task 1: Refactor MemoryManager to Plain Markdown (.md) Without Timestamps

**Files:**
- Modify: `meal_planner/tools/memory.py:18-150`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `data_dir: str`, `note: str`, `tier: str`
- Produces: `MemoryManager.add_note(...) -> dict`, `MemoryManager.get_context() -> dict[str, list[str]]`, `MemoryManager.clear_weekly_memory()`, `MemoryManager.hydrate(...)` reading and writing `.md` files.

- [ ] **Step 1: Write tests for Markdown memory storage and timestamp-free retrieval**
Update `tests/test_memory.py` to verify notes are written as `- <note>` into `weekly.md` and `long_term.md`, that timestamps are absent, and that `hydrate` checks `.md` files.

- [ ] **Step 2: Run test to verify failure**
Run: `uv run python -m unittest tests/test_memory.py -v`
Expected: FAIL due to `.json` file expectations.

- [ ] **Step 3: Implement Markdown storage in `meal_planner/tools/memory.py`**
Change `weekly_path` to `weekly.md` and `long_term_path` to `long_term.md`. Read and write clean `- note` bullet points without timestamps. Provide fallback support for reading legacy `.json` files if present.

- [ ] **Step 4: Run test to verify it passes**
Run: `uv run python -m unittest tests/test_memory.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add meal_planner/tools/memory.py tests/test_memory.py
git commit -m "refactor: store memories in markdown files without timestamps"
```

---

### Task 2: Remove Local Price and Nutrition Fact Tracking

**Files:**
- Modify: `meal_planner/tools/tracker.py:7-58`
- Modify: `meal_planner/agent.py:755-780`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: `init_bookkeeping_artifacts(data_dir: str)`
- Produces: Cleaned initialization without `prices.csv`. Removed `tool_log_price_update`, `tool_add_food_item`, `tool_get_analytics`, and `tool_lookup_food_catalog` from agent tool suite.

- [ ] **Step 1: Write/Update test in `tests/test_tracker.py` and `tests/test_add_foods.py`**
Update `tests/test_tracker.py` to test meal consumption logging without requiring `prices.csv`. Ensure any tests asserting `prices.csv` are updated or refactored.

- [ ] **Step 2: Run test to verify status**
Run: `uv run python -m unittest tests/test_tracker.py -v`

- [ ] **Step 3: Update `meal_planner/tools/tracker.py` and `meal_planner/agent.py`**
- In `meal_planner/tools/tracker.py`, remove automatic generation of `prices.csv` from `init_bookkeeping_artifacts`. Keep `record_price` as a lightweight no-op or optional helper if needed.
- In `meal_planner/agent.py`, remove `tool_log_price_update`, `tool_add_food_item`, `tool_get_analytics`, and `tool_lookup_food_catalog` from `get_agent_tools()`. Remove `prices.csv` logging and receipt scanning instructions from `build_system_instruction`.

- [ ] **Step 4: Run tests to verify pass**
Run: `uv run python -m unittest discover -s tests -p "test_*.py"`

- [ ] **Step 5: Commit**
```bash
git add meal_planner/tools/tracker.py meal_planner/agent.py tests/test_tracker.py
git commit -m "refactor: remove price and nutrition fact tracking tools"
```

---

### Task 3: Embed 3-Step Train of Thought Meal Planning Guidelines into Agent Prompt

**Files:**
- Modify: `meal_planner/agent.py:110-210`
- Test: `tests/test_streamlined_agent_flow.py`

**Interfaces:**
- Consumes: System prompt generation `build_system_instruction(user_timezone: str, data_dir: str) -> str`
- Produces: Updated system prompt containing explicit instructions for:
  1. Base plan around protein stock and needs.
  2. Step 1: Consider the budget (use LLM internal intuition and web search, not local price tracking).
  3. Step 2: Allocate budget by roughly balancing needs and preferences (protein foundation first, Vietnamese dishes, broth/noodles, rough macros, whey top-up).
  4. Step 3: Be aware of nutrition nuances (raw vs cooked yields, bone-in/skin-on vs boneless/skinless cuts, trimmings).

- [ ] **Step 1: Update system instructions in `meal_planner/agent.py`**
Add the 3-step train of thought directly under `CORE ATHLETE RULES & PLANNING PRINCIPLES` in `build_system_instruction`.

- [ ] **Step 2: Add test asserting prompt includes the 3-step train of thought**
Add test in `tests/test_streamlined_agent_flow.py` verifying that `build_system_instruction` includes budget consideration, needs vs preferences balancing, and raw vs cooked / bone-in nuances.

- [ ] **Step 3: Run full test suite**
Run: `uv run python -m unittest discover -s tests -p "test_*.py"`
Expected: All tests pass.

- [ ] **Step 4: Commit**
```bash
git add meal_planner/agent.py tests/test_streamlined_agent_flow.py
git commit -m "feat: embed 3-step meal planning train of thought into agent prompt"
```

---

### Task 4: Final Verification, Clean Slate, and Remote Push

**Files:**
- Check: All files clean, `data/` empty
- Verify: Full test suite 100% green

- [ ] **Step 1: Run full test suite**
Run: `uv run python -m unittest discover -s tests -p "test_*.py"`

- [ ] **Step 2: Verify `data/` is empty**
Ensure no leftover artifact files remain in `data/`.

- [ ] **Step 3: Push commits to `origin/main`**
Run: `git push origin main`
