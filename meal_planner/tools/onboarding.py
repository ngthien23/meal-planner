import json
import os
import re
from datetime import datetime, timedelta
import zoneinfo
from typing import Optional
from meal_planner.models import UserProfile

def resolve_timezone(tz_input: str) -> zoneinfo.ZoneInfo:
    """Safely resolves an IANA or common timezone string with UTC fallback."""
    cleaned = tz_input.strip()
    # Common alias mappings
    aliases = {
        "UTC": "UTC",
        "GMT": "UTC",
        "CET": "Europe/Brussels",
        "CEST": "Europe/Brussels",
        "EST": "America/New_York",
        "EDT": "America/New_York",
        "CST": "America/Chicago",
        "CDT": "America/Chicago",
        "PST": "America/Los_Angeles",
        "PDT": "America/Los_Angeles",
        "UTC+1": "Europe/Paris",
        "UTC+2": "Europe/Brussels",
        "UTC+7": "Asia/Ho_Chi_Minh",
        "ICT": "Asia/Ho_Chi_Minh",
    }
    # Normalize case for common zones like 'europe/brussels' -> 'Europe/Brussels'
    parts = cleaned.split("/")
    if len(parts) == 2:
        normalized_target = f"{parts[0].capitalize()}/{parts[1].capitalize()}"
    else:
        normalized_target = cleaned

    target = aliases.get(cleaned.upper(), normalized_target)
    try:
        return zoneinfo.ZoneInfo(target)
    except Exception:
        return zoneinfo.ZoneInfo("UTC")

def get_relative_datetime(
    relative_expr: str,
    tz_name: str = "UTC",
    reference_dt: Optional[datetime] = None
) -> tuple[datetime, str]:
    """Resolves relative date and meal type (e.g. 'tonight' -> (dt, 'dinner'))."""
    tz = resolve_timezone(tz_name)
    now = reference_dt if reference_dt is not None else datetime.now(tz)
    expr = relative_expr.lower().strip()

    # Determine meal type: prioritize explicit time-of-day / meal slots first
    if any(k in expr for k in ["dinner", "tonight", "night", "evening"]):
        meal_type = "dinner"
    elif any(k in expr for k in ["lunch", "noon"]):
        meal_type = "lunch"
    elif any(k in expr for k in ["breakfast", "morning"]):
        meal_type = "breakfast"
    elif "shake" in expr:
        meal_type = "breakfast"
    else:
        meal_type = "dinner"

    # Determine date
    days_offset = 0
    if "tomorrow" in expr:
        days_offset = 1
    elif "yesterday" in expr:
        days_offset = -1
    elif "today" in expr or "tonight" in expr:
        days_offset = 0
    else:
        # Check day names
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        matched_day = None
        for i, d in enumerate(day_names):
            if d in expr:
                matched_day = i
                break
        if matched_day is not None:
            current_weekday = now.weekday()
            days_ahead = (matched_day - current_weekday) % 7
            days_offset = days_ahead

    target_dt = now + timedelta(days=days_offset)
    return target_dt, meal_type

from dataclasses import fields

def init_user_profile(data_dir: str, profile_data: dict) -> UserProfile:
    """Initializes and persists UserProfile to profile.json."""
    os.makedirs(data_dir, exist_ok=True)
    profile = UserProfile(
        timezone=profile_data.get("timezone", "UTC"),
        bodyweight_kg=float(profile_data.get("bodyweight_kg", 65.0)),
        goal_state=profile_data.get("goal_state", "lean_bulk"),
        target_calories=float(profile_data.get("target_calories", 2550.0)),
        protein_multiplier=float(profile_data.get("protein_multiplier", 2.3)),
        fat_multiplier=float(profile_data.get("fat_multiplier", 1.0)),
        restrictions=profile_data.get("restrictions", []),
        texture_rules=profile_data.get("texture_rules", {
            "breakfast": "soft_or_liquid",
            "lunch": "solid_batch",
            "dinner": "broth_or_soft"
        }),
        batch_prep_days=profile_data.get("batch_prep_days", ["Sunday", "Wednesday"]),
        week_start_day=profile_data.get("week_start_day", "Saturday"),
        weeks_ahead=int(profile_data.get("weeks_ahead", 1)),
        currency=profile_data.get("currency", "EUR"),
        is_onboarded=bool(profile_data.get("is_onboarded", True))
    )
    profile_path = os.path.join(data_dir, "profile.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile.__dict__, f, indent=2)
    return profile

def load_user_profile(data_dir: str) -> Optional[UserProfile]:
    """Loads UserProfile from profile.json if present."""
    profile_path = os.path.join(data_dir, "profile.json")
    if not os.path.exists(profile_path):
        return None
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    valid_data = {k: v for k, v in data.items() if k in {f.name for f in fields(UserProfile)}}
    return UserProfile(**valid_data)
