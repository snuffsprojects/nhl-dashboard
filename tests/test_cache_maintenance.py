import tempfile
import unittest
from pathlib import Path

from cache_maintenance import purge_cache_files


class CacheMaintenanceTests(unittest.TestCase):
    def test_purge_removes_only_regenerable_cache_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            removable = {
                "phi_cache.json", "phi_history_20252026.json",
                "standings_cache.json", "playoff_bracket_2026.json",
                "phi_history_20252026.json.highlights.lock", ".nhl_cache.test.tmp",
            }
            protected = {"settings.json", "session.key", "notes.json"}
            for name in removable | protected:
                (data_dir / name).write_text("test", encoding="utf-8")
            (data_dir / ".cache-reset-requested").write_text("requested", encoding="ascii")

            deleted = set(purge_cache_files(data_dir, require_request=True))

            self.assertEqual(deleted, removable)
            self.assertFalse((data_dir / ".cache-reset-requested").exists())
            self.assertEqual({path.name for path in data_dir.iterdir()}, protected)

    def test_purge_requires_marker_when_requested(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            cache = data_dir / "vgk_cache.json"
            cache.write_text("{}", encoding="utf-8")
            self.assertEqual(purge_cache_files(data_dir, require_request=True), [])
            self.assertTrue(cache.exists())


if __name__ == "__main__":
    unittest.main()
