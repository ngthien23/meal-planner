import csv
import os
import re
from typing import Optional, Any
from datetime import datetime, timedelta

from meal_planner.tools.onboarding import resolve_timezone

__all__ = [
    "get_meal_plan_csv",
    "update_meal_plan_csv",
    "get_grocery_list_csv",
    "update_grocery_list_csv",
    "get_batch_cook_csv",
    "update_batch_cook_csv",
    "check_meal_plan_csv",
    "get_current_cycle_prefix",
    "check_and_apply_week_rollover"
]

def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val or 0.0)
    except (ValueError, TypeError):
        return default

DAY_NAME_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}

def get_current_cycle_prefix(
    user_timezone: str = "Europe/Brussels",
    reference_dt: Optional[datetime] = None,
    week_start_day: str = "Saturday"
) -> str:
    """Calculates the YYMMDD prefix for the cycle start date based on week_start_day."""
    tz = resolve_timezone(user_timezone)
    now = reference_dt if reference_dt is not None else datetime.now(tz)
    start_wd = DAY_NAME_MAP.get(week_start_day.lower(), 5)
    days_since_start = (now.weekday() - start_wd) % 7
    cycle_start = now - timedelta(days=days_since_start)
    return cycle_start.strftime("%y%m%d")

def _resolve_plan_path(data_dir: str, filename_pattern: str, prefix: Optional[str] = None) -> str:
    """Finds or resolves the path to an active plan file."""
    plans_dir = os.path.join(data_dir, "plans")
    os.makedirs(plans_dir, exist_ok=True)

    if prefix is not None:
        return os.path.join(plans_dir, f"{prefix}_{filename_pattern}")

    prefix = get_current_cycle_prefix("Europe/Brussels", week_start_day="Saturday")
    dated_name = f"{prefix}_{filename_pattern}"
    dated_path = os.path.join(plans_dir, dated_name)
    if os.path.exists(dated_path):
        return dated_path
    
    # Check if there is any matching file in plans/
    pattern_regex = re.compile(rf"^\d{{6}}_{re.escape(filename_pattern)}$")
    candidates = [os.path.join(plans_dir, f) for f in os.listdir(plans_dir) if pattern_regex.match(f)]
    if candidates:
        candidates.sort()
        return candidates[-1]
    
    # Check root file
    root_path = os.path.join(data_dir, filename_pattern)
    if os.path.exists(root_path):
        return root_path
        
    return dated_path


def get_meal_plan_csv(
    data_dir: str,
    target_date: Optional[str] = None,
    prefix: Optional[str] = None
) -> list[dict]:
    """Reads the active weekly meal plan CSV.
    
    Args:
        data_dir: Directory containing meal planner data.
        target_date: Optional 'YYYY-MM-DD' filter to return meals only for that date.
        prefix: Optional cycle prefix.
        
    Returns:
        List of row dicts: [{'Date': ..., 'Meal': ..., 'Recipe': ..., 'Ingredient': ..., 'P': ..., 'C': ..., 'F': ..., 'Calories': ...}]
    """
    path = _resolve_plan_path(data_dir, "meal_plan.csv", prefix=prefix)
    if not os.path.exists(path):
        return []

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if target_date and r.get("Date", "").strip() != target_date:
                continue
            rows.append(r)
    return rows


