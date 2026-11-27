"""Fetch and persist the selected team's previous season."""

import os
import time
from datetime import datetime

import requests

from cache_store import load_cache, write_cache_atomic
from config import (
    HISTORICAL_CACHE_FILE,
    HISTORICAL_CACHE_MAX_AGE_SECONDS,
    HISTORICAL_SEASON_ID,
    HTTP_HEADERS,
    TEAM_ABBREV,
)


def load_historical_cache(force_refresh=False):
    """Return last season, refreshing the local snapshot at most once per day."""
    cache_exists = os.path.exists(HISTORICAL_CACHE_FILE)
    cache_is_fresh = cache_exists and (
        time.time() - os.path.getmtime(HISTORICAL_CACHE_FILE)
        < HISTORICAL_CACHE_MAX_AGE_SECONDS
    )

    if cache_is_fresh and not force_refresh:
        return load_cache(HISTORICAL_CACHE_FILE)

    stale_cache = load_cache(HISTORICAL_CACHE_FILE)
    url = (
        "https://api-web.nhle.com/v1/club-schedule-season/"
        f"{TEAM_ABBREV}/{HISTORICAL_SEASON_ID}"
    )

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        games = [
            game for game in response.json().get("games", [])
            if game.get("gameType") in (2, 3)
        ]

        # Retain any detailed game data previously fetched on demand.
        existing_metrics = {
            game.get("id"): game.get("match_metrics")
            for game in stale_cache.get("games", [])
            if game.get("match_metrics")
        }
        existing_highlights = {
            game.get("id"): {
                "highlight_video_id": game.get("highlight_video_id"),
                "highlight_title": game.get("highlight_title"),
            }
            for game in stale_cache.get("games", [])
            if game.get("highlight_video_id")
        }
        for game in games:
            if game.get("id") in existing_metrics:
                game["match_metrics"] = existing_metrics[game["id"]]
            if game.get("id") in existing_highlights:
                game.update(existing_highlights[game["id"]])

        cache_data = {
            "season_id": HISTORICAL_SEASON_ID,
            "games": games,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if stale_cache.get("highlight_sync"):
            cache_data["highlight_sync"] = stale_cache["highlight_sync"]
        write_cache_atomic(cache_data, HISTORICAL_CACHE_FILE)
        return cache_data
    except Exception as error:
        print(f"Historical schedule refresh failed: {error}")
        return stale_cache


def save_historical_game_metrics(game_id, metrics):
    """Add an on-demand box score to the historical cache."""
    cache_data = load_cache(HISTORICAL_CACHE_FILE)
    for game in cache_data.get("games", []):
        if str(game.get("id")) == str(game_id):
            game["match_metrics"] = metrics
            write_cache_atomic(cache_data, HISTORICAL_CACHE_FILE)
            break
