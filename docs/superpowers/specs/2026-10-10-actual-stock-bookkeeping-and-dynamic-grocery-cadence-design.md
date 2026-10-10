# Actual Stock Bookkeeping & Dynamic Grocery Cadence Design

## 1. Intent & Context
Athletes rarely shop and eat in rigid lockstep with a pre-generated weekly schedule. Real life introduces two common variations:
1. **On-hand Protein & Cravings:** An athlete already has protein at home (e.g. 500g chicken wings and 500g chicken thigh quarters) and has a spontaneous craving (e.g. "air fried chicken").
2. **Flexible Grocery Timing:** When an athlete already has ample protein at home, forcing a rigid grocery run on Saturday and Wednesday leads to over-purchasing and spoiled food. Instead, food on hand must be eaten first, and the next grocery run should dynamically shift to the day when inventory runs out, maintaining a rolling 3–4 day freshness window from that point forward.

This system provides **actual stock bookkeeping**, **immediate craving resolution**, **stock-first consumption planning**, and **dynamic grocery cadence**.

---

## 2. Goals, Non-Goals, & Anti-Goals

### Goals
1. **Dual-Layer Inventory (Assumed vs. Actual):**
   - Track inventory state in `data/inventory.json` with status `assumed` (items from scheduled grocery runs past their date) and `actual` (real quantities explicitly reported or updated by the user).
   - Any actual stock reported by the user immediately supersedes assumed stock.
   - When an athlete reports on-hand stock before completing a planned grocery run, unbought perishable meats from that run are automatically removed.
   - Out-of-plan grocery purchases reported by the user are immediately recorded as `actual` stock and integrated into the plan.
2. **Immediate Next-Meal Craving Targeting:**
   - When the user mentions a craving, the agent checks `meal_logs.csv` and local time to identify the current/next eligible meal. If the current slot has not been logged as eaten, the craving replaces the current slot immediately; otherwise, it replaces the next slot.
   - Fits the requested dish into the schedule while calibrating ingredient raw weights to fulfill the target macros.
3. **Stock-First Exhaustion Engine (Lunch & Dinner):**
   - Any remaining on-hand protein after the craving meal is scheduled into consecutive upcoming meals across **both lunch and dinner** until on-hand stock is 0g.
   - Respects dinner texture preference by preparing dinner as a broth/soup variation (e.g. Chicken Noodle Soup / Chicken Broth) while lunches can be solid/air-fried/batch prep.
4. **Dynamic Floating Grocery Cadence:**
   - Calculates the exact date of on-hand stock exhaustion ($D_{\text{exhaust}}$).
   - Prunes or cancels redundant grocery runs before $D_{\text{exhaust}}$.
   - Shifts the next fresh grocery run to $D_{\text{exhaust}}$, purchasing fresh meat for the subsequent 3–4 days (shelf-life limit), followed by subsequent runs at 3–4 day intervals to complete the planning window.
   - Updates batch cook prep dates to match the rescheduled grocery run day.
5. **Full Artifact Synchronization:**
   - Updates `{prefix}_meal_plan.csv`, `{prefix}_batch_cook.csv`, and `{prefix}_grocery_list.csv` in place.
   - Displays clear summaries of what meals changed, what stock is consumed, and when the next grocery run is now scheduled.

### Non-Goals
- Real-time barcode or IoT smart fridge integration.
- Micromanaging non-perishable staples (salt, soy sauce, olive oil) beyond existing bulk threshold tracking.
- Altering the user's overarching nutritional target calories or protein/fat multipliers unless explicitly requested.

### Anti-Goals
- Buying duplicate protein while on-hand meat sits in the fridge.
- Rigidly enforcing Saturday/Wednesday shopping dates when the athlete already has food to eat.
- Silently ignoring a reported craving or postponing it to days later.

---

## 3. Architecture & Data Flow

```
User Input ("I have 500g wings & 500g thighs, craving air fried chicken")
     │
     ▼
[ADK Agent / tool_update_stock_and_craving]
     │
     ├─► 1. Temporal Resolution: Checks local time & meal_logs.csv for unconsumed slot
     │
     ├─► 2. Stock Bookkeeping: Saves to inventory.json (status="actual"); clears unbought run meats
     │
     ├─► 3. Craving Insertion: Replaces next slot with Craving Dish & solves macros
     │
     ├─► 4. Stock Exhaustion: Allocates remaining cuts to consecutive lunch/dinner (dinner = soup)
     │
     ├─► 5. Floating Cadence Solver:
     │        - Finds D_exhaust (day when stock reaches 0)
     │        - Drops obsolete pre-exhaustion grocery runs
     │        - Schedules next grocery run at D_exhaust (Run date = D_exhaust)
     │        - Aligns Prep_Day = D_exhaust in batch cook file
     │        - Generates subsequent runs at 3-4 day intervals
     │
     └─► 6. Artifact Sync: Rewrites weekly meal_plan.csv, batch_cook.csv, grocery_list.csv
```

---

## 4. Key Components & Implementation Details

### A. Inventory & Stock Bookkeeping (`meal_planner/tools/inventory.py`)
Data structure stored in `data/inventory.json`:
```json
{
  "updated_at": "2026-10-10T18:30:00+02:00",
  "items": [
    {
      "food_id": "chicken_wings",
      "name": "Chicken Wings",
      "quantity_g": 500.0,
      "status": "actual",
      "source": "user_report",
      "purchased_date": "2026-10-10"
    },
    {
      "food_id": "chicken_thigh_quarter",
      "name": "Chicken Thigh Quarter",
      "quantity_g": 500.0,
      "status": "actual",
      "source": "user_report",
      "purchased_date": "2026-10-10"
    }
  ]
}
```
- **Lifecycle:**
  - When grocery lists are generated, items in runs with date $\le$ current date default to `status: "assumed"`.
  - When the user explicitly provides stock updates or logs an unplanned grocery purchase, items are recorded as `status: "actual"`.
  - Reporting on-hand stock wipes unbought assumed perishables for upcoming runs, preventing ghost inventory.
  - As meals are consumed or scheduled, stock deductions decrement `quantity_g`.

