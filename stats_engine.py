"""Season-level statistics for the configured NHL team."""

from collections import defaultdict
from datetime import datetime

from config import TEAM_ABBREV


def _game_record(game):
    home = game.get("homeTeam", {})
    away = game.get("awayTeam", {})
    is_home = home.get("abbrev") == TEAM_ABBREV
    selected_team = home if is_home else away
    opponent = away if is_home else home
    goals_for = int(selected_team.get("score", 0) or 0)
    goals_against = int(opponent.get("score", 0) or 0)
    won = goals_for > goals_against
    finish = (
        game.get("gameOutcome", {}).get("lastPeriodType")
        or game.get("periodDescriptor", {}).get("periodType")
        or "REG"
    )
    overtime_loss = not won and finish in ("OT", "SO") and game.get("gameType") == 2

    return {
        "id": game.get("id"),
        "date": game.get("gameDate") or str(game.get("startTimeUTC", ""))[:10],
        "month": (game.get("gameDate") or str(game.get("startTimeUTC", ""))[:10])[:7],
        "home": is_home,
        "opponent": opponent.get("abbrev", "UNK"),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "result": "W" if won else "OTL" if overtime_loss else "L",
        "finish": finish,
        "game_type": game.get("gameType"),
    }


def _empty_summary(label=""):
    return {
        "label": label, "games": 0, "wins": 0, "losses": 0, "otl": 0,
        "points": 0, "goals_for": 0, "goals_against": 0, "goal_diff": 0,
        "win_pct": 0, "gf_per_game": 0, "ga_per_game": 0,
    }


def summarise(records, label=""):
    summary = _empty_summary(label)
    summary["games"] = len(records)
    summary["wins"] = sum(r["result"] == "W" for r in records)
    summary["otl"] = sum(r["result"] == "OTL" for r in records)
    summary["losses"] = summary["games"] - summary["wins"] - summary["otl"]
    summary["points"] = (summary["wins"] * 2) + summary["otl"]
    summary["goals_for"] = sum(r["goals_for"] for r in records)
    summary["goals_against"] = sum(r["goals_against"] for r in records)
    summary["goal_diff"] = summary["goals_for"] - summary["goals_against"]
    if records:
        summary["win_pct"] = round(summary["wins"] / summary["games"] * 100, 1)
        summary["gf_per_game"] = round(summary["goals_for"] / summary["games"], 2)
        summary["ga_per_game"] = round(summary["goals_against"] / summary["games"], 2)
    return summary


def _longest_streak(records, target):
    best = current = 0
    for record in records:
        matches = record["result"] == "W" if target == "W" else record["result"] != "W"
        current = current + 1 if matches else 0
        best = max(best, current)
    return best


def _build_view(records, label, points_apply=False):
    month_groups = defaultdict(list)
    opponent_groups = defaultdict(list)
    for record in records:
        month_groups[record["month"]].append(record)
        opponent_groups[record["opponent"]].append(record)

    months = []
    for month, grouped_records in sorted(month_groups.items()):
        item = summarise(grouped_records, datetime.strptime(month, "%Y-%m").strftime("%B %Y"))
        months.append(item)

    opponents = [
        summarise(grouped_records, opponent)
        for opponent, grouped_records in opponent_groups.items()
    ]
    opponents.sort(key=lambda item: (-item["games"], item["label"]))

    return {
        "label": label,
        "points_apply": points_apply,
        "overall": summarise(records, label),
        "home": summarise([r for r in records if r["home"]], "Home"),
        "away": summarise([r for r in records if not r["home"]], "Away"),
        "recent": summarise(records[-10:], "Last 10"),
        "recent_results": records[-10:],
        "months": months,
        "opponents": opponents,
        "longest_win_streak": _longest_streak(records, "W"),
        "longest_losing_streak": _longest_streak(records, "L"),
        "one_goal_games": sum(abs(r["goals_for"] - r["goals_against"]) == 1 for r in records),
        "overtime_games": sum(r["finish"] in ("OT", "SO") for r in records),
        "shutouts_for": sum(r["goals_against"] == 0 for r in records),
        "shutouts_against": sum(r["goals_for"] == 0 for r in records),
    }


def build_season_stats(games):
    completed = sorted(
        (
            _game_record(game) for game in games
            if game.get("gameState") == "OFF" and game.get("gameType") in (2, 3)
        ),
        key=lambda record: record["date"],
    )
    regular = [r for r in completed if r["game_type"] == 2]
    playoffs = [r for r in completed if r["game_type"] == 3]
    views = {
        "regular": _build_view(regular, "Regular Season", points_apply=True),
        "playoffs": _build_view(playoffs, "Playoffs"),
        "combined": _build_view(completed, "Combined"),
    }

    # Keep these summary aliases for callers that only need season availability.
    return {
        "overall": views["combined"]["overall"],
        "regular": views["regular"]["overall"],
        "playoffs": views["playoffs"]["overall"],
        "views": views,
    }
