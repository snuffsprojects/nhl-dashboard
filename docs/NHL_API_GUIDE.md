# NHL web API field guide

Practical notes for the unauthenticated JSON feeds used by NHL Dashboard.

> [!IMPORTANT]
> These endpoints are operated by NHL.com, but this is an independent field guide—not official NHL developer documentation. There is no published compatibility or availability guarantee. Treat every response defensively, cache successful data, use moderate polling, and expect fields or shapes to change.

Last live verification: **27 November 2026**.

## Base hosts

| Purpose | Base URL |
|---|---|
| JSON data | `https://api-web.nhle.com/v1` |
| Team SVG logos | `https://assets.nhle.com/logos/nhl/svg` |
| Default player image | `https://assets.nhle.com/mugs/nhl/default-headshot.png` |

The JSON requests observed here require no API key or authentication. Send an identifiable `User-Agent`, set a finite timeout, check the HTTP status before decoding JSON, and avoid browser-to-NHL calls when a small server-side cache will do.

```python
import requests

response = requests.get(
    "https://api-web.nhle.com/v1/standings/now",
    headers={"User-Agent": "my-hockey-project/1.0"},
    timeout=10,
)
response.raise_for_status()
payload = response.json()
```

## Endpoint summary

| Data | Endpoint |
|---|---|
| Club season schedule | `/club-schedule-season/{TEAM}/{SEASON}` |
| Current standings | `/standings/now` |
| Game play-by-play | `/gamecenter/{GAME_ID}/play-by-play` |
| Game landing summary | `/gamecenter/{GAME_ID}/landing` |
| Game box score | `/gamecenter/{GAME_ID}/boxscore` |
| Player profile and totals | `/player/{PLAYER_ID}/landing` |
| Stanley Cup bracket | `/playoff-bracket/{CUP_YEAR}` |

Examples below use Philadelphia, season `20262027`, and completed game `2026020229`. IDs should be treated as opaque strings or integers even when their digits appear meaningful.

## Season identifiers

Season IDs concatenate the starting and ending calendar years:

- `20262027` means the 2026–27 season.
- The immediately previous season is `20252026`.
- The dashboard validates that the second year is exactly one greater than the first.

Do not use the Stanley Cup year in schedule endpoints. The playoff-bracket endpoint is the exception: `/playoff-bracket/2026` represents the playoffs ending in 2026.

## Club season schedule

```text
GET https://api-web.nhle.com/v1/club-schedule-season/PHI/20262027
```

Observed top-level fields:

```text
previousSeason  currentSeason  clubTimezone  clubUTCOffset  games[]
```

Useful fields on each game:

```text
id
season
gameType
gameDate
startTimeUTC
gameState
gameScheduleState
venue
awayTeam
homeTeam
periodDescriptor
gameOutcome
tvBroadcasts
gameCenterLink
```

Team objects commonly include `id`, `abbrev`, localized names, logo URLs, split-squad flags, and—once applicable—`score`.

This feed is the best discovery point for game IDs and the authoritative input for a team schedule. NHL Dashboard filters `gameType == 2` as regular season and `gameType == 3` as playoffs. Other values should be preserved or ignored deliberately rather than assumed to be regular-season games.

## Game states and timing

States observed and handled by this project:

| Value | Practical meaning |
|---|---|
| `FUT` | Scheduled future game |
| `PRE` | Pregame state close to puck drop |
| `LIVE` | Game in progress |
| `CRIT` | Live game in a late/critical phase |
| `FINAL` | Game ended; post-game processing may still be underway |
| `OFF` | Completed and official enough to cache as final |
| `SUSP` | Game suspended; continue monitoring without discarding cached details |
| `PPD` | Game postponed |
| `CNCL` | Game cancelled |

Treat both `FINAL` and `OFF` as completed, and both `LIVE` and `CRIT` as live. The NHL may add or use additional values, so unknown states must be shown explicitly and must not be silently treated as upcoming or erase previously cached game details.

