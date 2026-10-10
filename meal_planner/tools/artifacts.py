import csv
import os
import re
from typing import Optional
from datetime import datetime

from meal_planner.tools.onboarding import load_user_profile, resolve_timezone
from meal_planner.tools.meal_generator import get_current_cycle_prefix, ensure_weekly_plan_artifacts

__all__ = [
    "get_meal_plan_csv",
    "update_meal_plan_csv",
    "get_grocery_list_csv",
    "update_grocery_list_csv",
    "get_batch_cook_csv",
    "update_batch_cook_csv"
]

def _resolve_plan_path(data_dir: str, filename_pattern: str, prefix: Optional[str] = None) -> str:
    """Finds or resolves the path to an active plan file."""
    profile = load_user_profile(data_dir)
    user_tz = profile.timezone if profile else "Europe/Brussels"
    week_start = getattr(profile, "week_start_day", "Saturday") if profile else "Saturday"
    
    if prefix is None:
        prefix = get_current_cycle_prefix(user_tz, week_start_day=week_start)
    
    plans_dir = os.path.join(data_dir, "plans")
    os.makedirs(plans_dir, exist_ok=True)
    
    # Try dated pattern first
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
        profile = load_user_profile(data_dir)
        if profile and profile.is_onboarded and profile.target_calories > 0:
            ensure_weekly_plan_artifacts(profile, data_dir)
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
            rows.append(r)
    return rows


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
            qty = int(round(float(it.get("Quantity_g", 0) or 0)))
            if qty <= 0:
                continue
            clean_rows.append({
                "Run": str(it.get("Run", "")).strip(),
                "Category": str(it.get("Category", "other")).strip().lower(),
                "Item": str(it.get("Item", "")).strip(),
                "Quantity_g": str(qty),
                "Estimated_Price_EUR": f"{float(it.get('Estimated_Price_EUR', 0.0) or 0.0):.2f}"
            })
    else:
        existing = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or fieldnames
                existing = list(reader)
        
        lookup = {(r.get("Run", "").strip(), r.get("Item", "").strip().lower()): i for i, r in enumerate(existing)}
        for it in entries:
            r_run = str(it.get("Run", "")).strip()
            r_item = str(it.get("Item", "")).strip()
            key = (r_run, r_item.lower())
            qty = int(round(float(it.get("Quantity_g", 0) or 0)))
            price = float(it.get("Estimated_Price_EUR", 0.0) or 0.0)
            cat = str(it.get("Category", "other")).strip().lower()

            if qty <= 0:
                if key in lookup:
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
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def update_batch_cook_csv(
    data_dir: str,
    entries: list[dict],
    prefix: Optional[str] = None
) -> dict:
    """Updates the active batch cook CSV."""
    path = _resolve_plan_path(data_dir, "batch_cook.csv", prefix=prefix)
    fieldnames = ["Dish", "Ingredient", "Grocery_Run", "Prep_Day", "Days_Served"]

    clean_rows = []
    for it in entries:
        clean_rows.append({
            "Dish": str(it.get("Dish", "")).strip(),
            "Ingredient": str(it.get("Ingredient", "")).strip(),
            "Grocery_Run": str(it.get("Grocery_Run", "")).strip(),
            "Prep_Day": str(it.get("Prep_Day", "")).strip(),
            "Days_Served": str(it.get("Days_Served", "")).strip()
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
