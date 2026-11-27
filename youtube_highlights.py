"""Match playlist videos to cached games for the configured team."""

import fcntl
import os
import re
from datetime import datetime, timezone

import requests

from cache_store import load_cache, write_cache_atomic
from config import HISTORICAL_CACHE_FILE, TEAM_ABBREV, TEAM_NAME, TEAM_SHORT_NAME, YOUTUBE_HIGHLIGHTS_PLAYLIST_ID

YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


def _normalise(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _team_terms(team):
    common = team.get("commonName", {}).get("default", "")
    place = team.get("placeName", {}).get("default", "")
    terms = {common, place, f"{place} {common}"}
    if team.get("abbrev") == TEAM_ABBREV:
        terms.update((TEAM_ABBREV, TEAM_NAME, TEAM_SHORT_NAME))
    return {_normalise(term) for term in terms if len(_normalise(term)) >= 4}


def _fetch_playlist(api_key):
    videos = []
    page_token = None

    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": YOUTUBE_HIGHLIGHTS_PLAYLIST_ID,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(YOUTUBE_PLAYLIST_ITEMS_URL, params=params, timeout=15)
        if not response.ok:
            try:
                api_error = response.json().get("error", {}).get("message")
            except ValueError:
                api_error = None
            raise RuntimeError(
                f"YouTube playlist request failed ({response.status_code}): "
                f"{api_error or 'unknown API error'}"
            )
        payload = response.json()

        for item in payload.get("items", []):
            snippet = item.get("snippet", {})
            details = item.get("contentDetails", {})
            video_id = details.get("videoId") or snippet.get("resourceId", {}).get("videoId")
            published_at = details.get("videoPublishedAt") or snippet.get("publishedAt")
            if video_id and published_at:
                videos.append({
                    "id": video_id,
                    "title": snippet.get("title", ""),
                    "published_at": published_at,
                })

        page_token = payload.get("nextPageToken")
        if not page_token:
            return videos


def _match_video(game, videos):
    away_terms = _team_terms(game.get("awayTeam", {}))
    home_terms = _team_terms(game.get("homeTeam", {}))
    try:
        start = datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None

    candidates = []
    for video in videos:
        title = _normalise(video["title"])
        if not any(term in title for term in away_terms):
            continue
        if not any(term in title for term in home_terms):
            continue

        try:
            published = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
        except ValueError:
            continue

        hours_after_start = (published - start).total_seconds() / 3600
        if -6 <= hours_after_start <= 48:
            candidates.append((abs(hours_after_start - 3), video))

    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def sync_historical_highlights():
    """Populate missing historical highlight IDs once, safely across workers."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key or not YOUTUBE_HIGHLIGHTS_PLAYLIST_ID:
        return {"matched": 0, "error": "YouTube highlights are not configured"}

    lock_path = f"{HISTORICAL_CACHE_FILE}.highlights.lock"
    with open(lock_path, "w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        cache_data = load_cache(HISTORICAL_CACHE_FILE)
        previous_sync = cache_data.get("highlight_sync", {})
        if previous_sync.get("playlist_id") == YOUTUBE_HIGHLIGHTS_PLAYLIST_ID:
            return previous_sync

        videos = _fetch_playlist(api_key)
        matched = 0
        for game in cache_data.get("games", []):
            video = _match_video(game, videos)
            if video:
                game["highlight_video_id"] = video["id"]
                game["highlight_title"] = video["title"]
                matched += 1

        result = {
            "playlist_id": YOUTUBE_HIGHLIGHTS_PLAYLIST_ID,
            "matched": matched,
            "games": len(cache_data.get("games", [])),
            "videos_scanned": len(videos),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        cache_data["highlight_sync"] = result
        write_cache_atomic(cache_data, HISTORICAL_CACHE_FILE)
        return result
