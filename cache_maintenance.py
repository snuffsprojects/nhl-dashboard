"""Constrained cache purge support for team changes and troubleshooting."""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(os.environ.get("NHL_DATA_DIR", Path(__file__).resolve().parent / "data"))
RESET_REQUEST = DATA_DIR / ".cache-reset-requested"
CACHE_PATTERNS = (
    "*_cache.json",
    "*_history_*.json",
    "standings_cache.json",
    "playoff_bracket_*.json",
    "*.highlights.lock",
    ".nhl_cache.*.tmp",
)


def request_cache_purge():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESET_REQUEST.write_text(datetime.now(timezone.utc).isoformat(), encoding="ascii")


def purge_cache_files(data_dir=DATA_DIR, require_request=False):
    data_dir = Path(data_dir)
    request_file = data_dir / RESET_REQUEST.name
    if require_request and not request_file.is_file():
        return []

    targets = set()
    for pattern in CACHE_PATTERNS:
        targets.update(path for path in data_dir.glob(pattern) if path.is_file() or path.is_symlink())

    removed = []
    for target in sorted(targets):
        target.unlink(missing_ok=True)
        removed.append(target.name)
    request_file.unlink(missing_ok=True)
    return removed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove regenerable NHL Dashboard caches")
    parser.add_argument("--if-requested", action="store_true")
    arguments = parser.parse_args()
    deleted = purge_cache_files(require_request=arguments.if_requested)
    if deleted:
        print(f"Removed {len(deleted)} NHL Dashboard cache files: {', '.join(deleted)}")
