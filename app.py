# app.py
from flask import Flask, render_template, jsonify, request, redirect, session, url_for
from datetime import datetime, timedelta, timezone
import glob
import json
import os
import time
import secrets
from functools import wraps
import requests
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from cache_store import load_cache, write_cache_atomic
from cache_maintenance import request_cache_purge
from config import (
    BACK_URL, DATA_DIR, DISPLAY_TIMEZONE, HISTORICAL_SEASON_ID, SEASON_ID,
    SITE_NAME, TEAM_ABBREV, TEAM_ACCENT_COLOR, TEAM_LOCATION, TEAM_MARK,
    TEAM_NAME, TEAM_PRIMARY_COLOR, TEAM_SHORT_NAME, TEAM_TERTIARY_COLOR,
    YOUTUBE_HIGHLIGHTS_PLAYLIST_ID,
    MQTT_TOPIC_PREFIX, public_config,
)
from game_center import process_game_center
from history_store import load_historical_cache, save_historical_game_metrics
from youtube_highlights import sync_historical_highlights
from stats_engine import build_season_stats
from settings_store import (
    get_admin_password_hash, load_or_create_session_key, set_admin_password_hash,
    update_config, validate_config,
)
from team_palettes import palette_for

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = load_or_create_session_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
LOCAL_TIMEZONE = ZoneInfo(DISPLAY_TIMEZONE)
PLAYER_PROFILE_CACHE_SECONDS = 3600
PLAYER_HISTORY_START_SEASON = HISTORICAL_SEASON_ID
player_profile_cache = {}
STANDINGS_CACHE_SECONDS = 90
STANDINGS_CACHE_FILE = str(DATA_DIR / "standings_cache.json")
standings_cache = {"fetched_at": 0.0, "payload": None}
PLAYOFF_CACHE_SECONDS = 300
playoff_cache = {}


@app.context_processor
def dashboard_branding():
    return {
        "dashboard": public_config(),
        "settings_admin": bool(session.get("nhl_admin")),
        "csrf_token": csrf_token(),
    }


@app.get('/api/config')
def dashboard_config():
    return jsonify(public_config())


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def valid_csrf():
    supplied = request.form.get("csrf_token", "")
    return bool(supplied and secrets.compare_digest(supplied, session.get("csrf_token", "")))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_admin_password_hash():
            return redirect(url_for("settings_setup"))
        if not session.get("nhl_admin"):
            return redirect(url_for("settings_login"))
        return view(*args, **kwargs)
    return wrapped


def _localised(value):
    return value.get("default", "") if isinstance(value, dict) else str(value or "")


def team_options():
    payload = None
    try:
        response = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=8)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        try:
            with open(STANDINGS_CACHE_FILE, "r", encoding="utf-8") as source:
                payload = json.load(source)
        except (OSError, json.JSONDecodeError):
            payload = {"standings": []}
    teams = {}
    for item in payload.get("standings", []):
        abbreviation = _localised(item.get("teamAbbrev")).upper()
        if not abbreviation:
            continue
        full_name = _localised(item.get("teamName"))
        short_name = _localised(item.get("teamCommonName")) or full_name
        location = _localised(item.get("placeName")) or full_name.removesuffix(f" {short_name}")
        teams[abbreviation] = {
            "abbrev": abbreviation, "name": full_name, "shortName": short_name,
            "location": location, "mark": abbreviation[:1],
            "logo": item.get("teamLogoDark") or item.get("teamLogo") or f"https://assets.nhle.com/logos/nhl/svg/{abbreviation}_dark.svg",
            "palette": palette_for(abbreviation),
        }
    teams.setdefault(TEAM_ABBREV, {
        "abbrev": TEAM_ABBREV, "name": TEAM_NAME, "shortName": TEAM_SHORT_NAME,
        "location": TEAM_LOCATION, "mark": TEAM_MARK,
        "logo": f"https://assets.nhle.com/logos/nhl/svg/{TEAM_ABBREV}_dark.svg",
        "palette": palette_for(TEAM_ABBREV),
    })
    return sorted(teams.values(), key=lambda team: team["name"])