`startTimeUTC` is an ISO-8601 UTC value such as `2026-11-01T21:00:00Z`. Display it by converting from UTC into the viewer's or configured venue timezone; do not manually add a fixed offset. Schedule objects may also provide `easternUTCOffset`, `venueUTCOffset`, and `venueTimezone`.

`periodDescriptor` usually contains:

```json
{"number": 3, "periodType": "REG", "maxRegulationPeriods": 3}
```

Observed period types include regulation (`REG`), overtime (`OT`), and shootout (`SO`). Overtime loss classification should use the final period type rather than merely comparing scores.

## Play-by-play

```text
GET https://api-web.nhle.com/v1/gamecenter/2026020229/play-by-play
```

Observed top-level fields include game identity and teams plus:

```text
gameState  periodDescriptor  clock  plays[]  rosterSpots[]  summary
```

The `plays` collection is the detailed event stream. Event shapes vary by event type, so consumers should branch on the event descriptor/type and tolerate missing detail fields.

For live use, this endpoint also supplies the current clock and team scores. NHL Dashboard polls quickly only around a live game and otherwise backs off; it does not poll every historical game repeatedly.

## Landing summary

```text
GET https://api-web.nhle.com/v1/gamecenter/2026020229/landing
```

The useful high-level section is `summary`, observed with:

```text
scoring[]  threeStars[]  penalties[]
```

`summary.scoring` is grouped by period. Each group has a `periodDescriptor` and a `goals` array. Keep the group's period descriptor attached when flattening the goals; individual goal records have not always carried enough period context by themselves.

Depending on the response/version, a fallback flattened `summary.scoringGoals` may be present. Defensive consumers can support both shapes.

Goal objects used by this project may contain:

```text
timeInPeriod
teamAbbrev
name or firstName/lastName
homeScore
awayScore
```

Names and abbreviations can be localized objects instead of plain strings.

## Box score and player-by-game statistics

```text
GET https://api-web.nhle.com/v1/gamecenter/2026020229/boxscore
```

The principal structure is:

```text
playerByGameStats
  awayTeam
    forwards[]
    defense[]
    goalies[]
  homeTeam
    forwards[]
    defense[]
    goalies[]
```

Common skater fields include:

```text
playerId  sweaterNumber  position  firstName  lastName
toi  pim  goals  assists  points  plusMinus
sog or shots  hits  blockedShots
```

Common goalie fields include:

```text
toi  pim  decision  saveShotsAgainst  savePctg  goalsAgainst  starter
```

`saveShotsAgainst` has been observed as a string such as `"28/30"`, not two numeric fields. Parse it defensively. Some unused or dressed goalies can legitimately report zero time and zero shots.

The dashboard derives team totals by summing player rows. This works for shots, hits, blocks, and penalty minutes but is an implementation choice, not a promise that every future team-level metric can be reconstructed this way.

## Player landing profile

```text
GET https://api-web.nhle.com/v1/player/8478439/landing
```

Observed identity fields include:

```text
playerId  isActive  currentTeamId  currentTeamAbbrev
firstName  lastName  sweaterNumber  position
headshot  heroImage  heightInInches  weightInPounds
birthDate  birthCity  birthCountry  shootsCatches
draftDetails  playerSlug
```

Statistical sections include `featuredStats` and `careerTotals`. `featuredStats` has been observed with a `season` plus a `regularSeason` object; playoff data is not guaranteed to exist. UI code should treat missing subsections as “no data,” not an error.

## Current standings

```text
GET https://api-web.nhle.com/v1/standings/now
```

Observed top-level fields:

```text
wildCardIndicator  standingsDateTimeUtc  standings[]
```

On 27 November 2026 the feed returned 32 rows. Useful fields include:

```text
teamAbbrev  teamName  teamCommonName  placeName
teamLogo  teamLogoDark
conferenceName  conferenceSequence
divisionName  divisionSequence
leagueSequence
gamesPlayed  wins  losses  otLosses  points
goalFor  goalAgainst  goalDifferential
l10Wins  l10Losses  l10OtLosses
```

The standings feed is also a convenient way to discover the current clubs, names, abbreviations, and logo URLs. Do not assume array order alone expresses rank; use the appropriate sequence field.

