import importlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


class ConfigurationTests(unittest.TestCase):
    def test_team_selection_changes_namespaces(self):
        with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {
            "NHL_TEAM": "SEA", "NHL_TEAM_NAME": "Seattle Kraken",
            "NHL_TEAM_SHORT_NAME": "Kraken", "NHL_TEAM_LOCATION": "Seattle",
            "NHL_DATA_DIR": data_dir,
        }, clear=False):
            import config
            configured = importlib.reload(config)
            self.assertEqual(configured.TEAM_ABBREV, "SEA")
            self.assertEqual(configured.public_config()["teamName"], "Seattle Kraken")
            self.assertEqual(configured.public_config()["tertiaryColor"], "#e9072b")
            self.assertEqual(configured.HISTORICAL_SEASON_ID, "20252026")
            self.assertEqual(configured.public_config()["historicalSeasonId"], "20252026")
            self.assertTrue(configured.CACHE_FILE.endswith("sea_cache.json"))
            self.assertEqual(configured.MQTT_TOPIC_SCORE, "nhl/sea/live_score")

    def test_invalid_team_abbreviation_is_rejected(self):
        with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {
            "NHL_TEAM": "SEA/../bad", "NHL_DATA_DIR": data_dir,
        }, clear=False):
            sys.modules.pop("config", None)
            with self.assertRaisesRegex(ValueError, "club abbreviation"):
                importlib.import_module("config")
            sys.modules.pop("config", None)

    def test_non_consecutive_season_is_rejected(self):
        with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {
            "NHL_SEASON": "20262028", "NHL_DATA_DIR": data_dir,
        }, clear=False):
            sys.modules.pop("config", None)
            with self.assertRaisesRegex(ValueError, "consecutive years"):
                importlib.import_module("config")
            sys.modules.pop("config", None)


if __name__ == "__main__":
    unittest.main()
