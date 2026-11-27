import unittest

from team_palettes import TEAM_PALETTES, palette_for


class TeamPaletteTests(unittest.TestCase):
    def test_current_league_has_three_colour_palettes(self):
        self.assertEqual(len(TEAM_PALETTES), 32)
        for abbreviation, palette in TEAM_PALETTES.items():
            self.assertRegex(abbreviation, r"^[A-Z]{3}$")
            self.assertEqual(len(palette), 3)
            for colour in palette:
                self.assertRegex(colour, r"^#[0-9a-f]{6}$")

    def test_unknown_club_uses_neutral_fallback(self):
        self.assertEqual(palette_for("NEW"), ("#748cab", "#f0b35a", "#dce4ef"))


if __name__ == "__main__":
    unittest.main()
