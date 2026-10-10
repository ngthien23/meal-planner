import os
import json
import csv
import re
from datetime import datetime, date, time, timedelta
from typing import Optional

from meal_planner.models import (
    InventoryItem,
    InventoryState,
    load_catalog,
    UserProfile,
)
from meal_planner.tools.onboarding import resolve_timezone, load_user_profile
from meal_planner.tools.meal_generator import get_current_cycle_prefix, ensure_weekly_plan_artifacts
from meal_planner.tools.tracker import log_meal_consumption

__all__ = [
    "InventoryItem",
    "InventoryState",
    "load_inventory_state",
    "save_inventory_state",
    "record_actual_stock",
    "reconcile_inventory_state",
    "reconcile_past_meal_deviation",
    "spread_missed_calories",
]


def load_inventory_state(data_dir: str) -> InventoryState:
    """Loads inventory state from inventory.json in data_dir.
    
    If the file does not exist, returns an empty default InventoryState.
    """
    inventory_path = os.path.join(data_dir, "inventory.json")
    if not os.path.exists(inventory_path):
        return InventoryState(
            last_reconciled_at=None,
            carried_calories=0.0,
            carried_protein_g=0.0,
            items=[],
            assumed_runs=[]
        )

    try:
        with open(inventory_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return InventoryState(
                last_reconciled_at=None,
                carried_calories=0.0,
                carried_protein_g=0.0,
                items=[],
                assumed_runs=[]
            )

        items = [
            InventoryItem(
                food_id=item["food_id"],
                name=item.get("name", item["food_id"].replace("_", " ").title()),
                quantity_g=float(item.get("quantity_g", 0.0)),
                status=item.get("status", "actual"),
                source=item.get("source", "user_report"),
                purchased_date=item.get("purchased_date", "")
            )
            for item in data.get("items", [])
        ]

        return InventoryState(
            last_reconciled_at=data.get("last_reconciled_at"),
            carried_calories=float(data.get("carried_calories", 0.0)),
            carried_protein_g=float(data.get("carried_protein_g", 0.0)),
            items=items,
            assumed_runs=data.get("assumed_runs", [])
        )
    except Exception:
        return InventoryState(
            last_reconciled_at=None,
            carried_calories=0.0,
            carried_protein_g=0.0,
            items=[],
            assumed_runs=[]
        )


def save_inventory_state(data_dir: str, state: InventoryState) -> None:
    """Persists inventory state to inventory.json in data_dir."""
    os.makedirs(data_dir, exist_ok=True)
    inventory_path = os.path.join(data_dir, "inventory.json")

    data = {
        "last_reconciled_at": state.last_reconciled_at,
        "carried_calories": round(float(state.carried_calories), 2),
        "carried_protein_g": round(float(state.carried_protein_g), 2),
        "assumed_runs": getattr(state, "assumed_runs", []),
        "items": [
            {
                "food_id": item.food_id,
                "name": item.name,
                "quantity_g": round(float(item.quantity_g), 2),
                "status": item.status,
                "source": item.source,
                "purchased_date": item.purchased_date
            }
            for item in state.items
        ]
    }

    with open(inventory_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_actual_stock(
    data_dir: str,
    items: list[dict],
    clear_unbought_run_meats: bool = True
) -> InventoryState:
    """Updates inventory state with user-reported actual stock items.
    
    If clear_unbought_run_meats is True, assumed perishable meats from upcoming
    planned runs are pruned so duplicate meat is not bought.
    Matching food_ids are updated with status='actual' and source='user_report',
    and new food_ids are appended.
    """
    state = load_inventory_state(data_dir)

    if clear_unbought_run_meats:
        try:
            catalog_ingredients, _ = load_catalog(data_dir=data_dir)
        except Exception:
            catalog_ingredients = {}

        def is_meat_or_perishable(food_id: str) -> bool:
            if food_id in catalog_ingredients:
                ing = catalog_ingredients[food_id]
                return bool(ing.perishable and (ing.category in ("meat", "seafood", "poultry") or "meat" in ing.category.lower()))
            lower_id = food_id.lower()
            if "canned" in lower_id or "dried" in lower_id:
                return False
            keywords = ("chicken", "beef", "pork", "meat", "shrimp", "fish", "salmon", "turkey", "lamb", "steak", "thigh", "wing", "breast")
            return any(k in lower_id for k in keywords)

        state.items = [
            item for item in state.items
            if not (item.status == "assumed" and is_meat_or_perishable(item.food_id))
        ]

    today_str = datetime.now().strftime("%Y-%m-%d")

    for raw_item in items:
        food_id = raw_item["food_id"]
        name = raw_item.get("name") or food_id.replace("_", " ").title()
        quantity_g = float(raw_item.get("quantity_g", 0.0))
        purchased_date = raw_item.get("purchased_date") or today_str
        source = raw_item.get("source", "user_report")
        status = "actual"

        existing = next((i for i in state.items if i.food_id == food_id), None)
        if existing:
            existing.name = name
            existing.quantity_g = quantity_g
            existing.status = status
            existing.source = source
            existing.purchased_date = purchased_date
        else:
            state.items.append(
                InventoryItem(
                    food_id=food_id,
                    name=name,
                    quantity_g=quantity_g,
                    status=status,
                    source=source,
                    purchased_date=purchased_date
                )
            )

    save_inventory_state(data_dir, state)
    return state


def _find_inventory_item(
    items: list[InventoryItem],
    ing_raw_name: str,
    catalog_ingredients: dict
) -> Optional[InventoryItem]:
    """Finds a matching item in items by food_id, name, catalog resolution, or substring."""
    ing_l = ing_raw_name.strip().lower()
    norm = ing_l.replace(" ", "_").replace("-", "_")

    # 1. Direct food_id match
    for it in items:
        if it.food_id.lower() == norm:
            return it

    # 2. Direct name match
    for it in items:
        if it.name.lower() == ing_l:
            return it

    # 3. Match via catalog
    for cat_id, cat_ing in catalog_ingredients.items():
        if cat_ing.name.lower() == ing_l or cat_id.lower() == norm:
            for it in items:
                if it.food_id == cat_id:
                    return it
            break

    # 4. Substring match
    for it in items:
        it_name_l = it.name.lower()
        it_id_l = it.food_id.lower().replace("_", " ")
        if it_name_l in ing_l or ing_l in it_name_l:
            return it
        if it_id_l in ing_l or ing_l in it_id_l:
            return it

    return None


def reconcile_inventory_state(
    data_dir: str,
    current_dt: datetime,
    user_tz: str = "Europe/Brussels"
) -> tuple[InventoryState, list[str]]:
    """Brings fridge stock up to date by catching up past scheduled shopping and meals.
    
    1. Assumes planned grocery runs with run date <= current_dt.date() were purchased
       and adds items to inventory with status='assumed' (respecting actual stock).
    2. Identifies past meal slots whose cutoff times (Breakfast 10:00, Lunch 14:30,
       Dinner 21:00) fall between last_reconciled_at and current_dt, and deducts
       their ingredients from stock (clamping to 0.0g).
    3. Advances last_reconciled_at to current_dt.isoformat() and persists state.
    
    Returns (state, actions).
    """
    profile = load_user_profile(data_dir)
    effective_tz = user_tz if user_tz else (profile.timezone if profile else "Europe/Brussels")
    tz = resolve_timezone(effective_tz)

    if current_dt.tzinfo is None:
        current_dt = current_dt.replace(tzinfo=tz)
    else:
        current_dt = current_dt.astimezone(tz)

    state = load_inventory_state(data_dir)
    if not hasattr(state, "assumed_runs") or state.assumed_runs is None:
        state.assumed_runs = []

    if profile is None:
        profile = UserProfile(timezone=effective_tz)

    prefix = get_current_cycle_prefix(
        tz_name=effective_tz,
        reference_dt=current_dt,
        week_start_day=getattr(profile, "week_start_day", "Saturday")
    )

    plans_dir = os.path.join(data_dir, "plans")
    plan_path = os.path.join(plans_dir, f"{prefix}_meal_plan.csv")
    grocery_path = os.path.join(plans_dir, f"{prefix}_grocery_list.csv")

    if not (os.path.exists(plan_path) and os.path.exists(grocery_path)):
        ensure_weekly_plan_artifacts(profile, data_dir, reference_dt=current_dt)

    # Determine last reconciled datetime and current cycle bounds
    try:
        current_cycle_start = datetime.strptime(prefix, "%y%m%d").date()
    except Exception:
        current_cycle_start = current_dt.date()

    last_dt = None
    if state.last_reconciled_at:
        try:
            last_dt = datetime.fromisoformat(state.last_reconciled_at)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=tz)
            else:
                last_dt = last_dt.astimezone(tz)
        except Exception:
            last_dt = None

    if last_dt is None:
        last_dt = datetime.combine(current_cycle_start, time(0, 0), tzinfo=tz)

    try:
        catalog_ingredients, _ = load_catalog(data_dir=data_dir)
    except Exception:
        catalog_ingredients = {}

    def is_meat_or_perishable(food_id: str) -> bool:
        if food_id in catalog_ingredients:
            ing = catalog_ingredients[food_id]
            return bool(ing.perishable and (ing.category in ("meat", "seafood", "poultry") or "meat" in ing.category.lower()))
        lower_id = food_id.lower()
        if "canned" in lower_id or "dried" in lower_id:
            return False
        keywords = ("chicken", "beef", "pork", "meat", "shrimp", "fish", "salmon", "turkey", "lamb", "steak", "thigh", "wing", "breast")
        return any(k in lower_id for k in keywords)

    # Only actual meat with positive stock on hand suppresses assumed runs
    user_has_actual_meat = any(
        it.status == "actual" and it.quantity_g > 0 and is_meat_or_perishable(it.food_id)
        for it in state.items
    )

    actions: list[str] = []

    # 1. Process scheduled grocery runs bounded by current cycle start and last_dt.date()
    grocery_files = []
    if os.path.exists(plans_dir):
        for fn in sorted(os.listdir(plans_dir)):
            m = re.match(r"^(\d{6})_grocery_list\.csv$", fn)
            if m:
                try:
                    f_start = datetime.strptime(m.group(1), "%y%m%d").date()
                    if f_start >= current_cycle_start:
                        grocery_files.append((os.path.join(plans_dir, fn), f_start))
                except Exception:
                    pass
    if not grocery_files and os.path.exists(grocery_path):
        grocery_files.append((grocery_path, current_cycle_start))
    if not grocery_files and os.path.exists(os.path.join(data_dir, "grocery_list.csv")):
        grocery_files.append((os.path.join(data_dir, "grocery_list.csv"), current_cycle_start))

    lower_bound_run_date = max(current_cycle_start, last_dt.date())

    for g_file, file_cycle_start in grocery_files:
        try:
            with open(g_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception:
            continue

        runs_by_label: dict[str, list[dict]] = {}
        for r in rows:
            run_lbl = r.get("Run", "").strip()
            if run_lbl:
                runs_by_label.setdefault(run_lbl, []).append(r)

        for run_lbl, run_rows in runs_by_label.items():
            run_date = None
            try:
                run_date = datetime.strptime(run_lbl, "%Y-%m-%d").date()
            except ValueError:
                pass

            if run_date is None:
                for day_offset in range(7):
                    candidate_date = file_cycle_start + timedelta(days=day_offset)
                    if candidate_date.strftime("%A").lower() in run_lbl.lower():
                        run_date = candidate_date
                        break
                if run_date is None:
                    run_date = file_cycle_start

            if lower_bound_run_date <= run_date <= current_dt.date():
                run_key = f"{run_date.isoformat()}_{run_lbl}"
                if run_key not in state.assumed_runs:
                    run_display = run_lbl if "run" in run_lbl.lower() else f"{run_lbl} Run"
                    for item_row in run_rows:
                        raw_item_name = item_row.get("Item", "").strip()
                        qty_str = item_row.get("Quantity", "")
                        pkg_str = item_row.get("Package_Size", "")

                        qty_g = 0.0
                        m_pkgs = re.search(r"(\d+)\s*x", qty_str)
                        m_pkg_size = re.search(r"(\d+(?:\.\d+)?)\s*g", pkg_str)
                        if m_pkgs and m_pkg_size:
                            qty_g = float(m_pkgs.group(1)) * float(m_pkg_size.group(1))
                        else:
                            m_planned = re.search(r"\((\d+(?:\.\d+)?)\s*g", qty_str)
                            if m_planned:
                                qty_g = float(m_planned.group(1))
                            elif m_pkg_size:
                                qty_g = float(m_pkg_size.group(1))
                            else:
                                qty_g = 500.0

                        food_id = None
                        for cat_id, cat_ing in catalog_ingredients.items():
                            if cat_ing.name.lower() == raw_item_name.lower():
                                food_id = cat_id
                                break
                        if not food_id:
                            food_id = raw_item_name.lower().replace(" ", "_").replace("-", "_")

                        is_perishable = is_meat_or_perishable(food_id)

                        existing_actual = next((i for i in state.items if i.food_id == food_id and i.status == "actual"), None)
                        if existing_actual and existing_actual.quantity_g > 0:
                            continue

                        if is_perishable and user_has_actual_meat:
                            continue

                        if existing_actual and existing_actual.quantity_g <= 0:
                            existing_actual.quantity_g = round(qty_g, 2)
                            existing_actual.status = "assumed"
                            existing_actual.source = "planned_run"
                            existing_actual.purchased_date = run_date.isoformat()
                        else:
                            existing_assumed = next((i for i in state.items if i.food_id == food_id and i.status == "assumed"), None)
                            if existing_assumed:
                                existing_assumed.quantity_g = round(existing_assumed.quantity_g + qty_g, 2)
                            else:
                                state.items.append(
                                    InventoryItem(
                                        food_id=food_id,
                                        name=raw_item_name,
                                        quantity_g=round(qty_g, 2),
                                        status="assumed",
                                        source="planned_run",
                                        purchased_date=run_date.isoformat()
                                    )
                                )
                        actions.append(f"Assumed {int(round(qty_g))}g {raw_item_name} purchased from {run_display}")

                    state.assumed_runs.append(run_key)

    # 2. Check meal_logs.csv for skipped or eaten-out meal slots
    skipped_or_eatout_slots = set()
    meal_logs_path = os.path.join(data_dir, "meal_logs.csv")
    if os.path.exists(meal_logs_path):
        try:
            with open(meal_logs_path, "r", encoding="utf-8") as f:
                log_reader = csv.DictReader(f)
                for log_row in log_reader:
                    log_date = log_row.get("Date", "").strip()
                    log_meal = log_row.get("Meal", "").strip().lower()
                    log_adh = log_row.get("Adherence", "").strip().lower()
                    if log_adh in ("skipped", "eat_out", "eaten_out"):
                        skipped_or_eatout_slots.add((log_date, log_meal))
        except Exception:
            pass

    # 3. Process meal consumption between last_reconciled_at and current_dt
    cutoff_hours = {
        "breakfast": time(10, 0),
        "lunch": time(14, 30),
        "dinner": time(21, 0)
    }

    meal_files = []
    if os.path.exists(plans_dir):
        for fn in sorted(os.listdir(plans_dir)):
            if re.match(r"^\d{6}_meal_plan\.csv$", fn):
                meal_files.append(os.path.join(plans_dir, fn))
    if not meal_files and os.path.exists(plan_path):
        meal_files.append(plan_path)
    if not meal_files and os.path.exists(os.path.join(data_dir, "meal_plan.csv")):
        meal_files.append(os.path.join(data_dir, "meal_plan.csv"))

    all_meal_rows = []
    for m_file in meal_files:
        try:
            with open(m_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_meal_rows.extend(list(reader))
        except Exception:
            continue

    slot_order = {"breakfast": 0, "lunch": 1, "dinner": 2}
    def meal_sort_key(r):
        d = r.get("Date", "")
        m = r.get("Meal", "").lower()
        return (d, slot_order.get(m, 9))

    all_meal_rows.sort(key=meal_sort_key)

    for row in all_meal_rows:
        date_str = row.get("Date", "").strip()
        meal_name = row.get("Meal", "").strip()
        m_lower = meal_name.lower()
        cutoff_t = cutoff_hours.get(m_lower)
        if not cutoff_t or not date_str:
            continue

        try:
            m_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        cutoff_dt = datetime.combine(m_date, cutoff_t, tzinfo=tz)

        if last_dt < cutoff_dt <= current_dt:
            # If slot was recorded as skipped or eaten out, do NOT deduct home stock
            if (date_str, m_lower) in skipped_or_eatout_slots:
                continue

            ing_str = row.get("Ingredient", "")
            pieces = [p.strip() for p in re.split(r"[;,]", ing_str) if p.strip()]

            deducted_summaries = []
            for piece in pieces:
                m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:g|ml)?\s*(?:raw(?:/dry)?\s*)?(.*?)$", piece, re.IGNORECASE)
                if not m:
                    continue
                needed_g = float(m.group(1))
                ing_raw_name = m.group(2).strip()

                matched_item = _find_inventory_item(state.items, ing_raw_name, catalog_ingredients)
                if matched_item:
                    actual_deducted = min(matched_item.quantity_g, needed_g)
                    matched_item.quantity_g = max(0.0, round(matched_item.quantity_g - needed_g, 2))
                    if actual_deducted > 0:
                        deducted_summaries.append(f"{int(round(actual_deducted))}g {matched_item.name}")

            if deducted_summaries:
                actions.append(f"Assumed {date_str} {meal_name.capitalize()} consumed: deducted {', '.join(deducted_summaries)}")
            else:
                actions.append(f"Assumed {date_str} {meal_name.capitalize()} consumed")

    state.last_reconciled_at = current_dt.isoformat()
    save_inventory_state(data_dir, state)
    return state, actions


def _find_planned_meal(
    data_dir: str,
    target_date: str,
    slot_name: str,
    user_tz: str = "Europe/Brussels"
) -> Optional[dict]:
    """Locates the planned meal row for (target_date, slot_name) across active meal plans."""
    profile = load_user_profile(data_dir)
    effective_tz = user_tz if user_tz else (profile.timezone if profile else "Europe/Brussels")
    tz = resolve_timezone(effective_tz)

    plans_dir = os.path.join(data_dir, "plans")
    meal_files = []
    if os.path.exists(plans_dir):
        for fn in sorted(os.listdir(plans_dir)):
            if re.match(r"^\d{6}_meal_plan\.csv$", fn):
                meal_files.append(os.path.join(plans_dir, fn))

    if os.path.exists(os.path.join(data_dir, "meal_plan.csv")):
        meal_files.append(os.path.join(data_dir, "meal_plan.csv"))

    if not meal_files and profile:
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=tz)
        except Exception:
            target_dt = None
        ensure_weekly_plan_artifacts(profile, data_dir, reference_dt=target_dt)
        if os.path.exists(plans_dir):
            for fn in sorted(os.listdir(plans_dir)):
                if re.match(r"^\d{6}_meal_plan\.csv$", fn):
                    meal_files.append(os.path.join(plans_dir, fn))

    target_slot = slot_name.strip().lower()

    for m_file in meal_files:
        try:
            with open(m_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    r_date = row.get("Date", "").strip()
                    r_meal = row.get("Meal", "").strip().lower()
                    if r_date == target_date and r_meal == target_slot:
                        return row
        except Exception:
            continue

    if profile:
        try:
            from meal_planner.tools.meal_generator import generate_weekly_plan
            temp_plan = generate_weekly_plan(profile, start_date=target_date)
            for day in temp_plan.days:
                if day.date_str == target_date:
                    slot = getattr(day, target_slot, None)
                    if slot:
                        ing_str = "; ".join(
                            item.get("label", f"{int(round(item['raw_weight_g']))}g raw {item['name']}")
                            for item in slot.ingredients
                        )
                        return {
                            "Date": day.date_str,
                            "Meal": slot.meal_type.capitalize(),
                            "Recipe": slot.recipe_name,
                            "Ingredient": ing_str,
                            "P": str(int(round(slot.protein_g))),
                            "C": str(int(round(slot.carbs_g))),
                            "F": str(int(round(slot.fat_g))),
                            "Calories": str(int(round(slot.calories)))
                        }
        except Exception:
            pass

    return None


def reconcile_past_meal_deviation(
    data_dir: str,
    target_date: str,
    slot_name: str,
    deviation_type: str,
    eaten_description: Optional[str] = None,
    actual_calories: Optional[float] = None,
    actual_protein_g: Optional[float] = None,
    roll_over_difference: bool = True,
    user_tz: str = "Europe/Brussels"
) -> dict:
    """Reconciles a past meal deviation (e.g. skipped meal or eating out).
    
    1. Locates the planned meal in active meal plans.
    2. Restores each ingredient's quantity back into inventory.json (un-consumes it).
       If the item exists, increments quantity_g; if not, adds it with status='actual'.
    3. Logs the deviation to meal_logs.csv with appropriate adherence.
    4. If roll_over_difference is True, adds the deficit to carried_calories and carried_protein_g.
    
    Returns a summary dictionary.
    """
    state = load_inventory_state(data_dir)
    try:
        catalog_ingredients, _ = load_catalog(data_dir=data_dir)
    except Exception:
        catalog_ingredients = {}

    planned_meal = _find_planned_meal(data_dir, target_date, slot_name, user_tz)
    if not planned_meal:
        return {
            "success": False,
            "target_date": target_date,
            "slot_name": slot_name.lower(),
            "deviation_type": deviation_type,
            "message": f"Planned meal for {target_date} {slot_name} could not be found."
        }

    planned_calories = float(planned_meal.get("Calories", 0.0) or 0.0)
    planned_protein = float(planned_meal.get("P", 0.0) or 0.0)
    recipe_name = planned_meal.get("Recipe", "").strip() or slot_name.capitalize()

    # 1. Restore home ingredients into inventory
    ing_str = planned_meal.get("Ingredient", "")
    pieces = [p.strip() for p in re.split(r"[;,]", ing_str) if p.strip()]

    restored_items_count = 0
    restored_items = []
    for piece in pieces:
        m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:g|ml)?\s*(?:raw(?:/dry)?\s*)?(.*?)$", piece, re.IGNORECASE)
        if not m:
            continue
        qty_g = float(m.group(1))
        raw_name = m.group(2).strip()

        matched_item = _find_inventory_item(state.items, raw_name, catalog_ingredients)
        if matched_item:
            matched_item.quantity_g = round(matched_item.quantity_g + qty_g, 2)
            matched_item.status = "actual"
            matched_item.source = "user_report"
            restored_items_count += 1
            restored_items.append({
                "food_id": matched_item.food_id,
                "name": matched_item.name,
                "quantity_g": qty_g
            })
        else:
            food_id = None
            for cat_id, cat_ing in catalog_ingredients.items():
                if cat_ing.name.lower() == raw_name.lower():
                    food_id = cat_id
                    break
            if not food_id:
                for cat_id, cat_ing in catalog_ingredients.items():
                    if cat_ing.name.lower() in raw_name.lower() or raw_name.lower() in cat_ing.name.lower():
                        food_id = cat_id
                        break
            if not food_id:
                food_id = raw_name.lower().replace(" ", "_").replace("-", "_")

            new_item = InventoryItem(
                food_id=food_id,
                name=raw_name,
                quantity_g=round(qty_g, 2),
                status="actual",
                source="user_report",
                purchased_date=target_date
            )
            state.items.append(new_item)
            restored_items_count += 1
            restored_items.append({
                "food_id": food_id,
                "name": raw_name,
                "quantity_g": qty_g
            })

    # 2. Log to meal_logs.csv and compute deficit
    dev_lower = deviation_type.strip().lower()
    if dev_lower == "skipped":
        log_meal_consumption(data_dir, {
            "date": target_date,
            "meal": slot_name.lower(),
            "recipe": recipe_name,
            "adherence": "skipped",
            "calories": 0.0,
            "veg_g": 0,
            "fruit_g": 0,
            "notes": eaten_description or f"Skipped {slot_name.capitalize()} on {target_date}"
        })
        cal_deficit = planned_calories
        prot_deficit = planned_protein
        reported_act_cal = 0.0
        reported_act_prot = 0.0
    elif dev_lower in ("eat_out", "eaten_out"):
        reported_act_cal = float(actual_calories) if actual_calories is not None else planned_calories
        reported_act_prot = float(actual_protein_g) if actual_protein_g is not None else planned_protein
        log_meal_consumption(data_dir, {
            "date": target_date,
            "meal": slot_name.lower(),
            "recipe": eaten_description or f"Ate out ({recipe_name})",
            "adherence": "eat_out",
            "calories": reported_act_cal,
            "veg_g": 0,
            "fruit_g": 0,
            "notes": eaten_description or f"Ate out for {slot_name.capitalize()} on {target_date}"
        })
        cal_deficit = max(0.0, planned_calories - reported_act_cal)
        prot_deficit = max(0.0, planned_protein - reported_act_prot)
    else:
        reported_act_cal = float(actual_calories) if actual_calories is not None else planned_calories
        reported_act_prot = float(actual_protein_g) if actual_protein_g is not None else planned_protein
        log_meal_consumption(data_dir, {
            "date": target_date,
            "meal": slot_name.lower(),
            "recipe": eaten_description or recipe_name,
            "adherence": deviation_type,
            "calories": reported_act_cal,
            "veg_g": 0,
            "fruit_g": 0,
            "notes": eaten_description or f"Deviation for {slot_name.capitalize()} on {target_date}"
        })
        cal_deficit = max(0.0, planned_calories - reported_act_cal)
        prot_deficit = max(0.0, planned_protein - reported_act_prot)

    # 3. Roll over deficit if requested
    if roll_over_difference and cal_deficit > 0:
        state.carried_calories = round(state.carried_calories + cal_deficit, 2)
        state.carried_protein_g = round(state.carried_protein_g + prot_deficit, 2)

    save_inventory_state(data_dir, state)

    message = (
        f"Reconciled {deviation_type} for {target_date} {slot_name.capitalize()}. "
        f"Restored {restored_items_count} ingredient items to inventory. "
    )
    if roll_over_difference and cal_deficit > 0:
        message += f"Rolled over {int(round(cal_deficit))} kcal and {int(round(prot_deficit))}g protein deficit."

    return {
        "success": True,
        "target_date": target_date,
        "slot_name": slot_name.lower(),
        "deviation_type": deviation_type,
        "planned_recipe": recipe_name,
        "planned_calories": planned_calories,
        "planned_protein_g": planned_protein,
        "actual_calories": reported_act_cal if actual_calories is not None or dev_lower != "skipped" else 0.0,
        "actual_protein_g": reported_act_prot if actual_protein_g is not None or dev_lower != "skipped" else 0.0,
        "calorie_deficit": cal_deficit,
        "protein_deficit_g": prot_deficit,
        "restored_items_count": restored_items_count,
        "restored_items": restored_items,
        "carried_calories": state.carried_calories,
        "carried_protein_g": state.carried_protein_g,
        "message": message
    }


def spread_missed_calories(
    data_dir: str,
    max_daily_calories: float = 200.0,
    max_daily_protein_g: float = 15.0,
    user_tz: str = "Europe/Brussels",
    reference_dt: Optional[datetime] = None
) -> dict:
    """Spreads accumulated carried calories and protein debt across upcoming remaining days.
    
    Capped strictly at min(max_daily_calories, carried_calories / N) kcal/day and
    min(max_daily_protein_g, carried_protein / N) g protein/day.
    Updates active weekly meal plan CSV and deducts distributed amounts from inventory state.
    """
    state = load_inventory_state(data_dir)
    if state.carried_calories <= 0 and state.carried_protein_g <= 0:
        return {
            "success": True,
            "distributed": False,
            "daily_calorie_increase": 0.0,
            "daily_protein_increase_g": 0.0,
            "days_affected": 0,
            "dates_adjusted": [],
            "total_calories_distributed": 0.0,
            "total_protein_distributed_g": 0.0,
            "remaining_carried_calories": 0.0,
            "remaining_carried_protein_g": 0.0,
            "message": "No carried calories or protein to distribute."
        }

    profile = load_user_profile(data_dir)
    effective_tz = user_tz if user_tz else (profile.timezone if profile else "Europe/Brussels")
    tz = resolve_timezone(effective_tz)
    ref_dt = reference_dt if reference_dt is not None else datetime.now(tz)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=tz)
    else:
        ref_dt = ref_dt.astimezone(tz)

    start_day = getattr(profile, "week_start_day", "Saturday") if profile else "Saturday"
    prefix = get_current_cycle_prefix(effective_tz, reference_dt=ref_dt, week_start_day=start_day)

    plans_dir = os.path.join(data_dir, "plans")
    plan_path = os.path.join(plans_dir, f"{prefix}_meal_plan.csv")
    if not os.path.exists(plan_path) and profile:
        ensure_weekly_plan_artifacts(profile, data_dir, reference_dt=ref_dt)

    if not os.path.exists(plan_path):
        plan_path = os.path.join(data_dir, "meal_plan.csv")

    if not os.path.exists(plan_path):
        return {
            "success": False,
            "distributed": False,
            "daily_calorie_increase": 0.0,
            "daily_protein_increase_g": 0.0,
            "days_affected": 0,
            "dates_adjusted": [],
            "total_calories_distributed": 0.0,
            "total_protein_distributed_g": 0.0,
            "remaining_carried_calories": state.carried_calories,
            "remaining_carried_protein_g": state.carried_protein_g,
            "message": "No active meal plan found to distribute carried calories."
        }

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or ["Date", "Meal", "Recipe", "Ingredient", "P", "C", "F", "Calories"]
            rows = list(reader)
    except Exception as e:
        return {
            "success": False,
            "distributed": False,
            "message": f"Failed to read meal plan: {e}"
        }

    all_dates = []
    for r in rows:
        d = r.get("Date", "").strip()
        if d and d not in all_dates:
            all_dates.append(d)

    ref_date = ref_dt.date()
    upcoming_dates = [d for d in all_dates if datetime.strptime(d, "%Y-%m-%d").date() > ref_date]
    if not upcoming_dates:
        upcoming_dates = [d for d in all_dates if datetime.strptime(d, "%Y-%m-%d").date() >= ref_date]
    if not upcoming_dates:
        upcoming_dates = list(all_dates)

    N = len(upcoming_dates)
    if N == 0:
        return {
            "success": False,
            "distributed": False,
            "message": "No upcoming days found in meal plan."
        }

    daily_cal = min(max_daily_calories, round(state.carried_calories / N, 1))
    daily_prot = min(max_daily_protein_g, round(state.carried_protein_g / N, 1))

    if daily_cal <= 0 and daily_prot <= 0:
        return {
            "success": True,
            "distributed": False,
            "daily_calorie_increase": 0.0,
            "daily_protein_increase_g": 0.0,
            "days_affected": 0,
            "dates_adjusted": [],
            "total_calories_distributed": 0.0,
            "total_protein_distributed_g": 0.0,
            "remaining_carried_calories": state.carried_calories,
            "remaining_carried_protein_g": state.carried_protein_g,
            "message": "Carried calories and protein are negligible."
        }

    # Update rows for breakfast on upcoming days
    for row in rows:
        r_date = row.get("Date", "").strip()
        r_meal = row.get("Meal", "").strip().lower()
        if r_date in upcoming_dates and r_meal == "breakfast":
            old_p = float(row.get("P", 0.0) or 0.0)
            old_cal = float(row.get("Calories", 0.0) or 0.0)
            new_p = int(round(old_p + daily_prot))
            new_cal = int(round(old_cal + daily_cal))
            row["P"] = str(new_p)
            row["Calories"] = str(new_cal)

            extra_carbs = int(round(max(0.0, daily_cal - (daily_prot * 4.0)) / 4.0))
            if extra_carbs > 0:
                row["C"] = str(int(round(float(row.get("C", 0.0) or 0.0) + extra_carbs)))

            ing_str = row.get("Ingredient", "")
            whey_add_g = int(round(daily_prot / 0.8)) if daily_prot > 0 else 0
            oats_add_g = int(round(max(0.0, daily_cal - (daily_prot * 4.0)) / 3.7)) if daily_cal > (daily_prot * 4.0) else 0

            if whey_add_g > 0:
                m_whey = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|ml)?\s*(raw(?:/dry)?\s*Whey Protein Isolate)", ing_str, re.IGNORECASE)
                if m_whey:
                    cur_w = float(m_whey.group(1))
                    new_w = int(round(cur_w + whey_add_g))
                    ing_str = ing_str[:m_whey.start()] + f"{new_w}g {m_whey.group(2)}" + ing_str[m_whey.end():]
                else:
                    ing_str = f"{ing_str}; {whey_add_g}g raw/dry Whey Protein Isolate"

            if oats_add_g > 0:
                m_oats = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|ml)?\s*(raw(?:/dry)?\s*Rolled Oats)", ing_str, re.IGNORECASE)
                if m_oats:
                    cur_o = float(m_oats.group(1))
                    new_o = int(round(cur_o + oats_add_g))
                    ing_str = ing_str[:m_oats.start()] + f"{new_o}g {m_oats.group(2)}" + ing_str[m_oats.end():]
                else:
                    ing_str = f"{ing_str}; {oats_add_g}g raw/dry Rolled Oats"

            row["Ingredient"] = ing_str

    # Save to active plan CSV and root meal_plan.csv if it exists
    target_files = [plan_path]
    root_plan = os.path.join(data_dir, "meal_plan.csv")
    if root_plan != plan_path and os.path.exists(root_plan):
        target_files.append(root_plan)

    for tf in target_files:
        try:
            with open(tf, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except Exception:
            pass

    tot_cal_dist = round(daily_cal * N, 2)
    tot_prot_dist = round(daily_prot * N, 2)
    state.carried_calories = max(0.0, round(state.carried_calories - tot_cal_dist, 2))
    state.carried_protein_g = max(0.0, round(state.carried_protein_g - tot_prot_dist, 2))
    save_inventory_state(data_dir, state)

    return {
        "success": True,
        "distributed": True,
        "daily_calorie_increase": daily_cal,
        "daily_protein_increase_g": daily_prot,
        "days_affected": N,
        "dates_adjusted": upcoming_dates,
        "total_calories_distributed": tot_cal_dist,
        "total_protein_distributed_g": tot_prot_dist,
        "remaining_carried_calories": state.carried_calories,
        "remaining_carried_protein_g": state.carried_protein_g,
        "message": (
            f"Successfully spread {int(round(tot_cal_dist))} kcal (+{int(round(daily_cal))} kcal/day) "
            f"and {int(round(tot_prot_dist))}g protein (+{int(round(daily_prot))}g/day) "
            f"across {N} upcoming days."
        )
    }

