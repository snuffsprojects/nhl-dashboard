# sync.py
import requests
import json
import time
from datetime import datetime

from cache_store import write_cache_atomic
from config import (
    CACHE_FILE,
    CACHE_FORMAT_VERSION,
    FAST_POLL_SECONDS,
    HTTP_HEADERS,
    IDLE_POLL_SECONDS,
    MQTT_TOPIC_SCORE,
    PREGAME_FAST_POLL_WINDOW_SECONDS,
    SEASON_ID,
    TEAM_ABBREV,
)
from game_center import process_game_center
from game_states import is_completed, is_scheduled, should_fast_poll
from mqtt_publisher import publish_mqtt
from time_utils import get_countdown_string, get_seconds_until_game

def run_sync():
    print("🚀 Initializing Self-Correcting Season Selection Engine...")
    schedule_url = f"https://api-web.nhle.com/v1/club-schedule-season/{TEAM_ABBREV}/{SEASON_ID}"

    # Force an immediate boot broadcast to establish initial state
    publish_mqtt(MQTT_TOPIC_SCORE, {"status": "STARTUP", "score_string": "Connecting..."})

    while True:
        try:
            print(f"\n--- 🔍 LIFECYCLE START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
            response = requests.get(schedule_url, headers=HTTP_HEADERS, timeout=5)

            if response.status_code != 200:
                print(f"❌ [API WARN] Schedule endpoint failed: {response.status_code}")
                time.sleep(30)
                continue

            schedule_data = response.json()
            all_games = schedule_data.get("games", [])

            # 💡 SELF-CORRECTING SEASON ENGINE: Automatically filter down based on layout availability
            playoff_slots = [g for g in all_games if g.get("gameType") == 3]
            regular_slots = [g for g in all_games if g.get("gameType") == 2]

            # MQTT follows the playoffs once they exist, including after the final
            # game. The webpage cache retains both competitions independently.
            is_playoff_active = len(playoff_slots) > 0

            if is_playoff_active:
                raw_active_slots = playoff_slots
                print(f"📊 Mode: Playoff Matrix. Tracking {len(playoff_slots)} posts.")
            else:
                raw_active_slots = regular_slots
                print(f"📊 Mode: Regular Season Matrix. Tracking {len(regular_slots)} posts.")

            web_slots = sorted(
                regular_slots + playoff_slots,
                key=lambda game: game.get("startTimeUTC", ""),
            )
            total_slots = len(web_slots)
            has_live_game = any(should_fast_poll(g.get("gameState")) for g in raw_active_slots)

            if has_live_game:
                print("🚨 LIVE GAME DETECTED. Throttling historical updates to save bandwidth!")

            compiled_payload_list = []
            try:
                with open(CACHE_FILE, "r") as f:
                    existing_cache_data = json.load(f)
                stored_season_id = existing_cache_data.get("season_id")
                if stored_season_id and stored_season_id != SEASON_ID:
                    archive_file = str(CACHE_FILE).replace(f"{TEAM_ABBREV.lower()}_cache.json", f"{TEAM_ABBREV.lower()}_history_{stored_season_id}.json")
                    write_cache_atomic(existing_cache_data, archive_file)
                    print(f"📚 Archived completed season {stored_season_id} to {archive_file}.")
                    existing_cache_data = {"games": []}
                existing_cache = existing_cache_data.get("games", [])
                if existing_cache_data.get("cache_format_version") == CACHE_FORMAT_VERSION:
                    cache_map = {g["id"]: g for g in existing_cache if "match_metrics" in g}
                else:
                    print("🔄 Timeline cache format changed. Rebuilding completed-game details once.")
                    cache_map = {}
            except Exception:
                cache_map = {}

            # Find the next upcoming game on the tracker
            next_game = None
            for g in raw_active_slots:
                if is_scheduled(g.get("gameState")):
                    next_game = g
                    break

            # If all matches are complete, retain the latest final for reference.
            last_completed_game = None
            completed_games = [g for g in raw_active_slots if is_completed(g.get("gameState"))]
            if completed_games:
                last_completed_game = completed_games[-1]

            for idx, game in enumerate(web_slots):
                state = game.get("gameState", "FUT")
                game_id = game.get("id")
                start_utc = game.get("startTimeUTC", "UNKNOWN")

                game_info = {
                    "id": game_id,
                    "startTimeUTC": start_utc,
                    "homeTeam": game.get("homeTeam", {}),
                    "awayTeam": game.get("awayTeam", {}),
                    "gameState": state,
                    "gameType": game.get("gameType"),
                    "gameDate": game.get("gameDate"),
                    "gameOutcome": game.get("gameOutcome", {}),
                    "periodDescriptor": game.get("periodDescriptor", {}),
                }

                if should_fast_poll(state):
                    print(f"  -> [{idx+1}/{total_slots}] Syncing ACTIVE Game ID: {game_id} ({state})")
                    time.sleep(0.5)
                    game_info["match_metrics"] = process_game_center(game_id)
                elif is_completed(state):
                    cached_game = cache_map.get(game_id, {})
                    cached_metrics = cached_game.get("match_metrics", {})

                    # Completed games no longer change during normal operation, so keep
                    # their detailed API response. If an earlier request failed and left
                    # no stats, retry it on the next cycle instead of caching the failure.
                    if cached_metrics.get("stats"):
                        game_info["match_metrics"] = cached_metrics
                    else:
                        print(f"  -> [{idx+1}/{total_slots}] Caching Finished Game ID: {game_id} ({state})")
                        time.sleep(0.5)
                        game_info["match_metrics"] = process_game_center(game_id)
                elif is_scheduled(state):
                    game_info["match_metrics"] = {"stats": [], "timeline": [], "roster": []}
                else:
                    # Preserve the last good details for postponed, cancelled,
                    # and unknown feed states instead of silently erasing them.
                    game_info["match_metrics"] = cache_map.get(game_id, {}).get(
                        "match_metrics", {"stats": [], "timeline": [], "roster": []}
                    )

                compiled_payload_list.append(game_info)

            # 💡 RESOLVING THE FINAL SCORE FREEZER: Handle the post-game/off-season screen state
            if not has_live_game:
                if next_game:
                    # An upcoming game exists -> Send full countdown parameters
                    n_home = next_game.get("homeTeam", {}).get("abbrev", "HOME")
                    n_away = next_game.get("awayTeam", {}).get("abbrev", "AWAY")
                    countdown_clock = get_countdown_string(next_game.get("startTimeUTC", ""))

                    # 🔍 NEW: Find the most recently completed game to extract the historical score
                    prev_score_str = "Prev: No Data"
                    completed_games = [g for g in raw_active_slots if is_completed(g.get("gameState"))]
                    if completed_games:
                        last_g = completed_games[-1]
                        lg_home = last_g.get("homeTeam", {})
                        lg_away = last_g.get("awayTeam", {})
                        prev_score_str = f"Last: {lg_away.get('abbrev')} {lg_away.get('score')} - {lg_home.get('abbrev')} {lg_home.get('score')}"

                    final_payload = {
                        "status": "COUNTDOWN",
                        "matchup": f"{n_away} @ {n_home}",
                        "score_string": f"Next: {n_away} @ {n_home}",
                        "prev_game_score": prev_score_str, # 💡 Transmitting the morning-after catchup score line!
                        "countdown": countdown_clock,
                        "period": 0,
                        "time_remaining": "00:00"
                    }
                    publish_mqtt(MQTT_TOPIC_SCORE, final_payload)
                elif last_completed_game:
                    # Absolutely all games finished -> Show absolute season conclusion metrics
                    lc_home = last_completed_game.get("homeTeam", {})
                    lc_away = last_completed_game.get("awayTeam", {})
                    f_score_str = f"{lc_away.get('abbrev')} {lc_away.get('score')} - {lc_home.get('abbrev')} {lc_home.get('score')}"

                    publish_mqtt(MQTT_TOPIC_SCORE, {
                        "status": "OFFSEASON",
                        "matchup": "Season Complete",
                        "score_string": f_score_str,
                        "countdown": "See You Next Season!",
                        "period": 0,
                        "time_remaining": "00:00"
                    })

            # Safely commit structure array to local cache matrix
            cache_data = {
                "cache_format_version": CACHE_FORMAT_VERSION,
                "season_id": SEASON_ID,
                "games": compiled_payload_list,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            write_cache_atomic(cache_data)
            print("💾 Master cache matrix written to disk cleanly.")

            seconds_until_next_game = None
            next_game_state = None
            if next_game:
                seconds_until_next_game = get_seconds_until_game(next_game.get("startTimeUTC", ""))
                next_game_state = next_game.get("gameState")

            should_fast_poll = (
                has_live_game
                or next_game_state == "PRE"
                or (
                    seconds_until_next_game is not None
                    and seconds_until_next_game <= PREGAME_FAST_POLL_WINDOW_SECONDS
                )
            )

            if should_fast_poll:
                print("⏱️ Game window active. Fast cycling engine in 15s...")
                time.sleep(FAST_POLL_SECONDS)
            else:
                sleep_seconds = IDLE_POLL_SECONDS
                if seconds_until_next_game is not None:
                    # Wake at the start of the five-minute pregame window instead of
                    # sleeping past puck drop during a normal ten-minute idle cycle.
                    until_fast_window = seconds_until_next_game - PREGAME_FAST_POLL_WINDOW_SECONDS
                    sleep_seconds = min(IDLE_POLL_SECONDS, max(FAST_POLL_SECONDS, until_fast_window))

                print(f"💤 System idle. Next schedule check in {round(sleep_seconds)}s...")
                time.sleep(sleep_seconds)

        except requests.exceptions.Timeout:
            print("❌ [CRITICAL TIMEOUT] NHL API did not respond within 5s. Shifting frame...")
            time.sleep(20)
        except Exception as e:
            print(f"❌ [UNHANDLED ENGINE CRASH] Stack Trace Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_sync()
