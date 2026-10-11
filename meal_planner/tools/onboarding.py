import zoneinfo

def resolve_timezone(tz_input: str) -> zoneinfo.ZoneInfo:
    """Safely resolves an IANA or common timezone string with UTC fallback."""
    cleaned = (tz_input or "Europe/Brussels").strip()
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
