import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import settings_store


VALID_SETTINGS = {
    "NHL_TEAM": "SEA",
    "NHL_TEAM_NAME": "Seattle Kraken",
    "NHL_TEAM_SHORT_NAME": "Kraken",
    "NHL_TEAM_LOCATION": "Seattle",
    "NHL_TEAM_MARK": "S",
    "NHL_SITE_NAME": "Kraken Watch",
    "NHL_SEASON": "20262027",
    "NHL_TIMEZONE": "America/Los_Angeles",
    "NHL_PRIMARY_COLOR": "#001628",
    "NHL_ACCENT_COLOR": "#99d9d9",
    "NHL_TERTIARY_COLOR": "#e9072b",
    "NHL_YOUTUBE_PLAYLIST_ID": "",
    "NHL_MQTT_TOPIC_PREFIX": "nhl/sea",
}


class SettingsStoreTests(unittest.TestCase):
    def test_config_and_password_are_preserved_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            with patch.multiple(
                settings_store,
                DATA_DIR=data_dir,
                SETTINGS_FILE=data_dir / "settings.json",
                SESSION_KEY_FILE=data_dir / "session.key",
            ):
                cleaned = settings_store.validate_config(VALID_SETTINGS)
                settings_store.set_admin_password_hash("test-password-hash")
                settings_store.update_config(cleaned)
                stored = settings_store.load_settings()

                self.assertEqual(stored["admin_password_hash"], "test-password-hash")
                self.assertEqual(stored["config"]["NHL_TEAM"], "SEA")
                self.assertEqual((data_dir / "settings.json").stat().st_mode & 0o777, 0o600)

    def test_invalid_timezone_is_rejected(self):
        values = dict(VALID_SETTINGS, NHL_TIMEZONE="Moon/Sea_of_Tranquility")
        with self.assertRaisesRegex(ValueError, "valid IANA timezone"):
            settings_store.validate_config(values)

    def test_session_key_is_stable_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            with patch.multiple(
                settings_store,
                DATA_DIR=data_dir,
                SETTINGS_FILE=data_dir / "settings.json",
                SESSION_KEY_FILE=data_dir / "session.key",
            ):
                first = settings_store.load_or_create_session_key()
                second = settings_store.load_or_create_session_key()
                self.assertEqual(first, second)
                self.assertEqual((data_dir / "session.key").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
