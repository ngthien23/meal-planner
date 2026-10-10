# Actual Stock Bookkeeping & Dynamic Grocery Cadence Design

## 1. Intent & Context
Athletes rarely shop and eat in rigid lockstep with a pre-generated weekly schedule. Real life introduces common variations:
1. **On-hand Protein & Cravings:** An athlete already has protein at home (e.g. 500g chicken wings and 500g chicken thigh quarters) and has a spontaneous craving (e.g. "air fried chicken").
2. **Flexible Grocery Timing:** When an athlete already has ample protein at home, forcing a rigid grocery run on Saturday and Wednesday leads to over-purchasing and spoiled food. Instead, food on hand must be eaten first, and the next grocery run dynamically shifts to the day when inventory runs out, maintaining a rolling 3–4 day freshness window from that point forward.
3. **Passive Adherence & Schedule Anchors:** Logging every meal is tedious. Past meals are assumed eaten according to plan unless reported otherwise. Preferred anchor times are Breakfast @ 08:00, Lunch @ 12:30, and Dinner @ 19:00. Eating out tracks calories/protein without deducting fridge stock. Baseline days consist of 3 core meals, while supporting optional extra snacks.

---

## 2. Goals, Non-Goals, & Anti-Goals

### Goals
1. **Dual-Layer Inventory (Assumed vs. Actual):**
   - Track inventory state in `data/inventory.json` with status `assumed` (items from scheduled grocery runs past their date) and `actual` (real quantities explicitly reported or updated by the user).
   - Any actual stock reported by the user immediately supersedes assumed stock.
   - When an athlete reports on-hand stock before completing a planned grocery run, unbought perishable meats from that run are automatically removed.
   - Out-of-plan grocery purchases reported by the user are immediately recorded as `actual` stock and integrated into the plan.
2. **Implicit Consumption by Time-of-Day:**
   - If no meal log or deviation is submitted, past meal slots relative to current local time are assumed consumed according to the plan, and inventory is automatically decremented.
3. **Preferred Meal Windows & Next-Meal Craving Targeting:**
   - Anchor times: Breakfast @ 08:00 (cutoff 10:00), Lunch @ 12:30 (cutoff 14:30), Dinner @ 19:00 (cutoff 21:00).
   - A craving replaces the very next core meal relative to current local time (unless explicitly specified as an extra meal/snack).
   - Fits the requested dish into the schedule while calibrating ingredient raw weights to fulfill target macros.
4. **Stock-First Exhaustion Engine (Lunch & Dinner):**
   - Any remaining on-hand protein after the craving meal is scheduled into consecutive upcoming meals across **both lunch and dinner** until on-hand stock is 0g.
   - Respects dinner texture preference by preparing dinner as a broth/soup variation (e.g. Chicken Noodle Soup / Chicken Broth) while lunches can be solid/air-fried/batch prep.
5. **Eating Out & Extra Snack Handling:**
   - Reporting an "eat out" meal logs nutritional macros/calories toward daily totals, but **does not** deduct home fridge/pantry stock.
   - Baseline is 3 core meals per day. Extra snacks/shakes reported by the user are added as additional slots without overwriting the 3 core meals.
6. **Dynamic Floating Grocery Cadence:**
   - Calculates the exact date of on-hand stock exhaustion ($D_{\text{exhaust}}$).
   - Prunes or cancels redundant grocery runs before $D_{\text{exhaust}}$.
   - Shifts the next fresh grocery run to $D_{\text{exhaust}}$, purchasing fresh meat for the subsequent 3–4 days (shelf-life limit), followed by subsequent runs at 3–4 day intervals to complete the planning window.
   - Updates batch cook prep dates to match the rescheduled grocery run day.
7. **Full Artifact Synchronization:**
   - Updates `{prefix}_meal_plan.csv`, `{prefix}_batch_cook.csv`, and `{prefix}_grocery_list.csv` in place.

### Non-Goals
- Requiring manual check-ins for every scheduled meal.
- Real-time barcode or IoT smart fridge integration.
- Micromanaging non-perishable staples (salt, soy sauce, olive oil) beyond existing bulk threshold tracking.

### Anti-Goals
- Deducting home meat stock when the athlete eats out at a restaurant.
- Buying duplicate protein while on-hand meat sits in the fridge.
- Rigidly enforcing Saturday/Wednesday shopping dates when the athlete already has food to eat.

---

## 3. Architecture & Data Flow

