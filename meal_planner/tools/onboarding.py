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
    target = aliases.get(cleaned.upper(), cleaned)
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

    # Determine meal type
    if any(k in expr for k in ["breakfast", "morning", "shake"]):
        meal_type = "breakfast"
    elif any(k in expr for k in ["lunch", "noon"]):
        meal_type = "lunch"
    elif any(k in expr for k in ["dinner", "tonight", "night", "evening"]):
        meal_type = "dinner"
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
        restrictions=profile_data.get("restrictions", [
            "no dairy milk (fortified soy only)",
            "ON whey only",
            "canned tuna only (no fresh tuna)"
        ]),
        texture_rules=profile_data.get("texture_rules", {
            "breakfast": "soft_or_liquid",
            "lunch": "solid_batch",
            "dinner": "broth_or_soft"
        }),
        batch_prep_days=profile_data.get("batch_prep_days", ["Sunday", "Wednesday"])
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
    return UserProfile(**data)
