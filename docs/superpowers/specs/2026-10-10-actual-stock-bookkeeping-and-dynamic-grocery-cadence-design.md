# Actual Stock Bookkeeping & Dynamic Grocery Cadence Design

## 1. Intent & Context
Athletes rarely shop and eat in rigid lockstep with a pre-generated weekly schedule. Real life introduces common variations:
1. **On-hand Protein & Cravings:** An athlete already has protein at home (e.g. 500g chicken wings and 500g chicken thigh quarters) and has a spontaneous craving (e.g. "air fried chicken").
2. **Flexible Grocery Timing:** When an athlete already has ample protein at home, forcing a rigid grocery run on Saturday and Wednesday leads to over-purchasing and spoiled food. Instead, food on hand must be eaten first, and the next grocery run should dynamically shift to the day when inventory runs out, maintaining a rolling 3–4 day freshness window from that point forward.
3. **Passive Adherence & Batch Chat-Time Reconciliation:** Real-time 24/7 background timers are undesirable and fragile. Instead, whenever the user chats, the agent runs a **catch-up reconciliation**: assuming past planned runs were completed and past anchor meals were consumed according to plan.
4. **Retrospective Corrections & Macro Deficit Amortization:** Athletes frequently report past events out-of-sync (e.g. at night: "this morning I skipped breakfast"). If an athlete cannot comfortably eat a huge catch-up meal before bed, the remaining caloric difference can be rolled over and amortized gently across upcoming days/next week (capped at a digestible daily ceiling like +150 to +200 kcal/day) so meal volumes stay manageable.

---

## 2. Goals, Non-Goals, & Anti-Goals

### Goals
1. **Dual-Layer Inventory (Assumed vs. Actual):**
   - Track inventory state in `data/inventory.json` with status `assumed` (items from scheduled grocery runs past their date) and `actual` (real quantities explicitly reported or updated by the user).
   - Any actual stock reported by the user immediately supersedes assumed stock.
   - When an athlete reports on-hand stock before completing a planned grocery run, unbought perishable meats from that run are automatically removed.
   - Out-of-plan grocery purchases reported by the user are immediately recorded as `actual` stock and integrated into the plan.
2. **Chat-Time State Reconciliation (Catch-Up):**
   - At conversation turn time, compare `last_reconciled_at` against current local time.
   - Advance assumed grocery purchases for runs $\le$ today.
   - Advance assumed meal consumption for meal slots whose cutoff has passed, deducting ingredients from inventory.
   - Record `last_reconciled_at = now`.
3. **Retrospective Past Meal Corrections & Stock Restoration:**
   - Allow reporting deviations for past meals (e.g., "I skipped breakfast this morning").
   - Restores the unconsumed ingredients back into `inventory.json`.
   - Recalculates the day's macro deficit and recommends remedial actions (immediate bedtime snack vs. rollover).
4. **Digestible Deficit Amortization Across Future Days:**
   - If an unrecovered calorie/protein deficit remains at the end of the day (or the user chooses not to eat late at night), the deficit can be carried forward and spread evenly across the remaining days or next week's meal plan.
   - Enforces a sensible daily buffer ceiling (maximum +150 to +200 kcal/day and +15g protein/day) to prevent stomach bloating and respect appetite limits.
5. **Preferred Meal Windows & Next-Meal Craving Targeting:**
   - Anchor times: Breakfast @ 08:00 (cutoff 10:00), Lunch @ 12:30 (cutoff 14:30), Dinner @ 19:00 (cutoff 21:00).
   - A craving replaces the very next core meal relative to current local time (unless explicitly specified as an extra meal/snack).
   - Fits the requested dish into the schedule while calibrating ingredient raw weights to fulfill target macros.
6. **Stock-First Exhaustion Engine (Lunch & Dinner):**
   - Any remaining on-hand protein after the craving meal is scheduled into consecutive upcoming meals across **both lunch and dinner** until on-hand stock is 0g.
   - Respects dinner texture preference by preparing dinner as a broth/soup variation (e.g. Chicken Noodle Soup / Chicken Broth) while lunches can be solid/air-fried/batch prep.
