"""UTC schedule and polling-time helpers."""

from datetime import datetime, timezone


def get_countdown_string(utc_start_str):
    try:
        event_time = datetime.strptime(utc_start_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        delta = event_time - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "Puck dropping..."
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, _ = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours}h"
        return f"{hours}h {minutes}m"
    except Exception:
        return "TBD"


def get_seconds_until_game(utc_start_str):
    try:
        event_time = datetime.strptime(utc_start_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (event_time - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return None
