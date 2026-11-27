"""Validation and derivation helpers for NHL season identifiers."""

import re


def validate_season_id(value):
    season_id = str(value).strip()
    if not re.fullmatch(r"\d{8}", season_id):
        raise ValueError("Season IDs must contain eight digits, for example 20262027.")
    start, end = int(season_id[:4]), int(season_id[4:])
    if end != start + 1:
        raise ValueError("The season must span consecutive years, for example 20262027.")
    return season_id


def previous_season_id(value):
    season_id = validate_season_id(value)
    return f"{int(season_id[:4]) - 1:04d}{int(season_id[4:]) - 1:04d}"
