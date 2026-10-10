# Two-Tier Memory & Dated Weekly Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Equip the Meal Planner Agent with a two-tier memory system (short-term weekly vs. long-term monthly/yearly) with relevance filtering, benchmarked startup hydration, per-week dated meal plan files (`YYMMDD_meal_plan.csv`), and a concise, artifact-pointing conversational style.

**Architecture:** A `MemoryManager` persists `data/memory/weekly.json` and `data/memory/long_term.json`, filtering out trivial chatter. At startup, it benchmarks loading each file and injects the context into the Gemini system prompt. The plan generator manages isolated weekly files (`data/plans/YYMMDD_meal_plan.csv`), checking existence before generating. The agent's prompt strictly mandates concise replies that point to file artifacts rather than dumping raw tables unless explicitly requested.

**Tech Stack:** Python 3.13, `time.perf_counter` (microsecond resolution benchmarking), `unittest`, JSON / CSV storage.

**Spec:** Current conversation specifications and [`meal-planner-requirements.md`](meal-planner-requirements.md).

## Global Constraints

- **Memory Discrimination:** Ephemeral or trivial conversational chatter (greetings, confirmations, acknowledgments) must never be saved to memory files.
- **Short-Term (Weekly) Scope:** Stored in `data/memory/weekly.json`. Holds current week's deviations, temporary physical constraints, and roll-overs. Capped and easily rolled over.
- **Long-Term (Monthly/Yearly) Scope:** Stored in `data/memory/long_term.json`. Holds permanent athlete preferences, dietary milestones, and macro adjustments. Deduplicated.
- **Dated File Naming:** Weekly files must be named using `YYMMDD` of the cycle start date (e.g. `data/plans/261010_meal_plan.csv` and `data/plans/261010_grocery_list.csv`).
- **Startup Transparency:** At script startup, print the exact list of hydrated files and their respective load times in milliseconds (`X.X ms`).
- **Conversational Precision:** Agent must be concise, only discuss immediate changes at hand, point to artifact paths (e.g. `data/plans/261010_meal_plan.csv`), and only print raw logs in chat when explicitly asked.

## Review Focus

1. **Trivial Chatter Leakage:** Notes like `"ok"`, `"thanks"`, `"sounds good"` must be rejected by the memory filter and return an ignore status without polluting memory files.
2. **Weekly Rollover Isolation:** Generating a plan for a new week must not contaminate or bloat the new week's plan with past weeks' completed meals.
3. **Invalid Date / Timezone Week Prefix:** Calculating the Saturday `YYMMDD` anchor across month and year boundaries (e.g., Dec 31 to Jan 2) must format the date correctly.
4. **Benchmark Accuracy:** Hydration benchmarking must measure actual disk read latency using `time.perf_counter()`, returning realistic milliseconds.
5. **System Instruction Prompt Bloat:** Formatted memory context injected into the system prompt must truncate or prune oversized lists so token usage remains efficient.

---

### Task 1: Two-Tier Memory Manager & Filtering Engine

**Files:**
- Create: `meal_planner/tools/memory.py`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: None (new module)
- Produces:
  - `MemoryManager(data_dir: str)`
  - `add_memory_note(data_dir: str, note: str, tier: str) -> dict`
  - `get_memory_context(data_dir: str) -> dict`
  - `hydrate_memory(data_dir: str) -> tuple[list[tuple[str, str, float]], float]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory.py
import unittest
import os
import shutil
from meal_planner.tools.memory import MemoryManager, add_memory_note, get_memory_context

class TestMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_memory_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_memory_discrimination_and_storage(self):
        mgr = MemoryManager(self.test_dir)

        # Review Focus 1: Trivial chatter must be ignored
        res_trivial = mgr.add_note("Okay sounds good thanks!", tier="weekly")
        self.assertEqual(res_trivial["status"], "ignored")

        # Meaningful weekly note
        res_weekly = mgr.add_note("Feeling lower back fatigue this week, keep Friday dinner light", tier="weekly")
        self.assertEqual(res_weekly["status"], "saved")
        self.assertEqual(res_weekly["tier"], "weekly")

        # Meaningful long-term note
        res_long = mgr.add_note("Severe intolerance to dairy whey, only ON Whey tolerated", tier="long_term")
        self.assertEqual(res_long["status"], "saved")
        self.assertEqual(res_long["tier"], "long_term")

        # Check retrieval context
        ctx = mgr.get_context()
        self.assertEqual(len(ctx["weekly"]), 1)
        self.assertEqual(len(ctx["long_term"]), 1)

    def test_startup_hydration_benchmarking(self):
        mgr = MemoryManager(self.test_dir)
        mgr.add_note("Tendon stiffness this week", tier="weekly")
        
        records, total_ms = mgr.hydrate()
        self.assertGreater(len(records), 0)
        self.assertGreaterEqual(total_ms, 0.0)
        file_paths = [r[1] for r in records]
        self.assertTrue(any("weekly.json" in fp for fp in file_paths))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_memory.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.memory'`

