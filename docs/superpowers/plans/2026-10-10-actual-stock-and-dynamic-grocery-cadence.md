# Actual Stock Bookkeeping & Dynamic Grocery Cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement actual fridge stock bookkeeping, chat-time catch-up reconciliation, retrospective past meal adjustments with gentle calorie rollover, and dynamic floating grocery runs that adapt to on-hand protein and cravings.

**Architecture:** An `inventory.json` file tracks actual vs. assumed stock and carried calorie debt. On each chat turn, an inventory reconciliation engine catches up past meals and planned shopping based on anchor times (08:00, 12:30, 19:00). A craving/stock exhaustion engine allocates on-hand protein consecutively across lunch (solid) and dinner (chicken soup) until stock hits 0, and a floating cadence solver shifts upcoming grocery runs to start on the exact day of inventory exhaustion ($D_{\text{exhaust}}$) at 3–4 day intervals.

**Tech Stack:** Python 3.13, Google ADK, standard library (`zoneinfo`, `datetime`, `json`, `csv`, `math`), `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-10-actual-stock-bookkeeping-and-dynamic-grocery-cadence-design.md`](file:///C:/Users/ngthien/Downloads/Repositories/meal-planner/docs/superpowers/specs/2026-10-10-actual-stock-bookkeeping-and-dynamic-grocery-cadence-design.md)

## Global Constraints
- Target daily protein, fat, and calories must be preserved using existing formulas in `macro_calculator.py`.
- No 24/7 background timer daemons; stock catch-up executes at conversation turn time.
- All CSV artifacts (`{prefix}_meal_plan.csv`, `{prefix}_batch_cook.csv`, `{prefix}_grocery_list.csv`) must stay strictly formatted with integer gram rounding and date-only run names.
- Eating out logs macros toward daily intake but never deducts fridge stock.
- Carried calorie debt from skipped meals is capped at +200 kcal/day and +15g protein/day to protect digestion.
- Use natural, standard English throughout tools, outputs, and documentation.

## Review Focus
1. **Unbought Perishable Purge:** When on-hand protein is reported before a scheduled grocery run, unbought perishable meats from that run must be pruned so the user does not buy duplicate meat.
2. **Stock Reversal on Skipped / Eaten Out Meals:** Retrospectively reporting a skipped or eaten out meal must restore ingredients to `inventory.json` so home food isn't marked as lost.
3. **Anchor Boundary Edges:** At 12:29 Lunch is targeted; at 12:31 Lunch is targeted if unlogged, but after cutoff 14:30 Dinner is targeted.
4. **Dinner Texture Compromise:** Consecutively scheduled on-hand chicken for dinner slots must be prepared as chicken soup/broth rather than dry solid cuts.
5. **Floating Run Window:** When runs shift to $D_{\text{exhaust}}$, grocery runs must not exceed 72–96h fresh meat shelf-life limits.

---

### Task 1: Inventory Models & Stock State Management

**Files:**
- Create: `meal_planner/tools/inventory.py`
- Modify: `meal_planner/models.py`
- Test: `tests/test_inventory_state.py`

**Interfaces:**
- Produces:
  - `InventoryItem`: dataclass with `food_id: str`, `name: str`, `quantity_g: float`, `status: str` (`"actual"` | `"assumed"`), `source: str`, `purchased_date: str`
  - `InventoryState`: dataclass with `last_reconciled_at: Optional[str]`, `carried_calories: float`, `carried_protein_g: float`, `items: list[InventoryItem]`
  - `load_inventory_state(data_dir: str) -> InventoryState`
  - `save_inventory_state(data_dir: str, state: InventoryState) -> None`
  - `record_actual_stock(data_dir: str, items: list[dict], clear_unbought_run_meats: bool = True) -> InventoryState`

- [ ] **Step 1: Write the failing test for inventory loading, saving, and actual stock recording**

```python
# tests/test_inventory_state.py
import unittest, os, shutil, tempfile
from meal_planner.tools.inventory import (
    InventoryState, InventoryItem, load_inventory_state, save_inventory_state, record_actual_stock
)

class TestInventoryState(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_save_and_load_inventory(self):
        state = InventoryState(
            last_reconciled_at="2026-10-10T18:00:00+02:00",
            carried_calories=150.0,
            carried_protein_g=12.0,
            items=[InventoryItem("chicken_wings", "Chicken Wings", 500.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)
        loaded = load_inventory_state(self.test_dir)
        self.assertEqual(loaded.carried_calories, 150.0)
        self.assertEqual(len(loaded.items), 1)
        self.assertEqual(loaded.items[0].food_id, "chicken_wings")
        self.assertEqual(loaded.items[0].status, "actual")

    def test_record_actual_stock_overwrites_matching_and_sets_actual(self):
        state = record_actual_stock(self.test_dir, [
            {"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 500.0},
            {"food_id": "chicken_thigh_quarter", "name": "Chicken Thigh Quarter", "quantity_g": 500.0}
        ])
        self.assertEqual(len(state.items), 2)
        self.assertTrue(all(item.status == "actual" for item in state.items))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_inventory_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.inventory'`

- [ ] **Step 3: Implement `meal_planner/tools/inventory.py` and data structures in `models.py`**

Implement `InventoryItem`, `InventoryState`, `load_inventory_state`, `save_inventory_state`, and `record_actual_stock`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_inventory_state.py -v`
Expected: PASS (2/2 tests passing)

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/inventory.py meal_planner/models.py tests/test_inventory_state.py
git commit -m "feat: add inventory state management and actual stock tracking"
```

---

### Task 2: Chat-Time Catch-Up & Implicit Consumption Engine

**Files:**
- Modify: `meal_planner/tools/inventory.py`
- Test: `tests/test_inventory_reconciliation.py`

**Interfaces:**
- Consumes:
  - `load_inventory_state`, `save_inventory_state` from `meal_planner.tools.inventory`
  - `get_current_cycle_prefix` from `meal_planner.tools.meal_generator`
- Produces:
  - `reconcile_inventory_state(data_dir: str, current_dt: datetime, user_tz: str = "Europe/Brussels") -> tuple[InventoryState, list[str]]`
    - Returns updated `InventoryState` and a list of actions performed (e.g. `["Assumed 1000g chicken breast purchased from Saturday Run", "Assumed Breakfast consumed (deducted 40g oats, 250ml milk, 30g whey)"]`).

- [ ] **Step 1: Write the failing test for chat-time catch-up**

```python
# tests/test_inventory_reconciliation.py
import unittest, os, shutil, tempfile
from datetime import datetime
import zoneinfo
from meal_planner.tools.inventory import (
    InventoryState, InventoryItem, save_inventory_state, reconcile_inventory_state
)
from meal_planner.models import UserProfile
from meal_planner.tools.onboarding import init_user_profile

class TestInventoryReconciliation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True
        })
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_chat_time_catchup_advances_past_meals_and_deducts_stock(self):
        tz = zoneinfo.ZoneInfo("Europe/Brussels")
        # Simulate state last reconciled at 07:00
        state = InventoryState(
            last_reconciled_at=datetime(2026, 10, 10, 7, 0, tzinfo=tz).isoformat(),
            items=[InventoryItem("chicken_breast", "Chicken Breast", 1000.0, "actual", "user_report", "2026-10-10")]
        )
        save_inventory_state(self.test_dir, state)

        # Chat happens at 15:00 on Saturday (Breakfast cutoff 10:00 and Lunch cutoff 14:30 have passed)
        chat_dt = datetime(2026, 10, 10, 15, 0, tzinfo=tz)
        new_state, actions = reconcile_inventory_state(self.test_dir, current_dt=chat_dt, user_tz="Europe/Brussels")
        self.assertEqual(new_state.last_reconciled_at, chat_dt.isoformat())
        self.assertTrue(any("consumed" in a.lower() for a in actions))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_inventory_reconciliation.py -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile_inventory_state'`

- [ ] **Step 3: Implement `reconcile_inventory_state` in `meal_planner/tools/inventory.py`**

Implement anchor windows (Breakfast 08:00 cutoff 10:00, Lunch 12:30 cutoff 14:30, Dinner 19:00 cutoff 21:00), grocery run integration ($\le current\_date$ tagged `assumed`), past slot deduction, and timestamp advancement.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_inventory_reconciliation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/inventory.py tests/test_inventory_reconciliation.py
git commit -m "feat: add chat-time catch-up reconciliation for implicit consumption"
```

---

### Task 3: Retrospective Past Meal Adjustments & Missed Calories Rollover

**Files:**
- Modify: `meal_planner/tools/inventory.py`
- Modify: `meal_planner/tools/adaptation.py`
- Test: `tests/test_retrospective_adjustments.py`

**Interfaces:**
- Consumes:
  - `load_inventory_state`, `save_inventory_state`
  - `log_meal_consumption` from `meal_planner.tools.tracker`
- Produces:
  - `reconcile_past_meal_deviation(data_dir: str, target_date: str, slot_name: str, deviation_type: str, eaten_description: Optional[str] = None, actual_calories: Optional[float] = None, actual_protein_g: Optional[float] = None, roll_over_difference: bool = True, user_tz: str = "Europe/Brussels") -> dict`

- [ ] **Step 1: Write the failing test for skipped meals restoring stock and rolling over calories**

```python
# tests/test_retrospective_adjustments.py
import unittest, os, shutil, tempfile
from meal_planner.tools.inventory import (
    InventoryState, InventoryItem, save_inventory_state, load_inventory_state, reconcile_past_meal_deviation
)
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts

class TestRetrospectiveAdjustments(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True
        })
        ensure_weekly_plan_artifacts(self.profile, self.test_dir)
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_skipped_breakfast_restores_stock_and_rolls_over_deficit(self):
        # 1. State where ingredients were deducted
        state = InventoryState(last_reconciled_at="2026-10-10T12:00:00+02:00", items=[])
        save_inventory_state(self.test_dir, state)

        # 2. User reports skipping breakfast
        result = reconcile_past_meal_deviation(
            self.test_dir, target_date="2026-10-10", slot_name="breakfast",
            deviation_type="skipped", roll_over_difference=True
        )
        self.assertTrue(result["success"])
        self.assertGreater(result["restored_items_count"], 0)
        self.assertGreater(result["carried_calories"], 0)

        # Verify stock was restored in inventory.json
        inv = load_inventory_state(self.test_dir)
        self.assertGreater(inv.carried_calories, 0)
        self.assertTrue(any(i.quantity_g > 0 for i in inv.items))

    def test_eating_out_does_not_deduct_home_stock(self):
        result = reconcile_past_meal_deviation(
            self.test_dir, target_date="2026-10-10", slot_name="lunch",
            deviation_type="eat_out", actual_calories=800.0, actual_protein_g=40.0
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["actual_calories"], 800.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_retrospective_adjustments.py -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile_past_meal_deviation'`

- [ ] **Step 3: Implement `reconcile_past_meal_deviation`**

Implement reverse stock restoration into `inventory.json`, macro logging, deficit calculation, and capped rollover distribution (+200 kcal/day and +15g P/day).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_retrospective_adjustments.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/inventory.py meal_planner/tools/adaptation.py tests/test_retrospective_adjustments.py
git commit -m "feat: add retrospective meal adjustments with stock reversal and calorie rollover"
```

---

### Task 4: Next-Meal Craving Targeting & Consecutive Stock Exhaustion Engine

**Files:**
- Modify: `meal_planner/tools/adaptation.py`
- Modify: `meal_planner/tools/meal_generator.py`
- Test: `tests/test_cravings_and_stock_exhaustion.py`

**Interfaces:**
- Produces:
  - `resolve_next_meal_slot(current_dt: datetime) -> tuple[str, str]` (e.g. `("2026-10-10", "dinner")`)
  - `apply_craving_and_exhaust_stock(data_dir: str, craving_dish: str, on_hand_proteins: list[dict], current_dt: datetime, cooking_style: str = "air_fried", is_extra_snack: bool = False, user_tz: str = "Europe/Brussels") -> dict`
    - Returns `{ "craving_slot": (date, slot), "exhaustion_schedule": list[dict], "exhaustion_date": str, "next_grocery_date": str }`

- [ ] **Step 1: Write the failing test for craving placement and consecutive lunch/dinner chicken soup exhaustion**

```python
# tests/test_cravings_and_stock_exhaustion.py
import unittest, os, shutil, tempfile
from datetime import datetime
import zoneinfo
from meal_planner.tools.adaptation import apply_craving_and_exhaust_stock, resolve_next_meal_slot
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts

class TestCravingsAndStockExhaustion(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tz = zoneinfo.ZoneInfo("Europe/Brussels")
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True
        })
        ensure_weekly_plan_artifacts(self.profile, self.test_dir)
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_next_meal_slot_resolution_anchors(self):
        # 11:00 -> Lunch today
        self.assertEqual(resolve_next_meal_slot(datetime(2026, 10, 10, 11, 0, tzinfo=self.tz)), ("2026-10-10", "lunch"))
        # 15:00 -> Dinner tonight
        self.assertEqual(resolve_next_meal_slot(datetime(2026, 10, 10, 15, 0, tzinfo=self.tz)), ("2026-10-10", "dinner"))
        # 21:30 -> Breakfast tomorrow
        self.assertEqual(resolve_next_meal_slot(datetime(2026, 10, 10, 21, 30, tzinfo=self.tz)), ("2026-10-11", "breakfast"))

    def test_air_fry_chicken_craving_and_consecutive_chicken_soup_dinner(self):
        # Saturday 15:00 -> craving targets Saturday Dinner
        cur_dt = datetime(2026, 10, 10, 15, 0, tzinfo=self.tz)
        res = apply_craving_and_exhaust_stock(
            self.test_dir,
            craving_dish="Air Fried Chicken",
            on_hand_proteins=[
                {"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 500.0},
                {"food_id": "chicken_thigh_quarter", "name": "Chicken Thigh Quarter", "quantity_g": 500.0}
            ],
            current_dt=cur_dt,
            user_tz="Europe/Brussels"
        )
        self.assertEqual(res["craving_slot"], ("2026-10-10", "dinner"))
        # Subsequent Sunday lunch is solid, Sunday dinner is chicken soup
        meals = res["exhaustion_schedule"]
        self.assertTrue(any("soup" in m["dish"].lower() for m in meals if m["slot"] == "dinner"))
        self.assertIsNotNone(res["exhaustion_date"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_cravings_and_stock_exhaustion.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_craving_and_exhaust_stock'`

- [ ] **Step 3: Implement `apply_craving_and_exhaust_stock` and `resolve_next_meal_slot`**

Implement anchor slot resolution, swap craving slot with raw protein solving, consecutively schedule remaining cuts with lunch (solid) and dinner (chicken soup/broth), and compute $D_{\text{exhaust}}$.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_cravings_and_stock_exhaustion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/adaptation.py meal_planner/tools/meal_generator.py tests/test_cravings_and_stock_exhaustion.py
git commit -m "feat: add next-meal craving resolution and consecutive lunch/dinner chicken soup stock exhaustion"
```

---

### Task 5: Dynamic Floating Grocery Cadence Solver

**Files:**
- Modify: `meal_planner/tools/grocery_planner.py`
- Modify: `meal_planner/tools/meal_generator.py`
- Test: `tests/test_dynamic_grocery_cadence.py`

**Interfaces:**
- Produces:
  - `reschedule_floating_grocery_runs(data_dir: str, exhaustion_date: str, profile: UserProfile) -> dict`
    - Drops runs before `exhaustion_date`.
    - Schedules next run on `exhaustion_date`.
    - Spaces future runs at 3–4 day freshness intervals.
    - Updates `{prefix}_grocery_list.csv` and `{prefix}_batch_cook.csv`.

- [ ] **Step 1: Write the failing test for dynamic grocery cadence shift**

```python
# tests/test_dynamic_grocery_cadence.py
import unittest, os, shutil, tempfile
from meal_planner.tools.grocery_planner import reschedule_floating_grocery_runs
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts, get_current_cycle_prefix
import csv

class TestDynamicGroceryCadence(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True,
            "week_start_day": "Saturday"
        })
        ensure_weekly_plan_artifacts(self.profile, self.test_dir)
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_reschedule_shifts_next_run_to_exhaustion_date(self):
        # On-hand chicken lasts until Tuesday (2026-10-13)
        res = reschedule_floating_grocery_runs(self.test_dir, exhaustion_date="2026-10-13", profile=self.profile)
        self.assertEqual(res["next_run_date"], "2026-10-13")
        self.assertEqual(res["next_run_day"], "Tuesday")

        prefix = get_current_cycle_prefix(self.profile.timezone, week_start_day="Saturday")
        grocery_csv = os.path.join(self.test_dir, "plans", f"{prefix}_grocery_list.csv")
        with open(grocery_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            runs = {row["Run"] for row in reader}
            self.assertIn("Tuesday", runs)
            self.assertNotIn("Saturday", runs)  # Pre-exhaustion run was dropped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_dynamic_grocery_cadence.py -v`
Expected: FAIL with `ImportError: cannot import name 'reschedule_floating_grocery_runs'`

- [ ] **Step 3: Implement `reschedule_floating_grocery_runs` in `grocery_planner.py`**

Implement run pruning, placing next run on $D_{\text{exhaust}}$, rolling 3–4 day fresh meat window generation, and updating `{prefix}_grocery_list.csv` and `{prefix}_batch_cook.csv`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_dynamic_grocery_cadence.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/grocery_planner.py meal_planner/tools/meal_generator.py tests/test_dynamic_grocery_cadence.py
git commit -m "feat: add dynamic floating grocery cadence solver"
```

---

### Task 6: Agent Tools & ADK System Instruction Integration

**Files:**
- Modify: `meal_planner/agent.py`
- Test: `tests/test_agent_stock_tools.py`

**Interfaces:**
- Exposes tools in `get_agent_tools`:
  - `tool_update_stock_and_craving`
  - `tool_report_past_meal_deviation`
  - `tool_log_unplanned_grocery_run`
  - `tool_view_inventory_stock`
- Connects chat-time catch-up before tool execution.

- [ ] **Step 1: Write the failing test for registered stock tools and execution**

```python
# tests/test_agent_stock_tools.py
import unittest, os, shutil, tempfile
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts

class TestAgentStockTools(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 70.0,
            "target_calories": 2500.0,
            "is_onboarded": True
        })
        ensure_weekly_plan_artifacts(self.profile, self.test_dir)
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_stock_tools_registered_and_executable(self):
        tools = {t.__name__: t for t in get_agent_tools(self.test_dir)}
        self.assertIn("tool_update_stock_and_craving", tools)
        self.assertIn("tool_report_past_meal_deviation", tools)
        self.assertIn("tool_view_inventory_stock", tools)

        # Execute stock update
        msg = tools["tool_update_stock_and_craving"](
            craving_dish="Air Fried Chicken",
            on_hand_proteins=[
                {"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 500.0},
                {"food_id": "chicken_thigh_quarter", "name": "Chicken Thigh Quarter", "quantity_g": 500.0}
            ]
        )
        self.assertIn("Air Fried Chicken", msg)
        self.assertIn("Chicken soup", msg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests/test_agent_stock_tools.py -v`
Expected: FAIL with `AssertionError: 'tool_update_stock_and_craving' not found`

- [ ] **Step 3: Implement tools in `meal_planner/agent.py` and update `build_system_instruction`**

Register tools with clean, natural English docstrings and integrate `reconcile_inventory_state` into the prompt builder and tool calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_agent_stock_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/agent.py tests/test_agent_stock_tools.py
git commit -m "feat: expose stock bookkeeping and craving adaptation tools to ADK agent"
```

---

### Task 7: End-to-End System Integration & Full Suite Verification

**Files:**
- Create: `tests/test_stock_bookkeeping_e2e.py`
- Test: All test files in `tests/`

- [ ] **Step 1: Write comprehensive end-to-end user scenario test**

```python
# tests/test_stock_bookkeeping_e2e.py
import unittest, os, shutil, tempfile
from meal_planner.tools.onboarding import init_user_profile
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts, get_current_cycle_prefix
from meal_planner.agent import get_agent_tools
import csv

class TestStockBookkeepingE2E(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.profile = init_user_profile(self.test_dir, {
            "timezone": "Europe/Brussels",
            "bodyweight_kg": 61.0,
            "target_calories": 2400.0,
            "is_onboarded": True,
            "week_start_day": "Saturday"
        })
        ensure_weekly_plan_artifacts(self.profile, self.test_dir)
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_full_athlete_scenario_craving_and_floating_cadence(self):
        tools = {t.__name__: t for t in get_agent_tools(self.test_dir)}
        # 1. Athlete reports 500g wings + 500g thighs craving air fried chicken
        msg = tools["tool_update_stock_and_craving"](
            craving_dish="Air Fried Chicken",
            on_hand_proteins=[
                {"food_id": "chicken_wings", "name": "Chicken Wings", "quantity_g": 500.0},
                {"food_id": "chicken_thigh_quarter", "name": "Chicken Thigh Quarter", "quantity_g": 500.0}
            ]
        )
        self.assertIn("Air Fried Chicken", msg)

        # 2. Verify meal plan CSV has Air Fried Chicken and Chicken Soup
        prefix = get_current_cycle_prefix("Europe/Brussels", week_start_day="Saturday")
        plan_csv = os.path.join(self.test_dir, "plans", f"{prefix}_meal_plan.csv")
        with open(plan_csv, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Air Fried Chicken", content)
            self.assertIn("Chicken Soup", content)

        # 3. Verify grocery list shifted and dropped Saturday meat run
        grocery_csv = os.path.join(self.test_dir, "plans", f"{prefix}_grocery_list.csv")
        with open(grocery_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            runs = {r["Run"] for r in reader}
            self.assertNotIn("Saturday", runs)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run python -m unittest tests/test_stock_bookkeeping_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run entire test suite across all 60+ tests**

Run: `uv run python -m unittest discover -s tests -p "test_*.py" -v`
Expected: 0 failures across entire suite.

- [ ] **Step 4: Commit**

```bash
git add tests/test_stock_bookkeeping_e2e.py
git commit -m "test: add end-to-end integration test for stock bookkeeping and floating grocery cadence"
```