## Stanley Cup bracket

```text
GET https://api-web.nhle.com/v1/playoff-bracket/2026
```

Observed top-level fields:

```text
bracketLogo  bracketLogoFr  series[]
```

A completed bracket returned 15 series. Series records include a `seriesLetter`, round/series status, top and bottom seed team data, win counts, and a winning-team identifier when decided.

Before a season's bracket is seeded, the endpoint may return an empty `series` array rather than an HTTP error. NHL Dashboard deliberately falls back to the most recent populated bracket for display.

## Localized values

Many names are objects rather than strings:

```json
{"default": "Philadelphia", "fr": "Philadelphie"}
```

Use `value.default` when present, but also accept an already-flat string and a missing value:

```python
def localized(value):
    if isinstance(value, dict):
        return value.get("default", "")
    return str(value or "")
```

This applies to team names, places, venues, player names, abbreviations, and other labels.

## Logos and images

A predictable team logo URL currently works as:

```text
https://assets.nhle.com/logos/nhl/svg/{ABBREV}_dark.svg
https://assets.nhle.com/logos/nhl/svg/{ABBREV}_light.svg
```

Prefer the logo URL returned by the API when available, with the predictable path as a fallback. Team marks and player images belong to their respective owners; do not imply that an open-source application's licence grants rights to those assets.

## Caching and polling lessons

NHL Dashboard uses these practical rules:

- Cache full schedules locally and replace cache files atomically.
- Poll every 15 seconds only around a live/pregame window.
- Back off to 10 minutes while idle.
- Cache completed-game details permanently; a final box score does not need refetching every cycle.
- Retry a completed game on a later cycle if its cached metrics are empty.
- Cache standings briefly (90 seconds in this project) and keep a disk fallback.
- Cache playoff brackets briefly (five minutes) and keep per-year disk fallbacks.
- Refresh the previous-season schedule at most daily.
- Keep each team's cache namespace separate.
- Preserve the last successful response when a transient request fails.

No published rate limit has been found. That is a reason to be conservative, not permission to send unlimited traffic.

## Failure modes observed in practice

- A schedule can arrive before all detailed game-centre calls finish. Show “still syncing” rather than treating that as permanent data loss.
- HTTP success does not guarantee a populated playoff bracket.
- Historical/player subsections can be absent.
- Localized fields can switch between object and scalar shapes.
- Fields can be `null`, omitted, or represented as formatted strings.
- A reverse-proxied application must generate prefix-aware local URLs; this is unrelated to NHL data but can look like an API failure in the UI.
- A failed `.json()` call can hide an HTTP error. Always call `raise_for_status()` first in new code.
- The feeds have no compatibility contract. Keep parsing isolated, tested, and tolerant.

## Minimal discovery workflow

```bash
# 1. Find a club's games and game IDs.
curl -fsS 'https://api-web.nhle.com/v1/club-schedule-season/PHI/20262027'

# 2. Inspect a final game's summary.
curl -fsS 'https://api-web.nhle.com/v1/gamecenter/2026020229/landing'

# 3. Inspect player-by-game rows.
curl -fsS 'https://api-web.nhle.com/v1/gamecenter/2026020229/boxscore'

# 4. Inspect an individual player.
curl -fsS 'https://api-web.nhle.com/v1/player/8478439/landing'

# 5. Discover all current clubs and rankings.
curl -fsS 'https://api-web.nhle.com/v1/standings/now'
```

Use `jq 'keys'`, `jq '.games[0]'`, or a short script to inspect live shapes rather than copying assumptions from this guide indefinitely.

## What this guide intentionally does not claim

- That the endpoints are a supported public developer API.
- That every possible field or enum value is listed.
- That the endpoints will remain unauthenticated or unchanged.
- That NHL, club, logo, or player-image rights are covered by this repository's software licence.
- That observed polling intervals are endorsed by NHL.com.

If you discover a changed field or another stable endpoint, please open an issue with the endpoint, observation date, a redacted example, and the smallest reproducible parser change.
