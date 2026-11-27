"""Safe JSON cache persistence for the synchronizer and web application."""

import json
import os
import stat
import tempfile

from config import CACHE_FILE


def load_cache(cache_file=CACHE_FILE):
    if not os.path.exists(cache_file):
        return {"games": [], "last_updated": "Never"}

    try:
        with open(cache_file, "r", encoding="utf-8") as cache_handle:
            return json.load(cache_handle)
    except Exception as error:
        print(f"Error reading cache file descriptor: {error}")
        return {"games": [], "last_updated": "Corrupted"}


def write_cache_atomic(cache_data, cache_file=CACHE_FILE):
    """Write a complete cache beside the live file, then atomically replace it."""
    cache_path = os.path.abspath(cache_file)
    cache_dir = os.path.dirname(cache_path)
    temp_path = None

    try:
        try:
            cache_mode = stat.S_IMODE(os.stat(cache_path).st_mode)
        except FileNotFoundError:
            cache_mode = 0o644

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cache_dir,
            prefix=".nhl_cache.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(cache_data, temp_file, indent=4)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.chmod(temp_path, cache_mode)
        os.replace(temp_path, cache_path)
        temp_path = None

        directory_fd = os.open(cache_dir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