```
User Input ("I have 500g wings & 500g thighs, craving air fried chicken")
     │
     ▼
[ADK Agent / tool_update_stock_and_craving]
     │
     ├─► 1. Temporal Window Resolution:
     │        - Checks local time against anchors (Breakfast 08:00, Lunch 12:30, Dinner 19:00)
     │        - Past meals assumed eaten (implicit consumption)
     │        - Identifies chronologically next core meal slot
     │
     ├─► 2. Stock Bookkeeping:
     │        - Saves reported items to inventory.json (status="actual")
     │        - Removes unbought redundant perishable meats from upcoming grocery run
     │
     ├─► 3. Craving Insertion:
     │        - Replaces target slot with Craving Dish & solves raw weights for macros
     │
     ├─► 4. Stock Exhaustion:
     │        - Allocates remaining cuts to consecutive lunch & dinner slots
     │        - Dinner prepared as soup/broth variation (compromise texture rule)
     │
     ├─► 5. Floating Cadence Solver:
     │        - Computes D_exhaust (exact date when on-hand stock hits 0)
     │        - Prunes pre-exhaustion grocery runs
     │        - Places next grocery run on D_exhaust (and batch prep on D_exhaust)
     │        - Spaces future runs at 3-4 day intervals
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
  - Items in planned grocery runs with run date $\le$ current date default to `status: "assumed"`.
  - When the user explicitly provides stock updates or logs an unplanned grocery purchase, items are recorded as `status: "actual"`.
  - Reporting on-hand stock wipes unbought assumed perishables for upcoming runs, preventing ghost inventory.
  - Eating out records calories/protein in `meal_logs.csv` but **never** decrements `inventory.json`.
  - Implicit consumption: as time passes past anchor windows (08:00, 12:30, 19:00), planned meal ingredients are decremented from stock automatically.

### B. Temporal Anchor Windows & Craving Targeting
Preferred anchor times and cutoff thresholds:
1. **Breakfast:** Target 08:00 (window 06:00 – 10:00).
2. **Lunch:** Target 12:30 (window 10:00 – 14:30).
3. **Dinner:** Target 19:00 (window 14:30 – 21:00).
4. After 21:00, next meal is Breakfast tomorrow (08:00).

- Next meal resolution:
  - If current time $T < 10:00 \rightarrow$ Breakfast today.
  - If $10:00 \le T < 14:30 \rightarrow$ Lunch today.
  - If $14:30 \le T < 21:00 \rightarrow$ Dinner tonight.
  - If $T \ge 21:00 \rightarrow$ Breakfast tomorrow.
- Core vs. Extra Meal handling:
  - Default: Cravings replace the resolved core meal slot.
  - If user explicitly specifies "extra", "snack", or "shake", an extra slot is appended to the day without overwriting core slots.

### C. Consecutive Stock Exhaustion Engine (Lunch & Dinner)
1. Remaining on-hand protein quantities are tracked.
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
    cooking_style: Optional[str] = "air_fried",
    is_extra_snack: bool = False
) -> str:
    """Updates actual stock on hand, swaps next core meal to satisfy craving, and reschedules subsequent lunch & dinner meals and grocery runs."""
```

### 2. `tool_log_eating_out`
```python
def tool_log_eating_out(
    meal_slot: str,
    calories: float,
    protein_g: float,
    dish_description: str = "Restaurant meal"
) -> str:
    """Logs an eaten out meal for macro tracking without deducting home pantry or meat stock."""
```

### 3. `tool_log_unplanned_grocery_run`
```python
def tool_log_unplanned_grocery_run(
    items: list[dict],
    run_date: Optional[str] = None
) -> str:
    """Logs groceries purchased out of plan, updates actual stock, and dynamically shifts future grocery runs."""
```

### 4. `tool_view_inventory_stock`
```python
def tool_view_inventory_stock() -> str:
    """Displays current inventory separated into 'Actual Stock' (confirmed) and 'Assumed Stock' (from planned runs)."""
```

---

## 6. Verification & Test Plan
1. **Unit Tests:**
   - `test_inventory_state_assumed_vs_actual`: Confirms tracking, loading, saving, and superseding of stock.
   - `test_implicit_consumption_by_time`: Verifies past meal windows automatically deduct stock without manual logging.
   - `test_eating_out_does_not_deduct_stock`: Verifies eating out logs calories/protein but leaves `inventory.json` stock intact.
   - `test_preferred_anchor_windows`: Verifies 08:00 Breakfast, 12:30 Lunch, and 19:00 Dinner window cutoffs.
   - `test_stock_exhaustion_lunch_and_dinner_soup`: Verifies 500g wings + 500g thighs are consumed across consecutive lunch (solid) and dinner (chicken soup) slots until 0g remains.
   - `test_dynamic_grocery_cadence_shift`: Verifies planned runs are pruned, next run is placed on $D_{\text{exhaust}}$, and subsequent runs occur 3–4 days later.
   - `test_unplanned_grocery_logging`: Confirms out-of-plan shopping adds actual inventory and recalculates runs.
2. **Integration Tests:**
   - Full flow test calling `tool_update_stock_and_craving` on an active cycle, checking CSV output for meal plan, batch cook, and grocery list.
