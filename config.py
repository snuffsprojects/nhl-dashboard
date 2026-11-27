"""Environment-backed configuration for the reusable NHL dashboard."""

import os
import re
import json
from pathlib import Path
from team_palettes import palette_for
from season_ids import previous_season_id, validate_season_id


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("NHL_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
try:
    with (DATA_DIR / "settings.json").open("r", encoding="utf-8") as settings_source:
        _PERSISTED = json.load(settings_source).get("config", {})
except (OSError, json.JSONDecodeError, AttributeError):
    _PERSISTED = {}


def _setting(name, default):
    return str(_PERSISTED.get(name, os.environ.get(name, default))).strip()

TEAM_ABBREV = _setting("NHL_TEAM", "VGK").upper()
if not re.fullmatch(r"[A-Z]{2,4}", TEAM_ABBREV):
    raise ValueError("NHL_TEAM must be a 2-4 letter NHL club abbreviation")
TEAM_NAME = _setting("NHL_TEAM_NAME", TEAM_ABBREV)
TEAM_SHORT_NAME = _setting("NHL_TEAM_SHORT_NAME", TEAM_NAME)
TEAM_LOCATION = _setting("NHL_TEAM_LOCATION", TEAM_ABBREV)
TEAM_MARK = _setting("NHL_TEAM_MARK", TEAM_ABBREV[:1]) or TEAM_ABBREV[:1]
_DEFAULT_PALETTE = palette_for(TEAM_ABBREV)
TEAM_PRIMARY_COLOR = _setting("NHL_PRIMARY_COLOR", _DEFAULT_PALETTE[0])
TEAM_ACCENT_COLOR = _setting("NHL_ACCENT_COLOR", _DEFAULT_PALETTE[1])
TEAM_TERTIARY_COLOR = _setting("NHL_TERTIARY_COLOR", _DEFAULT_PALETTE[2])
if not re.fullmatch(r"#[0-9a-fA-F]{6}", TEAM_PRIMARY_COLOR):
    raise ValueError("NHL_PRIMARY_COLOR must be a six-digit hex colour")
if not re.fullmatch(r"#[0-9a-fA-F]{6}", TEAM_ACCENT_COLOR):
    raise ValueError("NHL_ACCENT_COLOR must be a six-digit hex colour")
if not re.fullmatch(r"#[0-9a-fA-F]{6}", TEAM_TERTIARY_COLOR):
    raise ValueError("NHL_TERTIARY_COLOR must be a six-digit hex colour")
SITE_NAME = _setting("NHL_SITE_NAME", f"{TEAM_ABBREV} Watch")
BACK_URL = os.environ.get("NHL_BACK_URL", "/").strip() or "/"
BACK_LABEL = os.environ.get(
    "NHL_BACK_LABEL", "Dashboard 2" if "dashboard2" in BACK_URL.lower() else "Home"
).strip() or "Home"
DISPLAY_TIMEZONE = _setting("NHL_TIMEZONE", "Europe/London")

SEASON_ID = validate_season_id(_setting("NHL_SEASON", "20262027"))
HISTORICAL_SEASON_ID = previous_season_id(SEASON_ID)
CACHE_FORMAT_VERSION = 4
CACHE_FILE = str(DATA_DIR / f"{TEAM_ABBREV.lower()}_cache.json")
HISTORICAL_CACHE_FILE = str(DATA_DIR / f"{TEAM_ABBREV.lower()}_history_{HISTORICAL_SEASON_ID}.json")
HISTORICAL_CACHE_MAX_AGE_SECONDS = 86400
YOUTUBE_HIGHLIGHTS_PLAYLIST_ID = _setting("NHL_YOUTUBE_PLAYLIST_ID", "")

MQTT_ENABLED = os.environ.get("NHL_MQTT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
MQTT_BROKER = os.environ.get("NHL_MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("NHL_MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = _setting("NHL_MQTT_TOPIC_PREFIX", f"nhl/{TEAM_ABBREV.lower()}").strip("/")
MQTT_TOPIC_SCORE = f"{MQTT_TOPIC_PREFIX}/live_score"
MQTT_TOPIC_GOAL = f"{MQTT_TOPIC_PREFIX}/goal_alert"

HTTP_HEADERS = {"Connection": "close", "User-Agent": "NHL-Dashboard/1.0"}
FAST_POLL_SECONDS = int(os.environ.get("NHL_FAST_POLL_SECONDS", "15"))
IDLE_POLL_SECONDS = int(os.environ.get("NHL_IDLE_POLL_SECONDS", "600"))
PREGAME_FAST_POLL_WINDOW_SECONDS = int(os.environ.get("NHL_PREGAME_WINDOW_SECONDS", "300"))


def public_config():
    return {
        "teamAbbrev": TEAM_ABBREV,
        "teamName": TEAM_NAME,
        "teamShortName": TEAM_SHORT_NAME,
        "teamLocation": TEAM_LOCATION,
        "teamMark": TEAM_MARK,
        "siteName": SITE_NAME,
        "primaryColor": TEAM_PRIMARY_COLOR,
        "accentColor": TEAM_ACCENT_COLOR,
        "tertiaryColor": TEAM_TERTIARY_COLOR,
        "backUrl": BACK_URL,
        "backLabel": BACK_LABEL,
        "seasonId": SEASON_ID,
        "historicalSeasonId": HISTORICAL_SEASON_ID,
    }