def update_meal_plan_csv(
    data_dir: str,
    updates: list[dict],
    prefix: Optional[str] = None
) -> dict:
    """Updates, replaces, or adds meal slots in the weekly meal plan CSV.
    
    Args:
        data_dir: Directory containing meal planner data.
        updates: List of row dicts containing at least 'Date' and 'Meal', plus any of:
                 'Recipe', 'Ingredient', 'P', 'C', 'F', 'Calories'.
        prefix: Optional cycle prefix.
        
    Returns:
        Summary dict confirming updates.
    """
    path = _resolve_plan_path(data_dir, "meal_plan.csv", prefix=prefix)
    fieldnames = ["Date", "Meal", "Recipe", "Ingredient", "P", "C", "F", "Calories"]
    
    existing_rows = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames
            existing_rows = list(reader)
    else:
        root_path = os.path.join(data_dir, "meal_plan.csv")
        if os.path.exists(root_path):
            with open(root_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or fieldnames
                existing_rows = list(reader)

    # Check if plan starting date has changed (a new plan is made)
    existing_dates = {r.get("Date", "").strip() for r in existing_rows if r.get("Date") and r.get("Date").strip()}
    new_dates = {str(item.get("Date", "")).strip() for item in updates if item.get("Date") and str(item.get("Date", "")).strip()}
    if existing_dates and new_dates:
        min_existing = min(existing_dates)
        min_new = min(new_dates)
        if new_dates.isdisjoint(existing_dates) and min_new > min_existing:
            from meal_planner.tools.memory import MemoryManager
            mem_mgr = MemoryManager(data_dir)
            daily_calories, daily_p, _, _ = _get_baseline_daily_targets(mem_mgr)
            prev_cal = sum(_safe_float(r.get("Calories", 0)) for r in existing_rows)
            prev_p = sum(_safe_float(r.get("P", 0)) for r in existing_rows)
            prev_days = len(existing_dates)
            net_cal = prev_cal - (daily_calories * prev_days)
            net_p = prev_p - (daily_p * prev_days)
            mem_mgr.rollover_weekly_memory(
                net_cal=net_cal,
                net_p=net_p,
                daily_cal_target=daily_calories,
                daily_p_target=daily_p
            )
            existing_rows = []

    # Index existing rows by (Date, Meal.lower())
    row_index = {}
    for i, r in enumerate(existing_rows):
        key = (r.get("Date", "").strip(), r.get("Meal", "").strip().lower())
        row_index[key] = i

    updated_count = 0
    added_count = 0
    dates_touched = set()

    for item in updates:
        d = str(item.get("Date", "")).strip()
        m = str(item.get("Meal", "")).strip().capitalize()
        if not d or not m:
            continue
            
        key = (d, m.lower())
        dates_touched.add(d)

        # Standardize numeric values
        p_val = str(int(round(float(item.get("P", 0) or 0))))
        c_val = str(int(round(float(item.get("C", 0) or 0))))
        f_val = str(int(round(float(item.get("F", 0) or 0))))
        cal_val = str(int(round(float(item.get("Calories", 0) or 0))))

        clean_row = {
            "Date": d,
            "Meal": m,
            "Recipe": str(item.get("Recipe", "")).strip(),
            "Ingredient": str(item.get("Ingredient", "")).strip(),
            "P": p_val,
            "C": c_val,
            "F": f_val,
            "Calories": cal_val
        }

        if key in row_index:
            idx = row_index[key]
            existing_rows[idx] = clean_row
            updated_count += 1
        else:
            existing_rows.append(clean_row)
            row_index[key] = len(existing_rows) - 1
            added_count += 1

    # Sort rows by Date then meal order
    meal_order = {"breakfast": 1, "lunch": 2, "dinner": 3, "snack": 4}
    def _sort_key(r):
        dt = r.get("Date", "")
        mo = meal_order.get(r.get("Meal", "").strip().lower(), 5)
        return (dt, mo)
        
    existing_rows.sort(key=_sort_key)

    # Save to dated path and root meal_plan.csv
    target_files = [path]
    root_file = os.path.join(data_dir, "meal_plan.csv")
    if root_file != path:
        target_files.append(root_file)

    for tf in target_files:
        os.makedirs(os.path.dirname(tf), exist_ok=True)
        with open(tf, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_rows)

    return {
        "success": True,
        "updated_count": updated_count,
        "added_count": added_count,
        "dates_updated": sorted(list(dates_touched)),
        "file_path": path,
        "message": f"Successfully updated {updated_count} meals and added {added_count} meals across dates: {', '.join(sorted(dates_touched))}."
    }


def _parse_qty_g(val: any) -> int:
    """Safely extracts integer gram weight from numeric or formatted quantity strings like '1x (450g planned)', '500g', etc."""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return max(0, int(round(val)))
    s = str(val).strip()
    if not s:
        return 0
    # First look for planned grams in parentheses e.g. "(348g planned)" or "(348g"
    m = re.search(r"\((\d+(?:\.\d+)?)\s*g", s)
    if m:
        return max(0, int(round(float(m.group(1)))))
    # Next look for grams suffix e.g. "500g" or "500 g"
    m = re.search(r"(\d+(?:\.\d+)?)\s*g", s)
    if m:
        return max(0, int(round(float(m.group(1)))))
    # Fallback to general integer or float
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        return max(0, int(round(float(m.group(1)))))
    return 0


def get_grocery_list_csv(
    data_dir: str,
    prefix: Optional[str] = None
) -> list[dict]:
    """Reads the active split grocery list CSV."""
    path = _resolve_plan_path(data_dir, "grocery_list.csv", prefix=prefix)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if "Quantity_g" in r and r.get("Quantity_g"):
                r["Quantity_g"] = str(_parse_qty_g(r["Quantity_g"]))
            else:
                raw_q = r.get("Quantity", "")
                r["Quantity_g"] = str(_parse_qty_g(raw_q))
            rows.append(r)
    return rows


def _run_sort_key(run_str: str) -> tuple:
    """Helper to sort grocery runs chronologically and logically."""
    s = str(run_str).strip()
    s_lower = s.lower()
    # Check if starts with ISO date e.g. "2026-10-12" or "261012"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return (0, m.group(1), s_lower)
    day_order = {
        "saturday": 1,
        "sunday": 2,
        "monday": 3,
        "tuesday": 4,
        "wednesday": 5,
        "thursday": 6,
        "friday": 7,
    }
    for day, order in day_order.items():
        if day in s_lower:
            return (1, order, s_lower)
    if "pantry" in s_lower:
        return (2, 99, s_lower)
    return (3, s_lower, s_lower)


def update_grocery_list_csv(
    data_dir: str,
    entries: list[dict],
    mode: str = "merge",
    prefix: Optional[str] = None
) -> dict:
    """Updates the active grocery list CSV.
    
    Args:
        data_dir: Directory containing meal planner data.
        entries: List of items: [{'Run': '2026-10-13 Run', 'Category': 'meat', 'Item': 'Chicken Breast', 'Quantity_g': 1000, 'Estimated_Price_EUR': 9.50}]
        mode: 'replace' to overwrite entire list with new entries; 'merge' to update/append items.
              If mode is 'merge' and Quantity_g <= 0, that item is pruned.
        prefix: Optional cycle prefix.
    """
    path = _resolve_plan_path(data_dir, "grocery_list.csv", prefix=prefix)
    fieldnames = ["Run", "Category", "Item", "Quantity_g", "Estimated_Price_EUR"]

    if mode == "replace":
        clean_rows = []
        for it in entries:
            raw_qty = it.get("Quantity_g") if "Quantity_g" in it else it.get("Quantity", 0)
            qty = _parse_qty_g(raw_qty)
            if qty <= 0:
                continue
            price_raw = str(it.get("Estimated_Price_EUR", 0.0) or it.get("Price", 0.0) or 0.0).replace("€", "").replace("$", "").replace("£", "").strip()
            try:
                price = float(price_raw or 0.0)
            except ValueError:
                price = 0.0
            clean_rows.append({
                "Run": str(it.get("Run", "")).strip(),
                "Category": str(it.get("Category", "other")).strip().lower(),
                "Item": str(it.get("Item", "")).strip(),
                "Quantity_g": str(qty),
                "Estimated_Price_EUR": f"{price:.2f}"
            })
    else:
        existing = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    raw_q = r.get("Quantity_g") or r.get("Quantity", "")
                    q_val = str(_parse_qty_g(raw_q))
                    price_raw = str(r.get("Estimated_Price_EUR", 0.0)).replace("€", "").replace("$", "").replace("£", "").strip()
                    try:
                        price = float(price_raw or 0.0)
                    except ValueError:
                        price = 0.0
                    existing.append({
                        "Run": str(r.get("Run", "")).strip(),
                        "Category": str(r.get("Category", "other")).strip().lower(),
                        "Item": str(r.get("Item", "")).strip(),
                        "Quantity_g": q_val,
                        "Estimated_Price_EUR": f"{price:.2f}"
                    })
        
        lookup = {(r["Run"].lower().strip(), r["Item"].lower().strip()): i for i, r in enumerate(existing)}
        for it in entries:
            r_run = str(it.get("Run", "")).strip()
            r_item = str(it.get("Item", "")).strip()
            key = (r_run.lower().strip(), r_item.lower().strip())
            raw_qty = it.get("Quantity_g") if "Quantity_g" in it else it.get("Quantity", 0)
            qty = _parse_qty_g(raw_qty)
            price_raw = str(it.get("Estimated_Price_EUR", 0.0) or it.get("Price", 0.0) or 0.0).replace("€", "").replace("$", "").replace("£", "").strip()
            try:
                price = float(price_raw or 0.0)
            except ValueError:
                price = 0.0
            cat = str(it.get("Category", "other")).strip().lower()

            if qty <= 0:
                if not r_run:
                    for idx, r in enumerate(existing):
                        if r and r["Item"].lower().strip() == r_item.lower().strip():
                            existing[idx] = None
                elif key in lookup:
                    idx = lookup[key]
                    existing[idx] = None
                continue

            row_data = {
                "Run": r_run,
                "Category": cat,
                "Item": r_item,
                "Quantity_g": str(qty),
                "Estimated_Price_EUR": f"{price:.2f}"
            }
            if key in lookup:
                existing[lookup[key]] = row_data
            else:
                existing.append(row_data)
                lookup[key] = len(existing) - 1

        clean_rows = [r for r in existing if r is not None]

    # Post-process: sort by [Run, Category]
    clean_rows.sort(
        key=lambda r: (
            _run_sort_key(r.get("Run", "")),
            r.get("Category", "").lower(),
            r.get("Item", "").lower()
        )
    )

    target_files = [path]
    root_file = os.path.join(data_dir, "grocery_list.csv")
    if root_file != path:
        target_files.append(root_file)

    for tf in target_files:
        os.makedirs(os.path.dirname(tf), exist_ok=True)
        with open(tf, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(clean_rows)

    return {
        "success": True,
        "total_items": len(clean_rows),
        "file_path": path,
        "message": f"Successfully updated grocery list ({len(clean_rows)} items)."
    }


def get_batch_cook_csv(data_dir: str, prefix: Optional[str] = None) -> list[dict]:
    """Reads the active batch cook CSV."""
    path = _resolve_plan_path(data_dir, "batch_cook.csv", prefix=prefix)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            dish = str(r.get("Dish", "")).strip()
            main_prot = str(r.get("Main_Protein") or r.get("Protein") or r.get("Ingredient") or "").strip()
            meals = str(r.get("Meals") or r.get("Meal_Count") or r.get("Portions") or r.get("Days_Served") or "").strip()
            if "," in meals:
                meals = str(len([d for d in meals.split(",") if d.strip()]))
            rows.append({
                "Dish": dish,
                "Main_Protein": main_prot,
                "Meals": meals
            })
    return rows


def update_batch_cook_csv(
    data_dir: str,
    entries: list[dict],
    prefix: Optional[str] = None
) -> dict:
    """Updates the active batch cook CSV."""
    path = _resolve_plan_path(data_dir, "batch_cook.csv", prefix=prefix)
    fieldnames = ["Dish", "Main_Protein", "Meals"]

    clean_rows = []
    for it in entries:
        dish = str(it.get("Dish", "")).strip()
        main_prot = str(it.get("Main_Protein") or it.get("Protein") or it.get("Ingredient") or "").strip()
        meals_val = str(it.get("Meals") or it.get("Meal_Count") or it.get("Portions") or it.get("Days_Served") or "").strip()
        if "," in meals_val:
            meals_val = str(len([d for d in meals_val.split(",") if d.strip()]))
        clean_rows.append({
            "Dish": dish,
            "Main_Protein": main_prot,
            "Meals": meals_val
        })

    target_files = [path]
    root_file = os.path.join(data_dir, "batch_cook.csv")
    if root_file != path:
        target_files.append(root_file)

    for tf in target_files:
        os.makedirs(os.path.dirname(tf), exist_ok=True)
        with open(tf, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(clean_rows)

    return {
        "success": True,
        "total_dishes": len(clean_rows),
        "file_path": path,
        "message": f"Successfully updated batch cook instructions ({len(clean_rows)} dishes)."
    }


def _get_baseline_daily_targets(mem_mgr: Any) -> tuple[float, float, float, float]:
    """Helper to extract daily calorie, protein, carb, and fat targets from memory."""
    mem_ctx = mem_mgr.get_context()
    long_term_notes = mem_ctx.get("long_term", [])

    daily_calories = None
    daily_p = None
    daily_c = None
    daily_f = None
    bodyweight = None

    for note in long_term_notes:
        bw_m = re.search(r"(?:bodyweight|weight)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*kg", note, re.I)
        if not bw_m:
            bw_m = re.search(r"(\d+(?:\.\d+)?)\s*kg\b", note, re.I)
        if bw_m and bodyweight is None:
            bodyweight = float(bw_m.group(1))

        cal_m = re.search(r"(?:target\s+calories|calories?)\s*[:=]?\s*(\d+(?:\.\d+)?)", note, re.I)
        if not cal_m:
            cal_m = re.search(r"(\d{3,4})\s*(?:kcal|calories)", note, re.I)
        if cal_m and daily_calories is None:
            daily_calories = float(cal_m.group(1))

        p_m = re.search(r"(?:protein|target\s+protein)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*g", note, re.I)
        if not p_m:
            p_m = re.search(r"(\d+(?:\.\d+)?)\s*g\s*protein", note, re.I)
        if p_m and daily_p is None:
            daily_p = float(p_m.group(1))

        c_m = re.search(r"(?:carbs?|target\s+carbs?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*g", note, re.I)
        if not c_m:
            c_m = re.search(r"(\d+(?:\.\d+)?)\s*g\s*carbs?", note, re.I)
        if c_m and daily_c is None:
            daily_c = float(c_m.group(1))

        f_m = re.search(r"(?:fat|target\s+fat)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*g", note, re.I)
        if not f_m:
            f_m = re.search(r"(\d+(?:\.\d+)?)\s*g\s*fat", note, re.I)
        if f_m and daily_f is None:
            daily_f = float(f_m.group(1))

    if daily_calories is None:
        daily_calories = 2500.0
    if daily_p is None:
        daily_p = round(bodyweight * 2.2, 1) if bodyweight else 150.0
    if daily_f is None:
        daily_f = round(bodyweight * 0.9, 1) if bodyweight else round(daily_calories * 0.25 / 9.0, 1)
    if daily_c is None:
        daily_c = max(0.0, round((daily_calories - (daily_p * 4.0) - (daily_f * 9.0)) / 4.0, 1))

    return daily_calories, daily_p, daily_c, daily_f


def check_and_apply_week_rollover(
    data_dir: str,
    current_prefix: Optional[str] = None,
    user_timezone: str = "Europe/Brussels"
) -> dict:
    """Checks if transitioning to a new week cycle and rolls over any substantial net diffs."""
    from meal_planner.tools.memory import MemoryManager
    if current_prefix is None:
        current_prefix = get_current_cycle_prefix(user_timezone)

    plans_dir = os.path.join(data_dir, "plans")
    if not os.path.exists(plans_dir):
        return {"rolled_over": False, "carried": False}

    pattern = re.compile(r"^(\d{6})_meal_plan\.csv$")
    candidates = []
    for f in os.listdir(plans_dir):
        m = pattern.match(f)
        if m and m.group(1) < current_prefix:
            candidates.append((m.group(1), os.path.join(plans_dir, f)))

    if not candidates:
        return {"rolled_over": False, "carried": False}

    candidates.sort(key=lambda x: x[0])
    prev_prefix, prev_path = candidates[-1]

    curr_path = os.path.join(plans_dir, f"{current_prefix}_meal_plan.csv")
    if os.path.exists(curr_path):
        return {"rolled_over": False, "carried": False}

    mem_mgr = MemoryManager(data_dir)
    weekly_notes = mem_mgr.get_context().get("weekly", [])
    if any(
        "carried from last week" in n.lower()
        or f"cycle {current_prefix.lower()}" in n.lower()
        for n in weekly_notes
    ):
        return {"rolled_over": False, "carried": any("carried from last week" in n.lower() for n in weekly_notes)}

    prev_rows = []
    with open(prev_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        prev_rows = list(reader)

    if not prev_rows:
        return {"rolled_over": False, "carried": False}

    prev_dates = {r.get("Date", "").strip() for r in prev_rows if r.get("Date") and r.get("Date").strip()}
    prev_days = len(prev_dates) if prev_dates else 7

    daily_calories, daily_p, _, _ = _get_baseline_daily_targets(mem_mgr)
    prev_cal = sum(_safe_float(r.get("Calories", 0)) for r in prev_rows)
    prev_p = sum(_safe_float(r.get("P", 0)) for r in prev_rows)

    net_cal = prev_cal - (daily_calories * prev_days)
    net_p = prev_p - (daily_p * prev_days)

    rollover_res = mem_mgr.rollover_weekly_memory(
        net_cal=net_cal,
        net_p=net_p,
        daily_cal_target=daily_calories,
        daily_p_target=daily_p,
        cycle_prefix=current_prefix
    )

    return {
        "rolled_over": True,
        "carried": rollover_res.get("carried", False),
        "prev_prefix": prev_prefix,
        "current_prefix": current_prefix,
        "net_cal": rollover_res.get("net_cal"),
        "net_p": rollover_res.get("net_p"),
        "note": rollover_res.get("note")
    }


def check_meal_plan_csv(
    data_dir: str,
    target_weekly_calories: Optional[float] = None,
    target_weekly_p: Optional[float] = None,
    target_weekly_c: Optional[float] = None,
    target_weekly_f: Optional[float] = None,
    prefix: Optional[str] = None
) -> dict:
    """Checks the weekly meal plan sums against target calories and macros.
    
    Verifies that total planned weekly Calories, P, C, and F approximate the target
    goals, including carried deficits or surpluses from last week recorded in memory.
    
    Args:
        data_dir: Directory containing meal planner data.
        target_weekly_calories: Optional explicit weekly calorie goal.
        target_weekly_p: Optional explicit weekly protein goal (g).
        target_weekly_c: Optional explicit weekly carb goal (g).
        target_weekly_f: Optional explicit weekly fat goal (g).
        prefix: Optional cycle prefix.
        
    Returns:
        Result dict with 'status' ('ACCEPTED' or 'NEEDS_FIXING'), 'accepted' (bool),
        'message', 'planned', 'target', and 'discrepancies'.
    """
    from meal_planner.tools.memory import MemoryManager

    rows = get_meal_plan_csv(data_dir, prefix=prefix)
    if not rows:
        return {
            "status": "NEEDS_FIXING",
            "accepted": False,
            "message": "[NEEDS FIXING] No meal plan found in meal_plan.csv. Please generate and save a meal plan using tool_update_plans first.",
            "planned": {"calories": 0.0, "P": 0.0, "C": 0.0, "F": 0.0},
            "target": {"calories": 0.0, "P": 0.0, "C": 0.0, "F": 0.0},
            "discrepancies": ["No meals planned."],
            "daily_deviations": []
        }

    planned_calories = 0.0
    planned_p = 0.0
    planned_c = 0.0
    planned_f = 0.0
    unique_dates = set()

    for r in rows:
        d = r.get("Date", "").strip()
        if d:
            unique_dates.add(d)
        try:
            planned_calories += float(r.get("Calories", 0) or 0)
        except (ValueError, TypeError):
            pass
        try:
            planned_p += float(r.get("P", 0) or 0)
        except (ValueError, TypeError):
            pass
        try:
            planned_c += float(r.get("C", 0) or 0)
        except (ValueError, TypeError):
            pass
        try:
            planned_f += float(r.get("F", 0) or 0)
        except (ValueError, TypeError):
            pass

    num_days = len(unique_dates) if len(unique_dates) > 0 else 7

    # Load memory context for targets and carried numbers
    mem_mgr = MemoryManager(data_dir)
    mem_ctx = mem_mgr.get_context()
    weekly_notes = mem_ctx.get("weekly", [])

    daily_calories, daily_p, daily_c, daily_f = _get_baseline_daily_targets(mem_mgr)

    # Daily aggregation & Short-Term Memory deviation recording
    daily_totals = {}
    for r in rows:
        d = str(r.get("Date", "")).strip()
        if not d:
            continue
        if d not in daily_totals:
            daily_totals[d] = {"calories": 0.0, "p": 0.0, "c": 0.0, "f": 0.0}
        try:
            daily_totals[d]["calories"] += float(r.get("Calories", 0) or 0)
        except (ValueError, TypeError):
            pass
        try:
            daily_totals[d]["p"] += float(r.get("P", 0) or 0)
        except (ValueError, TypeError):
            pass
        try:
            daily_totals[d]["c"] += float(r.get("C", 0) or 0)
        except (ValueError, TypeError):
            pass
        try:
            daily_totals[d]["f"] += float(r.get("F", 0) or 0)
        except (ValueError, TypeError):
            pass

    daily_deviations = []
    for d in sorted(daily_totals.keys()):
        totals = daily_totals[d]
        dev_res = mem_mgr.record_daily_deviation(
            date=d,
            planned_cal=totals["calories"],
            target_cal=daily_calories,
            planned_p=totals["p"],
            target_p=daily_p,
            cal_threshold=0.15,
            p_threshold=0.10
        )
        if dev_res.get("deviating"):
            daily_deviations.append({
                "date": d,
                "planned_cal": totals["calories"],
                "target_cal": daily_calories,
                "cal_diff": dev_res.get("cal_diff"),
                "planned_p": totals["p"],
                "target_p": daily_p,
                "p_diff": dev_res.get("p_diff"),
                "note": dev_res.get("note")
            })

    # Prune any deviation notes in weekly.md for dates not in the active plan
    curr_weekly = mem_mgr.get_context().get("weekly", [])
    pruned_notes = []
    changed_weekly = False
    for n in curr_weekly:
        m = re.match(r"^\[?(\d{4}-\d{2}-\d{2})\]?\s*Daily\s+deviation:", n, re.I)
        if m and m.group(1) not in daily_totals:
            changed_weekly = True
        else:
            pruned_notes.append(n)
    if changed_weekly:
        mem_mgr._write_notes(mem_mgr.weekly_path, pruned_notes)

    # Parse carried adjustments from weekly notes
    carried_cals = 0.0
    carried_p = 0.0
    carried_c = 0.0
    carried_f = 0.0

    for note in weekly_notes:
        n_lower = note.lower()
        if "daily deviation:" in n_lower:
            continue
        if not any(k in n_lower for k in ("carried", "deficit", "surplus", "last week", "missed", "to cut", "to eat", "rollover")):
            continue

        if "net weekly deviation:" in n_lower:
            m_cal = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:kcal|calories)", note, re.I)
            if m_cal:
                dev_val = float(m_cal.group(1))
                carried_cals += -dev_val
            m_p = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:g\s*protein|g\s*p\b|p\b)", note, re.I)
            if m_p:
                dev_val = float(m_p.group(1))
                carried_p += -dev_val
            continue

        is_cut = any(k in n_lower for k in ("cut", "surplus", "reduce", "over")) and not any(k in n_lower for k in ("deficit", "to eat"))
        default_mult = -1.0 if is_cut else 1.0

        for cm in re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*(?:kcal|calories)", note, re.I):
            val_str = cm.group(1)
            val = float(val_str)
            if val_str.startswith("+"):
                carried_cals += abs(val)
            elif val_str.startswith("-"):
                carried_cals -= abs(val)
            else:
                carried_cals += val * default_mult

        for pm in re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*(?:g\s*protein|g\s*p\b|p\b)", note, re.I):
            val_str = pm.group(1)
            val = float(val_str)
            if val_str.startswith("+"):
                carried_p += abs(val)
            elif val_str.startswith("-"):
                carried_p -= abs(val)
            else:
                carried_p += val * default_mult

        for c_m in re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*(?:g\s*carbs?|g\s*c\b|c\b)", note, re.I):
            val_str = c_m.group(1)
            val = float(val_str)
            if val_str.startswith("+"):
                carried_c += abs(val)
            elif val_str.startswith("-"):
                carried_c -= abs(val)
            else:
                carried_c += val * default_mult

        for fm in re.finditer(r"([+-]?\d+(?:\.\d+)?)\s*(?:g\s*fat|g\s*f\b|f\b)", note, re.I):
            val_str = fm.group(1)
            val = float(val_str)
            if val_str.startswith("+"):
                carried_f += abs(val)
            elif val_str.startswith("-"):
                carried_f -= abs(val)
            else:
                carried_f += val * default_mult

    # Determine effective weekly targets
    target_cals = target_weekly_calories if target_weekly_calories is not None else ((daily_calories * num_days) + carried_cals)
    target_p = target_weekly_p if target_weekly_p is not None else ((daily_p * num_days) + carried_p)
    target_c = target_weekly_c if target_weekly_c is not None else ((daily_c * num_days) + carried_c)
    target_f = target_weekly_f if target_weekly_f is not None else ((daily_f * num_days) + carried_f)

    discrepancies = []

    # Calories: tolerance ±5% (buffer at least 150 kcal across week)
    cal_buffer = max(150.0, target_cals * 0.05)
    if planned_calories < (target_cals - cal_buffer):
        diff = target_cals - planned_calories
        pct = (diff / target_cals) * 100 if target_cals > 0 else 0
        discrepancies.append(f"Calories too low: Planned {int(planned_calories)} kcal vs Target {int(target_cals)} kcal (deficit of {int(diff)} kcal, -{pct:.1f}%).")
    elif planned_calories > (target_cals + cal_buffer):
        diff = planned_calories - target_cals
        pct = (diff / target_cals) * 100 if target_cals > 0 else 0
        discrepancies.append(f"Calories too high: Planned {int(planned_calories)} kcal vs Target {int(target_cals)} kcal (surplus of {int(diff)} kcal, +{pct:.1f}%).")

    # Protein: tolerance -5% to +10% (buffer at least 15g)
    p_buffer_low = max(15.0, target_p * 0.05)
    p_buffer_high = max(25.0, target_p * 0.10)
    if planned_p < (target_p - p_buffer_low):
        diff = target_p - planned_p
        pct = (diff / target_p) * 100 if target_p > 0 else 0
        discrepancies.append(f"Protein too low: Planned {int(planned_p)}P vs Target {int(target_p)}P (deficit of {int(diff)}P, -{pct:.1f}%). Consider adding high-protein ingredients or whey shakes.")
    elif planned_p > (target_p + p_buffer_high):
        diff = planned_p - target_p
        pct = (diff / target_p) * 100 if target_p > 0 else 0
        discrepancies.append(f"Protein too high: Planned {int(planned_p)}P vs Target {int(target_p)}P (surplus of {int(diff)}P, +{pct:.1f}%).")

    # Carbs: tolerance ±10% (buffer at least 30g)
    if target_c > 0:
        c_buffer = max(30.0, target_c * 0.10)
        if planned_c < (target_c - c_buffer):
            diff = target_c - planned_c
            pct = (diff / target_c) * 100
            discrepancies.append(f"Carbs too low: Planned {int(planned_c)}C vs Target {int(target_c)}C (deficit of {int(diff)}C, -{pct:.1f}%).")
        elif planned_c > (target_c + c_buffer):
            diff = planned_c - target_c
            pct = (diff / target_c) * 100
            discrepancies.append(f"Carbs too high: Planned {int(planned_c)}C vs Target {int(target_c)}C (surplus of {int(diff)}C, +{pct:.1f}%).")

    # Fat: tolerance ±10% (buffer at least 15g)
    if target_f > 0:
        f_buffer = max(15.0, target_f * 0.10)
        if planned_f < (target_f - f_buffer):
            diff = target_f - planned_f
            pct = (diff / target_f) * 100
            discrepancies.append(f"Fat too low: Planned {int(planned_f)}F vs Target {int(target_f)}F (deficit of {int(diff)}F, -{pct:.1f}%).")
        elif planned_f > (target_f + f_buffer):
            diff = planned_f - target_f
            pct = (diff / target_f) * 100
            discrepancies.append(f"Fat too high: Planned {int(planned_f)}F vs Target {int(target_f)}F (surplus of {int(diff)}F, +{pct:.1f}%).")

    carried_str = ""
    if carried_cals != 0 or carried_p != 0 or carried_c != 0 or carried_f != 0:
        parts = []
        if carried_cals != 0:
            parts.append(f"{int(carried_cals):+d} kcal")
        if carried_p != 0:
            parts.append(f"{int(carried_p):+d}P")
        if carried_c != 0:
            parts.append(f"{int(carried_c):+d}C")
        if carried_f != 0:
            parts.append(f"{int(carried_f):+d}F")
        carried_str = f"  (Base: {int(daily_calories * num_days)} kcal, Carried adjustment from last week: {', '.join(parts)})\n"

    dev_str = ""
    if daily_deviations:
        dev_lines = [
            f"  - [{d['date']}] {d['cal_diff']:+d} kcal, {d['p_diff']:+d}g P vs target "
            f"({int(d['planned_cal'])} kcal / {int(d['planned_p'])}g P planned)"
            for d in daily_deviations
        ]
        dev_str = "Daily intake deviations recorded in Short-Term Memory:\n" + "\n".join(dev_lines) + "\n\n"

    if not discrepancies:
        msg = (
            f"[ACCEPTED] Weekly meal plan matches nutritional goals within acceptable approximation!\n"
            f"- Planned Weekly: {int(planned_calories)} kcal | {int(planned_p)}P | {int(planned_c)}C | {int(planned_f)}F\n"
            f"- Target Weekly: {int(target_cals)} kcal | {int(target_p)}P | {int(target_c)}C | {int(target_f)}F\n"
            f"{carried_str}"
            f"{dev_str}"
            f"Everything checked. The meal plan is approved. Validation is complete (do NOT call tool_check_meal_plan or tool_get_meal_plan again)."
        )
        return {
            "status": "ACCEPTED",
            "accepted": True,
            "message": msg,
            "planned": {"calories": planned_calories, "P": planned_p, "C": planned_c, "F": planned_f},
            "target": {"calories": target_cals, "P": target_p, "C": target_c, "F": target_f},
            "discrepancies": [],
            "daily_deviations": daily_deviations
        }
    else:
        issues_str = "\n".join(f"- {d}" for d in discrepancies)
        msg = (
            f"[NEEDS FIXING] Weekly meal plan does not approximate the target goals:\n"
            f"{issues_str}\n\n"
            f"Summary:\n"
            f"- Planned Weekly: {int(planned_calories)} kcal | {int(planned_p)}P | {int(planned_c)}C | {int(planned_f)}F\n"
            f"- Target Weekly: {int(target_cals)} kcal | {int(target_p)}P | {int(target_c)}C | {int(target_f)}F\n"
            f"{carried_str}"
            f"{dev_str}"
            f"Request: Please adjust the meal plan using tool_update_plans to fix these discrepancies, then re-check with tool_check_meal_plan."
        )
        return {
            "status": "NEEDS_FIXING",
            "accepted": False,
            "message": msg,
            "planned": {"calories": planned_calories, "P": planned_p, "C": planned_c, "F": planned_f},
            "target": {"calories": target_cals, "P": target_p, "C": target_c, "F": target_f},
            "discrepancies": discrepancies,
            "daily_deviations": daily_deviations
        }