def current_settings():
    return {
        "NHL_TEAM": TEAM_ABBREV, "NHL_TEAM_NAME": TEAM_NAME,
        "NHL_TEAM_SHORT_NAME": TEAM_SHORT_NAME, "NHL_TEAM_LOCATION": TEAM_LOCATION,
        "NHL_TEAM_MARK": TEAM_MARK, "NHL_SITE_NAME": SITE_NAME,
        "NHL_SEASON": SEASON_ID,
        "NHL_TIMEZONE": DISPLAY_TIMEZONE, "NHL_PRIMARY_COLOR": TEAM_PRIMARY_COLOR,
        "NHL_ACCENT_COLOR": TEAM_ACCENT_COLOR,
        "NHL_TERTIARY_COLOR": TEAM_TERTIARY_COLOR,
        "NHL_YOUTUBE_PLAYLIST_ID": YOUTUBE_HIGHLIGHTS_PLAYLIST_ID,
        "NHL_MQTT_TOPIC_PREFIX": MQTT_TOPIC_PREFIX,
    }


@app.route('/settings/setup', methods=['GET', 'POST'])
def settings_setup():
    if get_admin_password_hash():
        return redirect(url_for("settings_login"))
    error = None
    if request.method == 'POST':
        password = request.form.get("password", "")
        if not valid_csrf():
            error = "The form expired. Please try again."
        elif len(password) < 10:
            error = "Use at least 10 characters."
        elif password != request.form.get("confirm_password", ""):
            error = "The passwords do not match."
        else:
            set_admin_password_hash(generate_password_hash(password))
            session.clear()
            session["nhl_admin"] = True
            return redirect(url_for("settings_page"))
    return render_template("settings_setup.html", error=error)


@app.route('/settings/login', methods=['GET', 'POST'])
def settings_login():
    if not get_admin_password_hash():
        return redirect(url_for("settings_setup"))
    error = None
    if request.method == 'POST':
        if not valid_csrf():
            error = "The form expired. Please try again."
        elif check_password_hash(get_admin_password_hash(), request.form.get("password", "")):
            session.clear()
            session["nhl_admin"] = True
            return redirect(url_for("settings_page"))
        else:
            error = "Incorrect password."
    return render_template("settings_login.html", error=error)


@app.post('/settings/logout')
def settings_logout():
    if valid_csrf():
        session.clear()
    return redirect(url_for("index"))


@app.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings_page():
    error = None
    values = current_settings()
    if request.method == 'POST':
        if not valid_csrf():
            error = "The form expired. Please try again."
        else:
            try:
                values = validate_config(request.form)
                update_config(values)
                return redirect(url_for("settings_page", saved="1"))
            except ValueError as validation_error:
                error = str(validation_error)
    return render_template(
        "settings.html", values=values, teams=team_options(), error=error,
        saved=request.args.get("saved") == "1",
        cache_clear=request.args.get("cache_clear") == "1",
        cache_error=request.args.get("cache_error") == "1",
        historical_season=HISTORICAL_SEASON_ID,
    )


@app.post('/settings/cache/clear')
@admin_required
def settings_clear_cache():
    if not valid_csrf():
        return redirect(url_for("settings_page", cache_error="1"))
    request_cache_purge()
    # Replacing settings.json triggers the existing path unit. Its apply service
    # stops the synchronizer before honouring the purge request.
    update_config(current_settings())
    return redirect(url_for("settings_page", cache_clear="1"))

def format_utc_to_london(utc_string):
    try:
        utc_dt = datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        london_dt = utc_dt.astimezone(LOCAL_TIMEZONE)
        return (
            london_dt.strftime("%A, %b %d"),
            london_dt.strftime("%H:%M"),
            london_dt.tzname(),
        )
    except Exception:
        return "Date TBD", "00:00", "UK"

def build_google_calendar_url(utc_string, matchup, location):
    """Build a pre-filled three-hour Google Calendar event in UTC."""
    try:
        start = datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None

    end = start + timedelta(hours=3)
    query = urlencode({
        "action": "TEMPLATE",
        "text": f"{TEAM_NAME}: {matchup}",
        "dates": f"{start.strftime('%Y%m%dT%H%M%SZ')}/{end.strftime('%Y%m%dT%H%M%SZ')}",
        "details": f"{TEAM_NAME} game — {matchup}",
        "location": location,
    })
    return f"https://calendar.google.com/calendar/render?{query}"

