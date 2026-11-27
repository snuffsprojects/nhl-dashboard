import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class StatsTests(unittest.TestCase):
    def test_selected_team_can_be_changed(self):
        with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {
            "NHL_TEAM": "SEA", "NHL_DATA_DIR": data_dir,
        }, clear=False):
            import config
            import stats_engine
            importlib.reload(config)
            engine = importlib.reload(stats_engine)
            stats = engine.build_season_stats([{
                "id": 1, "gameState": "OFF", "gameType": 2,
                "gameDate": "2026-10-01",
                "homeTeam": {"abbrev": "SEA", "score": 4},
                "awayTeam": {"abbrev": "VAN", "score": 2},
                "gameOutcome": {"lastPeriodType": "REG"},
            }])
            self.assertEqual(stats["overall"]["wins"], 1)
            self.assertEqual(stats["overall"]["goals_for"], 4)


if __name__ == "__main__":
    unittest.main()
