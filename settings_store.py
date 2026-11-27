"""Atomic persisted configuration and administrator state."""

import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from season_ids import previous_season_id


DATA_DIR = Path(os.environ.get("NHL_DATA_DIR", Path(__file__).resolve().parent / "data"))
SETTINGS_FILE = DATA_DIR / "settings.json"
SESSION_KEY_FILE = DATA_DIR / "session.key"

CONFIG_KEYS = (
    "NHL_TEAM", "NHL_TEAM_NAME", "NHL_TEAM_SHORT_NAME", "NHL_TEAM_LOCATION",
    "NHL_TEAM_MARK", "NHL_SITE_NAME", "NHL_SEASON",
    "NHL_TIMEZONE", "NHL_PRIMARY_COLOR", "NHL_ACCENT_COLOR", "NHL_TERTIARY_COLOR",
    "NHL_YOUTUBE_PLAYLIST_ID", "NHL_MQTT_TOPIC_PREFIX",
)


def load_settings():
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_settings(value):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".settings.", suffix=".tmp", dir=DATA_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(value, target, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, SETTINGS_FILE)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def update_config(config):
    settings = load_settings()
    settings["config"] = {key: config[key] for key in CONFIG_KEYS if key in config}
    write_settings(settings)


def set_admin_password_hash(password_hash):
    settings = load_settings()
    settings["admin_password_hash"] = password_hash
    write_settings(settings)


def get_admin_password_hash():
    return str(load_settings().get("admin_password_hash", ""))


def load_or_create_session_key():
    try:
        return SESSION_KEY_FILE.read_text(encoding="ascii").strip()
    except OSError:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        descriptor, temporary = tempfile.mkstemp(prefix=".session.", dir=DATA_DIR)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as target:
                target.write(key)
                target.flush()
                os.fsync(target.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, SESSION_KEY_FILE)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return key


def validate_config(payload):
    cleaned = {key: str(payload.get(key, "")).strip() for key in CONFIG_KEYS}
    cleaned["NHL_TEAM"] = cleaned["NHL_TEAM"].upper()
    if not re.fullmatch(r"[A-Z]{2,4}", cleaned["NHL_TEAM"]):
        raise ValueError("Choose a valid NHL team abbreviation.")
    for key in ("NHL_TEAM_NAME", "NHL_TEAM_SHORT_NAME", "NHL_TEAM_LOCATION", "NHL_TEAM_MARK", "NHL_SITE_NAME"):
        if not cleaned[key] or len(cleaned[key]) > 80:
            raise ValueError("Team names, mark and site name are required and must be under 80 characters.")
    previous_season_id(cleaned["NHL_SEASON"])
    for key in ("NHL_PRIMARY_COLOR", "NHL_ACCENT_COLOR", "NHL_TERTIARY_COLOR"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", cleaned[key]):
            raise ValueError("Colours must use six-digit hex values.")
        cleaned[key] = cleaned[key].lower()
    try:
        ZoneInfo(cleaned["NHL_TIMEZONE"])
    except ZoneInfoNotFoundError as error:
        raise ValueError("Enter a valid IANA timezone such as Europe/London.") from error
    if cleaned["NHL_MQTT_TOPIC_PREFIX"]:
        if not re.fullmatch(r"[A-Za-z0-9_./-]{1,120}", cleaned["NHL_MQTT_TOPIC_PREFIX"]):
            raise ValueError("The MQTT topic prefix contains unsupported characters.")
        cleaned["NHL_MQTT_TOPIC_PREFIX"] = cleaned["NHL_MQTT_TOPIC_PREFIX"].strip("/")
    return cleaned