@app.route('/')
def index():
    cache_data = load_cache()
    historical_cache = load_historical_cache()
    if not historical_cache.get("highlight_sync"):
        try:
            sync_historical_highlights()
            historical_cache = load_historical_cache()
        except Exception as error:
            app.logger.warning("YouTube highlight sync failed: %s", error)
    regular_games = []
    playoff_games = []

    raw_regular_games = []
    raw_playoff_games = []
    for game in cache_data.get("games", []):
        if game.get("gameType", 2) == 3:
            raw_playoff_games.append(game)
        else:
            raw_regular_games.append(game)

    regular_games = process_games(raw_regular_games)
    playoff_games = process_games(raw_playoff_games)
    playoffs_started = any(game.get("state") in ["PRE", "LIVE", "OFF"] for game in playoff_games)

    historical_regular_games = process_games([
        game for game in historical_cache.get("games", [])
        if game.get("gameType") == 2
    ])
    historical_playoff_games = process_games([
        game for game in historical_cache.get("games", [])
        if game.get("gameType") == 3
    ])

    return render_template(
        "index.html",
        regular_games=regular_games,
        playoff_games=playoff_games,
        historical_regular_games=historical_regular_games,
        historical_playoff_games=historical_playoff_games,
        default_tab="playoffs" if playoffs_started else "regular",
        last_updated=cache_data.get("last_updated", "Never"),
    )


@app.route('/stats')
def stats():
    current_cache = load_cache()
    historical_cache = load_historical_cache()
    current_stats = build_season_stats(current_cache.get("games", []))
    historical_stats = build_season_stats(historical_cache.get("games", []))

    return render_template(
        "stats.html",
        current_stats=current_stats,
        historical_stats=historical_stats,
        default_season="current" if current_stats["overall"]["games"] else "historical",
    )


@app.get('/standings')
def standings_page():
    return render_template('standings.html')


@app.get('/playoffs')
def playoffs_page():
    return render_template('playoffs.html')


@app.get('/api/standings')
def nhl_standings():
    """Serve official NHL standings with a short cache and disk fallback."""
    now = time.time()
    payload = standings_cache.get("payload")
    stale = now - standings_cache.get("fetched_at", 0) >= STANDINGS_CACHE_SECONDS

    if payload is None or stale:
        try:
            response = requests.get("https://api-web.nhle.com/v1/standings/now", timeout=8)
            response.raise_for_status()
            payload = response.json()
            payload["servedFromCache"] = False
            standings_cache.update({"fetched_at": now, "payload": payload})
            with open(STANDINGS_CACHE_FILE, "w", encoding="utf-8") as cache_file:
                json.dump(payload, cache_file, ensure_ascii=False)
        except Exception as error:
            app.logger.warning("NHL standings refresh failed: %s", error)
            if payload is None:
                try:
                    with open(STANDINGS_CACHE_FILE, "r", encoding="utf-8") as cache_file:
                        payload = json.load(cache_file)
                except (OSError, json.JSONDecodeError):
                    payload = {"standings": [], "error": "NHL standings are temporarily unavailable."}
            payload = {**payload, "servedFromCache": True}

    api_response = jsonify(payload)
    api_response.headers["Access-Control-Allow-Origin"] = "*"
    api_response.headers["Cache-Control"] = "no-store"
    return api_response


@app.get('/api/playoffs/<int:year>')
def nhl_playoffs(year):
    """Serve an NHL playoff bracket by Cup year with a disk fallback."""
    current_year = datetime.now(LOCAL_TIMEZONE).year
    if year < 2010 or year > current_year + 1:
        return jsonify({"error": "That playoff season is outside the available range."}), 400
    now = time.time()
    cached = playoff_cache.get(year)
    payload = cached.get("payload") if cached else None
    stale = cached is None or now - cached.get("fetched_at", 0) >= PLAYOFF_CACHE_SECONDS
    cache_file_path = str(DATA_DIR / f"playoff_bracket_{year}.json")
    if payload is None or stale:
        try:
            response = requests.get(f"https://api-web.nhle.com/v1/playoff-bracket/{year}", timeout=8)
            response.raise_for_status()
            payload = response.json()
            payload["servedFromCache"] = False
            playoff_cache[year] = {"fetched_at": now, "payload": payload}
            with open(cache_file_path, "w", encoding="utf-8") as cache_file:
                json.dump(payload, cache_file, ensure_ascii=False)
        except Exception as error:
            app.logger.warning("NHL playoff bracket refresh failed for %s: %s", year, error)
            if payload is None:
                try:
                    with open(cache_file_path, "r", encoding="utf-8") as cache_file:
                        payload = json.load(cache_file)
                except (OSError, json.JSONDecodeError):
                    payload = {"series": [], "error": "The NHL playoff bracket is temporarily unavailable."}
            payload = {**payload, "servedFromCache": True}
    api_response = jsonify(payload)
    api_response.headers["Access-Control-Allow-Origin"] = "*"
    api_response.headers["Cache-Control"] = "no-store"
    return api_response

