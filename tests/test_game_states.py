import unittest

from game_states import (
    is_completed,
    is_live,
    is_scheduled,
    should_fast_poll,
    state_category,
    state_label,
)


class GameStateTests(unittest.TestCase):
    def test_known_lifecycle_states_are_classified(self):
        for state in ("FUT", "PRE"):
            self.assertTrue(is_scheduled(state))
        for state in ("LIVE", "CRIT"):
            self.assertTrue(is_live(state))
            self.assertTrue(should_fast_poll(state))
        for state in ("FINAL", "OFF"):
            self.assertTrue(is_completed(state))

    def test_exception_states_have_explicit_labels(self):
        self.assertEqual(state_label("SUSP"), "Suspended")
        self.assertEqual(state_label("PPD"), "Postponed")
        self.assertEqual(state_label("CNCL"), "Cancelled")
        self.assertTrue(should_fast_poll("SUSP"))

    def test_unknown_state_is_never_mislabelled_as_upcoming(self):
        self.assertEqual(state_category("NEW_CODE"), "unknown")
        self.assertEqual(state_label("NEW_CODE"), "Status unavailable (NEW_CODE)")


if __name__ == "__main__":
    unittest.main()
