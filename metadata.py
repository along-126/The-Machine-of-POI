"""No automatic GPS inference or camera time claims: editable user metadata only."""
from __future__ import annotations
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def clock_text(config: dict, source_is_remote=False, now=None) -> str | None:
    """Return YYYY-MM-DD HH:MM:SS or NO SIGNAL. Hidden returns None."""
    if not config.get("show", True):
        return None
    if config.get("manual", False):
        try:
            base = datetime.fromisoformat(config["clock_base"])
            passed = max(0.0, (now if now is not None else time.time()) - float(config["set_epoch"]))
            return (base + timedelta(seconds=passed)).strftime("%Y-%m-%d %H:%M:%S")
        except (KeyError, ValueError, TypeError, OverflowError):
            return "NO SIGNAL"

    zone = config.get("timezone", "UNSET" if source_is_remote else "SYSTEM")
    if zone == "UNSET" or not zone:
        return "NO SIGNAL"
    try:
        if zone == "SYSTEM":
            return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        return datetime.now(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M:%S")
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return "NO SIGNAL"


def coordinates_text(config: dict) -> str | None:
    if not config.get("show", True):
        return None
    if not config.get("has_coordinates", False):
        return "NO SIGNAL"
    try:
        lat, lon = float(config["lat"]), float(config["lon"])
    except (TypeError, KeyError, ValueError):
        return "NO SIGNAL"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return "NO SIGNAL"
    return f"{abs(lat):.2f}° {'N' if lat>=0 else 'S'}  {abs(lon):.2f}° {'E' if lon>=0 else 'W'}"
