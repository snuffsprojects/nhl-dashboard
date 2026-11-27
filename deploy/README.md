# Deployment templates

These examples assume the repository is installed at `/opt/nhl-dashboard`, its virtual environment is `/opt/nhl-dashboard/.venv`, the service account is `pi`, and writable data belongs in `/var/lib/nhl-dashboard`.

Before installing them, review and change:

- `User=` and `Group=` in both long-running services;
- every `/opt/nhl-dashboard` path if the checkout lives elsewhere;
- `ReadWritePaths=` and `NHL_DATA_DIR` together if data lives elsewhere;
- the nginx route and `X-Forwarded-Prefix` together if you want a different URL;
- the Python virtual-environment paths if you use a system or container runtime.

The web application trusts one layer of forwarded host, protocol and prefix headers. Do not expose Gunicorn directly to untrusted clients while allowing them to supply those headers; put it behind the configured nginx proxy.

The settings path unit watches `settings.json`. Its oneshot service stops the synchronizer, optionally performs a constrained requested cache purge, restarts the web process and starts the synchronizer. The web service itself cannot invoke `systemctl`.