7. **Eating Out & Extra Snack Handling:**
   - Reporting an "eat out" meal logs nutritional macros/calories toward daily totals, but **does not** deduct home fridge/pantry stock.
   - Baseline is 3 core meals per day. Extra snacks/shakes reported by the user are added as additional slots without overwriting the 3 core meals.
8. **Dynamic Floating Grocery Cadence:**
   - Calculates the exact date of on-hand stock exhaustion ($D_{\text{exhaust}}$).
   - Prunes or cancels redundant grocery runs before $D_{\text{exhaust}}$.
   - Shifts the next fresh grocery run to $D_{\text{exhaust}}$, purchasing fresh meat for the subsequent 3–4 days (shelf-life limit), followed by subsequent runs at 3–4 day intervals to complete the planning window.
   - Updates batch cook prep dates to match the rescheduled grocery run day.
9. **Full Artifact Synchronization:**
   - Updates `{prefix}_meal_plan.csv`, `{prefix}_batch_cook.csv`, and `{prefix}_grocery_list.csv` in place.

### Non-Goals
- Forcing huge binge-eating catch-up meals that exceed the athlete's digestive comfort.
- Real-time 24/7 daemon background workers or timers.
- Requiring manual check-ins for every scheduled meal.

### Anti-Goals
- Overloading single meals with excess food when compensating for past skipped calories.
- Deducting home meat stock when the athlete eats out at a restaurant.
- Leaving skipped meal ingredients marked as consumed instead of putting them back in the fridge.

---

## 3. Architecture & Data Flow

```
User Input (Any message / Craving / Retrospective deviation)
     │
     ▼
[1. Chat-Time Reconciliation Engine]
     │   - Reads last_reconciled_at vs now_local
     │   - Assumes past runs completed -> adds assumed inventory
     │   - Assumes past cutoff meals consumed -> deducts stock
     │   - Advances last_reconciled_at
     │
     ▼
[2. Dispatch Request]
     │
     ├─► Retrospective Report ("I skipped breakfast this morning"):
     │        - Restores breakfast ingredients to inventory.json
     │        - Updates today's logged macros
     │        - Offers choice: immediate snack OR amortize deficit across upcoming days
     │
     ├─► Calorie Deficit Amortization:
     │        - Distributes unrecovered deficit over next N days (capped at +200 kcal/day)
     │        - Adjusts portion sizes in weekly meal_plan.csv accordingly
     │
     ├─► Eating Out ("I ate out for lunch"):
     │        - Restores planned lunch ingredients to inventory.json
     │        - Logs restaurant macros in meal_logs.csv
     │
     └─► Craving & On-Hand Stock ("I have 500g wings & 500g thighs, craving air fried chicken"):
              - Identifies next core meal window
              - Swaps craving dish and solves raw portion weights
              - Allocates remaining chicken to consecutive lunch & dinner (soup) slots
              - Solves D_exhaust and reschedules grocery runs to float dynamically
              - Rewrites CSV artifacts
```

---

## 4. Key Components & Implementation Details

