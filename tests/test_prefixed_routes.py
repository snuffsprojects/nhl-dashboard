import unittest
from pathlib import Path
import re


class PrefixedRouteTests(unittest.TestCase):
    def test_no_application_assets_or_requests_are_root_relative(self):
        project = Path(__file__).parents[1]
        candidates = list((project / "templates").glob("*.html")) + list((project / "static").glob("*.js"))
        forbidden = (
            re.compile(r'''(?:href|src|action)=["']/'''),
            re.compile(r'''fetch\s*\(\s*[`"']/'''),
        )
        for source in candidates:
            text = source.read_text(encoding="utf-8")
            for pattern in forbidden:
                self.assertIsNone(pattern.search(text), f"Root-relative application URL in {source.name}")

    def test_dashboard_requests_use_flask_generated_urls(self):
        template = (Path(__file__).parents[1] / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("fetch(`/game_boxscore/", template)
        self.assertNotIn("fetch(`/player_stats/", template)
        self.assertIn("url_for('game_boxscore'", template)
        self.assertIn("url_for('player_stats'", template)

    def test_player_season_tabs_use_flask_generated_urls(self):
        template = (Path(__file__).parents[1] / "templates" / "players.html").read_text(encoding="utf-8")
        self.assertNotIn('href="/players?', template)
        self.assertNotIn("fetch(`/player_stats/", template)
        self.assertIn("url_for('players', season=season.id)", template)
        self.assertIn("url_for('player_stats'", template)

    def test_stats_back_link_uses_flask_generated_url(self):
        template = (Path(__file__).parents[1] / "templates" / "stats.html").read_text(encoding="utf-8")
        self.assertNotIn('href="/"', template)
        self.assertIn("url_for('index')", template)

    def test_season_labels_are_configuration_driven(self):
        templates = Path(__file__).parents[1] / "templates"
        for name in ("index.html", "players.html", "stats.html"):
            text = (templates / name).read_text(encoding="utf-8")
            for hard_coded in ("2025–26", "2026–27", "2027 Stanley"):
                self.assertNotIn(hard_coded, text, f"Hard-coded season label in {name}")


if __name__ == "__main__":
    unittest.main()
