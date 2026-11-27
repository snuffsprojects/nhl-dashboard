"""NHL game-center parsing and live MQTT score state."""

import time

import requests

from config import HTTP_HEADERS, MQTT_TOPIC_GOAL, MQTT_TOPIC_SCORE, TEAM_ABBREV
from mqtt_publisher import publish_mqtt


last_broadcasted_score = ""
last_goal_count = 0

def process_game_center(game_id):
    try:
        ts = str(int(time.time()))
        pbp_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play?v={ts}"
        pbp_response = requests.get(pbp_url, headers=HTTP_HEADERS, timeout=5)
        pbp_response.raise_for_status()
        pbp_res = pbp_response.json()

        home_abbrev = pbp_res.get("homeTeam", {}).get("abbrev", "HOME")
        away_abbrev = pbp_res.get("awayTeam", {}).get("abbrev", "AWAY")

        scoring_timeline = []
        landing_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/landing?v={ts}"
        landing_response = requests.get(landing_url, headers=HTTP_HEADERS, timeout=5)
        landing_response.raise_for_status()
        landing_res = landing_response.json()

        summary_obj = landing_res.get("summary", {})
        goals_list = []

        # The landing response groups goals by period. Preserve that authoritative
        # period descriptor on each goal instead of trying to infer periods from
        # the goal's position in a flattened list.
        for period_data in summary_obj.get("scoring", []):
            period_descriptor = period_data.get("periodDescriptor", {})
            period_number = period_descriptor.get("number", period_data.get("period"))
            period_type = period_descriptor.get("periodType", "REG")

            for goal in period_data.get("goals", []):
                timeline_goal = dict(goal)
                timeline_goal["_period_number"] = period_number
                timeline_goal["_period_type"] = period_type
                goals_list.append(timeline_goal)

        # Retain compatibility if the NHL omits the grouped scoring summary.
        if not goals_list:
            goals_list = summary_obj.get("scoringGoals", [])

        for goal in goals_list:
            raw_period = goal.get("_period_number")
            period_type = goal.get("_period_type", "REG")

            if raw_period is None and "periodDescriptor" in goal and isinstance(goal["periodDescriptor"], dict):
                raw_period = goal["periodDescriptor"].get("number", 1)
                period_type = goal["periodDescriptor"].get("periodType", period_type)
            elif raw_period is None and "periodNumber" in goal:
                raw_period = goal["periodNumber"]
            elif raw_period is None and "period" in goal and not isinstance(goal["period"], dict):
                raw_period = goal["period"]

            if raw_period is None:
                raw_period = 1

            try:
                raw_period = int(raw_period)
            except Exception:
                raw_period = 1

            if period_type == "SO":
                period_label = "SO"
            elif raw_period == 4 or period_type == "OT":
                period_label = "OT" if raw_period == 4 else f"{raw_period - 3}OT"
            else:
                period_label = f"P{raw_period}"

            formatted_time = goal.get("timeInPeriod", "00:00")

            try:
                min_str, sec_str = formatted_time.split(":")
                elapsed_seconds = (int(min_str) * 60) + int(sec_str)
                game_elapsed_seconds = ((raw_period - 1) * 20 * 60) + elapsed_seconds
                pct_position = min((game_elapsed_seconds / (60 * 60)) * 100, 100)
            except Exception:
                pct_position = 50

            team_abbrev = "UNK"
            if "teamAbbrev" in goal:
                if isinstance(goal["teamAbbrev"], dict): team_abbrev = goal["teamAbbrev"].get("default", "UNK")
                else: team_abbrev = str(goal["teamAbbrev"])

            scorer_name = "Unknown Player"
            if "name" in goal:
                if isinstance(goal["name"], dict): scorer_name = goal["name"].get("default", "Unknown")
                else: scorer_name = str(goal["name"])
            elif "firstName" in goal:
                f_name = goal.get("firstName", {}).get("default", "")
                l_name = goal.get("lastName", {}).get("default", "")
                scorer_name = f"{f_name} {l_name}".strip() or "Unknown"

            scoring_timeline.append({
                "period": period_label,
                "time": formatted_time,
                "team": team_abbrev,
                "scorer": scorer_name,
                "home_score": goal.get("homeScore", 0),
                "away_score": goal.get("awayScore", 0),
                "position_pct": round(pct_position, 1)
            })

        global last_broadcasted_score, last_goal_count
        game_state = pbp_res.get("gameState", "FUT")
        current_goal_count = len(scoring_timeline)
        live_score_payload = None

        if game_state == "LIVE":
            home_score = pbp_res.get("homeTeam", {}).get("score", 0)
            away_score = pbp_res.get("awayTeam", {}).get("score", 0)
            current_score_str = f"{away_abbrev} {away_score} - {home_abbrev} {home_score}"

            live_period = 1
            if "periodDescriptor" in pbp_res and isinstance(pbp_res["periodDescriptor"], dict):
                live_period = pbp_res["periodDescriptor"].get("number", 1)
            else:
                live_period = pbp_res.get("period", 1)

            try:
                live_period = int(live_period)
            except Exception:
                live_period = 1

            live_score_payload = {
                "status": "LIVE",
                "matchup": f"{away_abbrev} @ {home_abbrev}",
                "score_string": current_score_str,
                "away_score": away_score,
                "home_score": home_score,
                "period": live_period,
                "time_remaining": pbp_res.get("clock", {}).get("timeRemaining", "20:00")
            }

            if current_score_str != last_broadcasted_score:
                if last_broadcasted_score != "":
                    if current_goal_count > last_goal_count:
                        latest_goal = scoring_timeline[-1] if scoring_timeline else {}
                        goal_payload = {"alert": "GOAL SCORED!", "score": current_score_str, "details": latest_goal}
                        publish_mqtt(MQTT_TOPIC_GOAL, goal_payload)
                    elif current_goal_count < last_goal_count:
                        goal_payload = {
                            "alert": "DISALLOWED_RESET",
                            "score": current_score_str,
                            "details": {"msg": "Goal recalled by review. Clear display states."}
                        }
                        publish_mqtt(MQTT_TOPIC_GOAL, goal_payload)

                last_broadcasted_score = current_score_str
                last_goal_count = current_goal_count

        box_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore?v={ts}"
        box_response = requests.get(box_url, headers=HTTP_HEADERS, timeout=5)
        box_response.raise_for_status()
        box_res = box_response.json()
        player_data = box_res.get("playerByGameStats", {})

        totals = {"home": {"sog": 0, "hits": 0, "blocks": 0, "pim": 0}, "away": {"sog": 0, "hits": 0, "blocks": 0, "pim": 0}}
        game_roster = []
        selected_team_players = []

        for side in ["homeTeam", "awayTeam"]:
            target_side = "home" if side == "homeTeam" else "away"
            team_box = player_data.get(side, {})
            team_abbrev = home_abbrev if side == "homeTeam" else away_abbrev
            is_selected_team = team_abbrev == TEAM_ABBREV

            for pos_key in ["forwards", "defense", "goalies"]:
                skaters_list = team_box.get(pos_key, [])
                for p in skaters_list:
                    totals[target_side]["sog"] += p.get("sog", p.get("shots", 0))
                    totals[target_side]["hits"] += p.get("hits", 0)
                    totals[target_side]["blocks"] += p.get("blockedShots", 0)
                    totals[target_side]["pim"] += p.get("pim", 0)

                    if is_selected_team:
                        f_name = p.get("firstName", {}).get("default", "")
                        l_name = p.get("lastName", {}).get("default", "")
                        p_name = f"{f_name} {l_name}".strip() or p.get("name", {}).get("default", "Unknown")
                        pos_code = "G" if pos_key == "goalies" else "D" if pos_key == "defense" else "F"
                        if "position" in p: pos_code = p.get("position")

                        game_roster.append({
                            "id": p.get("playerId"),
                            "number": p.get("sweaterNumber", "--"),
                            "name": p_name,
                            "pos": pos_code
                        })

                        player_game = {
                            "id": p.get("playerId"),
                            "number": p.get("sweaterNumber", "--"),
                            "name": p_name,
                            "pos": pos_code,
                            "type": "goalie" if pos_key == "goalies" else "skater",
                            "toi": p.get("toi", "00:00"),
                            "pim": p.get("pim", 0),
                        }
                        if pos_key == "goalies":
                            saves_against = str(p.get("saveShotsAgainst", "0/0"))
                            try:
                                saves, shots_against = [int(value) for value in saves_against.split("/", 1)]
                            except (TypeError, ValueError):
                                saves, shots_against = 0, 0
                            player_game.update({
                                "decision": p.get("decision", ""),
                                "saves": saves,
                                "shots_against": shots_against,
                                "goals_against": p.get("goalsAgainst", max(shots_against - saves, 0)),
                                "save_pct": p.get("savePctg"),
                                "starter": bool(p.get("starter", False)),
                            })
                        else:
                            player_game.update({
                                "goals": p.get("goals", 0),
                                "assists": p.get("assists", 0),
                                "points": p.get("points", p.get("goals", 0) + p.get("assists", 0)),
                                "plus_minus": p.get("plusMinus", 0),
                                "shots": p.get("sog", p.get("shots", 0)),
                                "hits": p.get("hits", 0),
                                "blocks": p.get("blockedShots", 0),
                            })
                        selected_team_players.append(player_game)

        game_roster.sort(key=lambda x: x["name"])
        parsed_stats = [
            {"label": "Shots on Goal", "away": totals["away"]["sog"], "home": totals["home"]["sog"]},
            {"label": "Hits", "away": totals["away"]["hits"], "home": totals["home"]["hits"]},
            {"label": "Blocked Shots", "away": totals["away"]["blocks"], "home": totals["home"]["blocks"]},
            {"label": "Penalty Minutes", "away": totals["away"]["pim"], "home": totals["home"]["pim"]}
        ]

        if live_score_payload is not None:
            period_scores = []
            for period_label in ("P1", "P2", "P3", "OT", "SO"):
                away_period = sum(1 for goal in scoring_timeline if goal.get("period") == period_label and goal.get("team") == away_abbrev)
                home_period = sum(1 for goal in scoring_timeline if goal.get("period") == period_label and goal.get("team") == home_abbrev)
                if period_label in ("P1", "P2", "P3") or away_period or home_period:
                    period_scores.append([period_label, away_period, home_period])

            live_score_payload.update({
                "away_team": away_abbrev,
                "home_team": home_abbrev,
                "period_scores": period_scores,
                "shots": [totals["away"]["sog"], totals["home"]["sog"]],
                "hits": [totals["away"]["hits"], totals["home"]["hits"]],
                "blocks": [totals["away"]["blocks"], totals["home"]["blocks"]],
            })
            publish_mqtt(MQTT_TOPIC_SCORE, live_score_payload)

        return {
            "homeTeam": home_abbrev,
            "awayTeam": away_abbrev,
            "stats": parsed_stats,
            "timeline": scoring_timeline,
            "roster": game_roster,
            "players": selected_team_players,
        }
    except Exception as e:
        print(f"\n[METRIC BREAKDOWN RECOVERY] Shielded glitch on game {game_id}: {e}")
        return {"homeTeam": "HOME", "awayTeam": "AWAY", "stats": [], "timeline": [], "roster": [], "players": []}
