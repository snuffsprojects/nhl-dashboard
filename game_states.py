"""Classification helpers for NHL web API game-state codes."""

SCHEDULED_STATES = frozenset({"FUT", "PRE"})
LIVE_STATES = frozenset({"LIVE", "CRIT"})
COMPLETED_STATES = frozenset({"FINAL", "OFF"})
INTERRUPTED_STATES = frozenset({"SUSP"})
POSTPONED_STATES = frozenset({"PPD"})
CANCELLED_STATES = frozenset({"CNCL"})


def normalise_game_state(state):
    return str(state or "UNKNOWN").strip().upper() or "UNKNOWN"


def is_scheduled(state):
    return normalise_game_state(state) in SCHEDULED_STATES


def is_live(state):
    return normalise_game_state(state) in LIVE_STATES


def is_completed(state):
    return normalise_game_state(state) in COMPLETED_STATES


def should_fast_poll(state):
    return normalise_game_state(state) in LIVE_STATES | INTERRUPTED_STATES


def state_category(state):
    state = normalise_game_state(state)
    if state in SCHEDULED_STATES:
        return "scheduled"
    if state in LIVE_STATES:
        return "live"
    if state in COMPLETED_STATES:
        return "completed"
    if state in INTERRUPTED_STATES:
        return "suspended"
    if state in POSTPONED_STATES:
        return "postponed"
    if state in CANCELLED_STATES:
        return "cancelled"
    return "unknown"


def state_label(state):
    state = normalise_game_state(state)
    return {
        "FUT": "Upcoming",
        "PRE": "Pregame",
        "LIVE": "LIVE NOW",
        "CRIT": "LIVE NOW",
        "FINAL": "Final",
        "OFF": "Final",
        "SUSP": "Suspended",
        "PPD": "Postponed",
        "CNCL": "Cancelled",
    }.get(state, f"Status unavailable ({state})")