- [ ] **Step 3: Implement `meal_planner/tools/memory.py`**

Implement `MemoryManager`:
- Paths: `data/memory/weekly.json` and `data/memory/long_term.json`.
- Heuristic filter: ignores short trivial phrases (< 8 chars, or matching keywords `["thanks", "ok", "okay", "cool", "sounds good", "hello", "hi", "bye"]`).
- Saves timestamped entries: `{"timestamp": "YYYY-MM-DD", "note": str}`.
- Deduplication: checks if note is already present.
- `hydrate()`: reads `profile.json`, `weekly.json`, `long_term.json`, and any current plan, timing each with `time.perf_counter()`, returning list of `(label, path, elapsed_ms)` and `total_ms`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_memory.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/memory.py tests/test_memory.py
git commit -m "feat(memory): implement two-tier memory manager with filtering and hydration benchmarking"
```

---

### Task 2: Dated Weekly Plan Management (`YYMMDD` Naming)

**Files:**
- Modify: `meal_planner/tools/meal_generator.py`
- Modify: `meal_planner/tools/grocery_planner.py`
- Test: `tests/test_dated_artifacts.py`

**Interfaces:**
- Consumes: `UserProfile`, `generate_weekly_plan()`
- Produces:
  - `get_current_cycle_prefix(tz_name: str, reference_dt: datetime | None = None) -> str` (e.g. `261010`)
  - `ensure_weekly_plan_artifacts(profile: UserProfile, data_dir: str, reference_dt: datetime | None = None) -> tuple[str, str, bool]` (returns `(plan_path, grocery_path, newly_created)`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dated_artifacts.py
import unittest
import os
import shutil
from datetime import datetime
import zoneinfo
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import (
    get_current_cycle_prefix,
    ensure_weekly_plan_artifacts
)

class TestDatedArtifacts(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_dated_data"
        os.makedirs(self.test_dir, exist_ok=True)
        self.profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_cycle_prefix_calculation(self):
        # Reference date: Thursday 2026-10-15
        # The Saturday of this cycle was 2026-10-10 -> YYMMDD is "261010"
        ref = datetime(2026, 10, 15, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        prefix = get_current_cycle_prefix("Europe/Brussels", reference_dt=ref)
        self.assertEqual(prefix, "261010")

    def test_ensure_weekly_plan_creates_and_reuses(self):
        ref = datetime(2026, 10, 15, 12, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        # First call: should create 261010_meal_plan.csv
        plan_csv, grocery_csv, created = ensure_weekly_plan_artifacts(
            self.profile, self.test_dir, reference_dt=ref
        )
        self.assertTrue(created)
        self.assertTrue(os.path.exists(plan_csv))
        self.assertIn("261010_meal_plan.csv", plan_csv)
        self.assertTrue(os.path.exists(grocery_csv))
        self.assertIn("261010_grocery_list.csv", grocery_csv)

        # Second call: should detect existing file and NOT recreate
        plan_csv2, grocery_csv2, created2 = ensure_weekly_plan_artifacts(
            self.profile, self.test_dir, reference_dt=ref
        )
        self.assertFalse(created2)
        self.assertEqual(plan_csv, plan_csv2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_dated_artifacts.py`  
Expected: FAIL with `ImportError: cannot import name 'get_current_cycle_prefix'`