@app.route('/players')
def players():
    current_cache = load_cache()
    season_files = {current_cache.get("season_id", SEASON_ID): None}
    history_prefix = f"{TEAM_ABBREV.lower()}_history_"
    for history_file in glob.glob(str(DATA_DIR / f"{history_prefix}*.json")):
        season_id = os.path.basename(history_file).removeprefix(history_prefix).removesuffix(".json")
        if season_id.isdigit() and season_id >= PLAYER_HISTORY_START_SEASON:
            season_files[season_id] = history_file

    available_seasons = sorted(season_files, reverse=True)
    selected_season = request.args.get("season", SEASON_ID)
    if selected_season not in season_files:
        selected_season = available_seasons[0]
    selected_file = season_files[selected_season]
    selected_cache = current_cache if selected_file is None else load_cache(selected_file)
    player_map = {}

    def toi_seconds(toi):
        try:
            minutes, seconds = str(toi).split(":", 1)
            return int(minutes) * 60 + int(seconds)
        except (TypeError, ValueError):
            return 0

    def format_toi(seconds, total=False):
        seconds = max(int(round(seconds)), 0)
        if total:
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes}:{seconds:02d}"

    for game in selected_cache.get("games", []):
        metrics = game.get("match_metrics", {})
        for player in metrics.get("players", []):
            player_id = player.get("id")
            if not player_id:
                continue
            key = str(player_id)
            summary = player_map.setdefault(key, {
                "id": player_id,
                "number": player.get("number", "--"),
                "name": player.get("name", "Unknown Player"),
                "pos": player.get("pos", "--"),
                "games_tracked": 0,
                "toi_seconds": 0,
                "last_toi": "—",
                "last_game_date": "",
                "shots": 0,
                "hits": 0,
                "blocks": 0,
            })
            seconds_played = toi_seconds(player.get("toi"))
            if seconds_played <= 0:
                continue
            summary["games_tracked"] += 1
            summary["toi_seconds"] += seconds_played
            summary["shots"] += int(player.get("shots", 0) or 0)
            summary["hits"] += int(player.get("hits", 0) or 0)
            summary["blocks"] += int(player.get("blocks", 0) or 0)
            game_date = game.get("gameDate", "")
            if game_date >= summary["last_game_date"]:
                summary["last_game_date"] = game_date
                summary["last_toi"] = player.get("toi", "—")

    for summary in player_map.values():
        games = summary["games_tracked"]
        summary["avg_toi"] = format_toi(summary["toi_seconds"] / games) if games else "—"
        summary["total_toi"] = format_toi(summary["toi_seconds"], total=True) if games else "—"
        summary["shots_per_game"] = round(summary["shots"] / games, 1) if games else 0
        summary["hits_per_game"] = round(summary["hits"] / games, 1) if games else 0
        summary["blocks_per_game"] = round(summary["blocks"] / games, 1) if games else 0

    roster = sorted(player_map.values(), key=lambda player: (str(player["pos"]), str(player["name"])))
    seasons = [
        {"id": season_id, "label": f"{season_id[:4]}–{season_id[6:]}"}
        for season_id in available_seasons
    ]
    return render_template(
        "players.html",
        players=roster,
        seasons=seasons,
        selected_season=selected_season,
        selected_season_label=f"{selected_season[:4]}–{selected_season[6:]}",
        is_current_season=selected_season == SEASON_ID,
    )

@app.route('/cyd-preview')
def cyd_preview():
    return render_template("cyd_preview.html")

