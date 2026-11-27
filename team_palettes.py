"""Curated three-colour screen palettes for current NHL clubs."""

# Ordered as primary, secondary and highlight. These are presentation defaults,
# not a claim of ownership or an exhaustive reproduction of each brand guide.
TEAM_PALETTES = {
    "ANA": ("#f47a38", "#000000", "#b9975b"),
    "BOS": ("#ffb81c", "#000000", "#ffffff"),
    "BUF": ("#003087", "#ffb81c", "#ffffff"),
    "CGY": ("#d2001c", "#faaf19", "#000000"),
    "CAR": ("#ce1126", "#000000", "#a4a9ad"),
    "CHI": ("#cf0a2c", "#000000", "#ff671b"),
    "COL": ("#6f263d", "#236192", "#a2aaad"),
    "CBJ": ("#002654", "#ce1126", "#a4a9ad"),
    "DAL": ("#006847", "#8f8f8c", "#000000"),
    "DET": ("#ce1126", "#ffffff", "#a4a9ad"),
    "EDM": ("#041e42", "#ff4c00", "#ffffff"),
    "FLA": ("#041e42", "#c8102e", "#b9975b"),
    "LAK": ("#111111", "#a2aaad", "#ffffff"),
    "MIN": ("#154734", "#a6192e", "#eaaa00"),
    "MTL": ("#af1e2d", "#192168", "#ffffff"),
    "NSH": ("#ffb81c", "#041e42", "#ffffff"),
    "NJD": ("#ce1126", "#000000", "#ffffff"),
    "NYI": ("#00539b", "#f47d30", "#ffffff"),
    "NYR": ("#0038a8", "#ce1126", "#ffffff"),
    "OTT": ("#da1a32", "#000000", "#c69214"),
    "PHI": ("#f74902", "#000000", "#ffffff"),
    "PIT": ("#000000", "#fcb514", "#ffffff"),
    "SJS": ("#006d75", "#000000", "#ea7200"),
    "SEA": ("#001628", "#99d9d9", "#e9072b"),
    "STL": ("#002f87", "#fcb514", "#041e42"),
    "TBL": ("#002868", "#ffffff", "#000000"),
    "TOR": ("#00205b", "#ffffff", "#a2aaad"),
    "UTA": ("#010101", "#69b3e7", "#ffffff"),
    "VAN": ("#00205b", "#00843d", "#97999b"),
    "VGK": ("#b4975a", "#333f42", "#c8102e"),
    "WSH": ("#c8102e", "#041e42", "#ffffff"),
    "WPG": ("#041e42", "#ac162c", "#7b9ac0"),
}


def palette_for(abbreviation, fallback=("#748cab", "#f0b35a", "#dce4ef")):
    return TEAM_PALETTES.get(str(abbreviation).upper(), fallback)
