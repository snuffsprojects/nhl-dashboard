# NHL Dashboard

A self-hosted dashboard for following any NHL club. It includes current and historical schedules, live and final game detail, season statistics, player summaries, league standings, Stanley Cup brackets, calendar links and optional YouTube highlight matching.

The repository also includes an independent [NHL web API field guide](docs/NHL_API_GUIDE.md) covering the endpoints, observed response shapes, game states, localization, caching, polling and failure modes learned while building the dashboard.

This project was extracted from the original VGK Watch installation. VGK remains the default example, but the application has no fixed team in its schedule, statistics, player, standings or playoff logic.

## Choose a team

On a packaged LAN installation, open `/intranet/nhl-dashboard/settings` in a browser. The first visit asks you to create a local administrator password; after that, the page discovers the current NHL clubs and lets you choose the team, branding colours, timezone and current season. The historical view is always derived as the immediately preceding season, so `20262027` automatically uses `20252026` for history. A bundled 32-team palette library supplies three-colour themes automatically, with manual colour overrides still available. Saving writes a private local settings file and reloads only the two NHL Dashboard services. The nginx example limits every settings URL to loopback and RFC1918 private networks.

The settings page also has a confirmed **Purge cached data** action for changing teams or troubleshooting. It removes only regenerable team schedules, historical game details, standings and playoff cache files. It deliberately preserves `settings.json`, `session.key`, the administrator password hash and environment configuration. The apply service stops the synchronizer before deletion to prevent an in-progress cycle recreating old cache files, then restarts the web and sync services. The selected team can take several minutes to repopulate afterward.

Environment variables provide the initial defaults and remain useful for headless or multi-instance deployments. Persisted choices from the settings page take precedence over those defaults. Copy `.env.example` to a deployment-owned environment file and change at least:

```ini
NHL_TEAM=SEA
NHL_TEAM_NAME=Seattle Kraken
NHL_TEAM_SHORT_NAME=Kraken
NHL_TEAM_LOCATION=Seattle
NHL_TEAM_MARK=S
NHL_SITE_NAME=Kraken Watch
NHL_MQTT_TOPIC_PREFIX=nhl/sea
```

`NHL_TEAM` must be the three-letter abbreviation accepted by the NHL schedule API. Cache files and optional MQTT topics are namespaced by that abbreviation. Use a separate `NHL_DATA_DIR` for each instance if you run more than one team.

## Run locally

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
set -a; . ./.env; set +a
.venv/bin/python sync.py
```

Run the web app separately with:

```sh
.venv/bin/gunicorn --bind 127.0.0.1:5055 --workers 2 --threads 2 app:app
```

The synchronizer refreshes rapidly around games and every ten minutes while idle. Example systemd and nginx files are under `deploy/`; they assume an `/opt/nhl-dashboard` checkout and must be reviewed for your user, paths and desired URL before installation. See [the deployment notes](deploy/README.md) and `.env.example` for all settings. Install both `nhl-dashboard-settings.*` units to apply browser changes automatically. MQTT and YouTube are optional; MQTT is disabled by default.

The NHL web feeds used here are public endpoints, not a compatibility-guaranteed developer API. Team names and logos belong to their respective owners; logo artwork is loaded from NHL-hosted URLs at runtime and is not bundled.

The screen-oriented palette library in `team_palettes.py` was last reviewed on 25 November 2026 against the current 32-team colour table at [Tightknit](https://tightknit.ai/team-colors/nhl/), which in turn identifies its published sources. The third value is a curated supporting highlight where a club publishes only two dominant colours. Palettes are defaults rather than bundled brand assets, and all names, colours and marks remain the property of their respective owners.

## CYD companion display

The existing `CYD-Board-Software/` Arduino sketch, `CYD-PlatformIO/` project and browser design preview are retained as a future-update prototype. They remain VGK-specific and are **not** part of the generic-team guarantee yet. Real secret headers are excluded. A future release should move team identity, colours, labels and MQTT topics into shared build-time configuration before enabling MQTT for a generic deployment.

## Data, secrets and tests

Do not commit `.env`, `data/`, live caches, logs, PID files, lock files, virtual environments or CYD secret headers. The included `.gitignore` covers them.

```sh
python3 -m unittest discover -s tests
```