def process_games(raw_games):
    processed_games = []

    for game in raw_games:
        state = game.get("gameState", "FUT")
        home = game.get("homeTeam", {})
        away = game.get("awayTeam", {})

        home_score = home.get("score", 0)
        away_score = away.get("score", 0)
        home_abbrev = home.get("abbrev", "HOME")
        away_abbrev = away.get("abbrev", "AWAY")

        outcome_class = ""
        border_class = ""
        status_label = "Upcoming"

        if state == "LIVE":
            border_class = "border-live"
            status_label = "LIVE NOW"
        elif state == "OFF":
            status_label = "Final"
            if (home_abbrev == TEAM_ABBREV and home_score > away_score) or (away_abbrev == TEAM_ABBREV and away_score > home_score):
                outcome_class = "outcome-win"
            else:
                outcome_class = "outcome-loss"
        else:
            if not processed_games or processed_games[-1].get("state") == "OFF":
                border_class = "border-next"

        start_time_utc = game.get("startTimeUTC", "")
        date_str, time_str, timezone_name = format_utc_to_london(start_time_utc)
        matchup = f"{away_abbrev} @ {home_abbrev}"
        location = f"Home (@ {TEAM_ABBREV})" if home_abbrev == TEAM_ABBREV else f"Away (@ {home_abbrev})"

        processed_games.append({
            "id": game.get("id"),
            "date": date_str,
            "time": time_str,
            "timezone": timezone_name,
            "state": state,
            "matchup": matchup,
            "away_abbrev": away_abbrev,
            "home_abbrev": home_abbrev,
            "venue": location,
            "score": f"{away_abbrev} {away_score} - {home_abbrev} {home_score}",
            "status": status_label,
            "outcome_class": outcome_class,
            "border_class": border_class,
            "calendar_url": build_google_calendar_url(start_time_utc, matchup, location)
                if state in ["FUT", "PRE"] else None,
            "highlight_video_id": game.get("highlight_video_id"),
            "highlight_title": game.get("highlight_title"),
        })

    return processed_games

def build_boxscore_payload(game, metrics):
    home = game.get("homeTeam", {})
    away = game.get("awayTeam", {})
    return {
        "homeTeam": metrics.get("homeTeam", home.get("abbrev", "HOME")),
        "awayTeam": metrics.get("awayTeam", away.get("abbrev", "AWAY")),
        "home_team": metrics.get("homeTeam", home.get("abbrev", "HOME")),
        "away_team": metrics.get("awayTeam", away.get("abbrev", "AWAY")),
        "home_score": home.get("score", 0),
        "away_score": away.get("score", 0),
        "game_state": game.get("gameState", "FUT"),
        "period_type": game.get("periodDescriptor", {}).get("periodType", "REG"),
        "stats": metrics.get("stats", []),
        "timeline": metrics.get("timeline", []),
        "roster": metrics.get("roster", []),
        "players": metrics.get("players", []),
    }

@app.route('/game_boxscore/<game_id>')
def game_boxscore(game_id):
    cache_data = load_cache()

    for game in cache_data.get("games", []):
        if str(game.get("id")) == str(game_id):
            metrics = game.get("match_metrics", {})
            if game.get("gameState") in ("LIVE", "OFF") and not metrics.get("players"):
                refreshed_metrics = process_game_center(game_id)
                if refreshed_metrics.get("stats"):
                    metrics = refreshed_metrics
                    game["match_metrics"] = metrics
                    write_cache_atomic(cache_data)

            return jsonify(build_boxscore_payload(game, metrics))

    historical_cache = load_historical_cache()
    for game in historical_cache.get("games", []):
        if str(game.get("id")) == str(game_id):
            metrics = game.get("match_metrics")
            if not metrics or not metrics.get("stats") or not metrics.get("players"):
                metrics = process_game_center(game_id)
                if metrics.get("stats"):
                    save_historical_game_metrics(game_id, metrics)

            return jsonify(build_boxscore_payload(game, metrics))

    return jsonify({"home_team": "HOME", "away_team": "AWAY", "stats": [], "timeline": [], "roster": []})

@app.route('/player_stats/<player_id>')
def player_stats(player_id):
    try:
        cached = player_profile_cache.get(str(player_id))
        if cached and time.monotonic() - cached[0] < PLAYER_PROFILE_CACHE_SECONDS:
            return jsonify(cached[1])
        profile_url = f"https://api-web.nhle.com/v1/player/{player_id}/landing"
        import requests
        response = requests.get(profile_url, timeout=8)
        response.raise_for_status()
        profile_res = response.json()
        player_profile_cache[str(player_id)] = (time.monotonic(), profile_res)
        return jsonify(profile_res)
    except Exception as e:
        return jsonify({"error": f"Failed to reach player profile endpoint: {e}"}), 500

if __name__ == "__main__":
    # Local fallback only. External traffic should reach the production server
    # through the authenticated Cloudflare Tunnel, never Flask's debug server.
    app.run(host="127.0.0.1", port=int(os.environ.get("NHL_PORT", "5055")), debug=False)