### B. Temporal Slot & Craving Resolution
Given user timezone $TZ$ and current timestamp $T$:
1. Determine current weekday and time.
2. Meal slot boundaries:
   - Breakfast: 06:00 – 11:30
   - Lunch: 11:30 – 16:30
   - Dinner: 16:30 – 23:59
3. Check `meal_logs.csv` for today's consumption:
   - If $T < 11:30$ and breakfast not logged $\rightarrow$ Breakfast today.
   - If $T < 16:30$ and lunch not logged $\rightarrow$ Lunch today.
   - If $T \ge 16:30$ and dinner not logged $\rightarrow$ Dinner tonight.
   - If current slot is already logged $\rightarrow$ Advances to the next upcoming chronological slot.
4. Target slot is replaced with the craving dish (e.g. "Air Fried Chicken"), with raw weights calibrated to the slot's protein target, inheriting and scaling the slot's side ingredients to balance carbs and calories.

### C. Consecutive Stock Exhaustion Engine (Lunch & Dinner)
1. Take remaining on-hand protein quantities.
2. For each consecutive upcoming meal slot:
   - **Lunch Slots:** Schedule solid/air-fried/batch cuts (e.g. "Air Fried Chicken with Rice & Broccoli").
   - **Dinner Slots:** Schedule soup/broth cuts (e.g. "Chicken Noodle Soup / Chicken Broth") fulfilling the dinner soft/broth texture preference.
   - Calculate required portion size $W_{\text{raw}}$:
     $$W_{\text{raw}} = \frac{\text{target\_protein\_g}}{\text{protein\_density}}$$
   - Decrement on-hand stock by $W_{\text{raw}}$.
3. Record exact date and slot when inventory reaches 0: $D_{\text{exhaust}}$.

### D. Dynamic Floating Grocery Cadence
1. From $D_{\text{exhaust}}$, compute the date for the next grocery run:
   - Grocery Run Date = Date of first meal requiring store-bought meat ($D_{\text{run}} = D_{\text{exhaust}}$).
2. Fresh meat rule: Meats bought on $D_{\text{run}}$ cover meals from $D_{\text{run}}$ through $D_{\text{run}} + 3\text{ days}$ (maximum 72–96h refrigeration window).
3. Subsequent grocery runs are scheduled at 3–4 day intervals (e.g., Tuesday $\rightarrow$ Friday $\rightarrow$ Monday).
4. Drop redundant planned grocery runs prior to $D_{\text{exhaust}}$.
5. In `{prefix}_grocery_list.csv`, the `Run` column shows the revised run day (e.g. `Tuesday`).
6. In `{prefix}_batch_cook.csv`, `Prep_Day` and `Grocery_Run` synchronize with the new run schedule.

---

## 5. Agent Tools & Interface

### 1. `tool_update_stock_and_craving`
```python
def tool_update_stock_and_craving(
    craving_dish: Optional[str] = None,
    on_hand_proteins: Optional[list[dict]] = None,
    cooking_style: Optional[str] = "air_fried"
) -> str:
    """Updates actual stock on hand, swaps next meal to satisfy craving, and reschedules subsequent lunch & dinner meals and grocery runs."""
```
- Accepts on-hand protein items (e.g. `[{"name": "Chicken wings", "quantity_g": 500}, {"name": "Chicken thigh quarter", "quantity_g": 500}]`).
- Updates inventory.
- Adapts weekly meal plan, batch cook file, and grocery list.
- Returns comprehensive breakdown:
  1. Next meal swapped for craving.
  2. Consecutive lunch and dinner meals scheduled to use up remaining on-hand stock (with dinner as chicken soup).
  3. New date of stock depletion and rescheduled grocery run date.

### 2. `tool_log_unplanned_grocery_run`
```python
def tool_log_unplanned_grocery_run(
    items: list[dict],
    run_date: Optional[str] = None
) -> str:
    """Logs groceries purchased out of plan, updates actual stock, and dynamically shifts future grocery runs."""
```

### 3. `tool_view_inventory_stock`
```python
def tool_view_inventory_stock() -> str:
    """Displays current inventory separated into 'Actual Stock' (confirmed) and 'Assumed Stock' (from planned runs)."""
```

---

## 6. Verification & Test Plan
1. **Unit Tests:**
   - `test_inventory_state_assumed_vs_actual`: Confirms tracking, loading, saving, and superseding of stock.
   - `test_next_meal_craving_resolution`: Tests unlogged current meal window vs already logged meal progression.
   - `test_stock_exhaustion_lunch_and_dinner_soup`: Verifies 500g wings + 500g thighs are consumed across consecutive lunch (solid) and dinner (chicken soup) slots until 0g remains.
   - `test_dynamic_grocery_cadence_shift`: Verifies planned runs are pruned, next run is placed on $D_{\text{exhaust}}$, and subsequent runs occur 3–4 days later.
   - `test_unplanned_grocery_logging`: Confirms out-of-plan shopping adds actual inventory and recalculates runs.
2. **Integration Tests:**
   - Full flow test calling `tool_update_stock_and_craving` on an active cycle, checking CSV output for meal plan, batch cook, and grocery list.
