import unittest

from season_ids import previous_season_id, validate_season_id


class SeasonIdTests(unittest.TestCase):
    def test_previous_season_is_derived(self):
        self.assertEqual(previous_season_id("20262027"), "20252026")

    def test_season_must_span_consecutive_years(self):
        with self.assertRaisesRegex(ValueError, "consecutive years"):
            validate_season_id("20262028")


if __name__ == "__main__":
    unittest.main()