### A. Inventory & Stock Bookkeeping (`meal_planner/tools/inventory.py`)
Data structure stored in `data/inventory.json`:
```json
{
  "last_reconciled_at": "2026-10-10T18:30:00+02:00",
  "amortized_calorie_debt": 0.0,
  "amortized_protein_debt_g": 0.0,
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
- **Lifecycle & Reconciliation:**
  - `reconcile_inventory_state(data_dir, current_dt)`:
    - Runs at chat start or before tool execution.
    - Adds planned grocery runs with run date $\le$ current date as `assumed` inventory.
    - For past meal slots between `last_reconciled_at` and `current_dt`, deducts ingredient quantities from inventory.
    - Saves `last_reconciled_at = current_dt.isoformat()`.
  - When user explicitly updates stock or logs unplanned shopping, items are saved with `status: "actual"`.
  - Reporting on-hand stock clears unbought assumed perishables from upcoming runs.

### B. Retrospective Past Meal Handling & Deficit Amortization
- Function `reconcile_past_meal_deviation(data_dir, target_date, slot_name, deviation_type, eaten_macros=None, amortize_debt=True)`:
  - If `deviation_type == "skipped"`:
    - Finds ingredients scheduled for that slot.
    - Re-adds their portion weights back to `inventory.json`!
    - Updates `meal_logs.csv` to record slot as skipped.
    - Calculates remaining daily protein and calorie deficit ($\Delta_{\text{cal}}$, $\Delta_{\text{prot}}$).
    - If `amortize_debt=True` (or user cannot finish calories today):
      - Saves remaining deficit to `amortized_calorie_debt` and `amortized_protein_debt_g` in `inventory.json`.
      - Amortizes deficit across next 5–7 days with daily caps:
        $$\Delta_{\text{daily\_cal}} = \min\left(200.0, \frac{\Delta_{\text{cal}}}{N}\right)$$
        $$\Delta_{\text{daily\_prot}} = \min\left(15.0, \frac{\Delta_{\text{prot}}}{N}\right)$$
      - Adjusts portion sizes in `{prefix}_meal_plan.csv` to seamlessly recoup the calories without meal bloat.
  - If `deviation_type == "eat_out"`:
    - Planned slot ingredients are restored to `inventory.json`.
    - Eaten out calories and protein are logged in `meal_logs.csv`.

### C. Temporal Anchor Windows & Craving Targeting
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

### D. Consecutive Stock Exhaustion Engine (Lunch & Dinner)
1. Remaining on-hand protein quantities are tracked.
2. For each consecutive upcoming meal slot:
   - **Lunch Slots:** Schedule solid/air-fried/batch cuts (e.g. "Air Fried Chicken with Rice & Broccoli").
   - **Dinner Slots:** Schedule soup/broth cuts (e.g. "Chicken Noodle Soup / Chicken Broth") fulfilling the dinner soft/broth texture preference.
   - Calculate required portion size $W_{\text{raw}}$:
     $$W_{\text{raw}} = \frac{\text{target\_protein\_g}}{\text{protein\_density}}$$
   - Decrement on-hand stock by $W_{\text{raw}}$.
3. Record exact date and slot when inventory reaches 0: $D_{\text{exhaust}}$.

### E. Dynamic Floating Grocery Cadence
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

### 2. `tool_report_past_meal_deviation`
```python
def tool_report_past_meal_deviation(
    meal_slot: str,
    deviation_type: str,  # "skipped" | "eat_out" | "custom"
    day_or_date: Optional[str] = None,  # Defaults to "today"
    eaten_description: Optional[str] = None,
    actual_calories: Optional[float] = None,
    actual_protein_g: Optional[float] = None,
    amortize_to_future_days: bool = True
) -> str:
    """Reconciles a past meal deviation, reverses assumed stock deductions to put unused food back in the fridge, and either advises on immediate catch-up or amortizes deficit across future days."""
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
    """Displays current inventory separated into 'Actual Stock' (confirmed) and 'Assumed Stock' (from planned runs), reconciliation timestamp, and any active amortized calorie debt."""
```

---

## 6. Verification & Test Plan
1. **Unit Tests:**
   - `test_chat_time_reconciliation_catchup`: Simulates elapsed days/hours and verifies past runs/meals are marked assumed consumed.
   - `test_retrospective_skipped_meal_restores_stock`: Verifies reporting "skipped breakfast" restores ingredients back into `inventory.json`.
   - `test_calorie_debt_amortization_spread`: Verifies unrecovered calorie deficit is safely amortized across future days capped at +200 kcal/day.
   - `test_retrospective_eating_out_restores_stock`: Verifies eating out restores home ingredients while recording actual eaten calories/protein.
   - `test_preferred_anchor_windows`: Verifies 08:00 Breakfast, 12:30 Lunch, and 19:00 Dinner window cutoffs.
   - `test_stock_exhaustion_lunch_and_dinner_soup`: Verifies 500g wings + 500g thighs are consumed across consecutive lunch (solid) and dinner (chicken soup) slots until 0g remains.
   - `test_dynamic_grocery_cadence_shift`: Verifies planned runs are pruned, next run is placed on $D_{\text{exhaust}}$, and subsequent runs occur 3–4 days later.
   - `test_unplanned_grocery_logging`: Confirms out-of-plan shopping adds actual inventory and recalculates runs.
2. **Integration Tests:**
   - Full flow test calling `tool_update_stock_and_craving` and `tool_report_past_meal_deviation` on an active cycle, checking CSV output for meal plan, batch cook, and grocery list.