- [ ] **Step 3: Implement `get_current_cycle_prefix` and `ensure_weekly_plan_artifacts`**

Implement in `meal_planner/tools/meal_generator.py`:
- `get_current_cycle_prefix(tz_name: str, reference_dt: datetime | None = None) -> str`: Finds the starting Saturday of the current 7-day cycle. Formats as `%y%m%d`.
- `ensure_weekly_plan_artifacts(profile: UserProfile, data_dir: str, reference_dt: datetime | None = None)`:
  - Computes prefix (e.g. `261010`).
  - Checks if `data_dir/plans/{prefix}_meal_plan.csv` exists.
  - If exists, returns paths and `created=False`.
  - If not, calls `generate_weekly_plan()`, saves to `data_dir/plans/{prefix}_meal_plan.csv`, generates split groceries to `data_dir/plans/{prefix}_grocery_list.csv`, and returns `created=True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_dated_artifacts.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/meal_generator.py tests/test_dated_artifacts.py
git commit -m "feat(artifacts): implement dated weekly plan management with YYMMDD naming"
```

---

### Task 3: Agent Integration, Memory Tools & Precision Communication Persona

**Files:**
- Modify: `meal_planner/agent.py`
- Modify: `meal_planner/cli.py`
- Test: `tests/test_memory_agent_integration.py`

**Interfaces:**
- Consumes: `MemoryManager`, `ensure_weekly_plan_artifacts`
- Produces:
  - `tool_save_memory_note(note: str, tier: str) -> str`
  - Updated `build_system_instruction(user_timezone: str, data_dir: str) -> str`
  - Startup hydration banner in `cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_memory_agent_integration.py
import unittest
import os
import shutil
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.memory import MemoryManager

class TestMemoryAgentIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_agent_mem"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_memory_tool_and_system_instruction(self):
        tools = get_agent_tools(self.test_dir)
        tools_map = {t.__name__: t for t in tools}
        self.assertIn("tool_save_memory_note", tools_map)

        # Save meaningful note
        msg = tools_map["tool_save_memory_note"]("User prefers higher sodium broth in Phở for lifting", "long_term")
        self.assertIn("Saved to long-term memory", msg)

        # System instruction must include the memory context and artifact-pointing rule
        prompt = build_system_instruction("Europe/Brussels", data_dir=self.test_dir)
        self.assertIn("higher sodium broth", prompt)
        self.assertIn("POINT TO THE ARTIFACT FILE", prompt)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_memory_agent_integration.py`  
Expected: FAIL with `KeyError: 'tool_save_memory_note'`

- [ ] **Step 3: Implement memory tool and precision instructions in `agent.py` and `cli.py`**

In `meal_planner/agent.py`:
- Add `tool_save_memory_note(note: str, tier: str = "weekly") -> str`.
- Update `build_system_instruction`:
  - Load and inject short-term weekly and long-term memory items.
  - Enforce communication style:
    1. Precision & conciseness: Only discuss immediate adjustments/preferences.
    2. Artifact pointing: When asked about schedule or groceries, state the exact path (e.g. `data/plans/261010_meal_plan.csv`). Do not print large tables unless asked.
    3. Filter out trivial notes from memory.
In `meal_planner/cli.py`:
- On startup, execute `MemoryManager.hydrate()`, printing loaded files and latency in `X.X ms`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_memory_agent_integration.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/agent.py meal_planner/cli.py tests/test_memory_agent_integration.py
git commit -m "feat(agent): bind memory tools and enforce concise artifact-pointing persona"
```

---

### Task 4: Full Test Suite & End-to-End Verification

**Files:**
- Modify: `README.md`
- Test: Full test suite

- [ ] **Step 1: Run full test suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`  
Expected: All tests PASS with zero errors.

- [ ] **Step 2: Update `README.md` with memory system and dated files documentation**

Document:
- Short-term vs. Long-term memory structure.
- Startup memory hydration and millisecond benchmarks.
- Dated weekly files (`data/plans/YYMMDD_meal_plan.csv`).
- Conversational precision guidelines.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document two-tier memory architecture and dated weekly artifact naming"
```
