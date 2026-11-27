# Security

## Supported version

Security fixes are applied to the latest version on the default branch.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting feature rather than opening a public issue. Include the affected route or component, deployment shape, reproduction steps, and potential impact. Do not include live credentials, session cookies, private IP addresses, or personal data.

## Deployment boundary

NHL Dashboard is designed for a trusted local network. The included nginx example restricts `/settings` and every nested settings route to loopback and RFC1918 private networks in addition to application authentication and CSRF protection.

Before exposing any route publicly:

- put Gunicorn behind a trusted reverse proxy;
- do not permit clients to spoof forwarded host, protocol, or prefix headers;
- use HTTPS and an additional authentication/access layer;
- keep `/etc/nhl-dashboard.env`, `settings.json`, `session.key`, Wi-Fi headers, and API keys out of source control;
- run the services as an unprivileged account with a dedicated writable data directory;
- review the nginx allow/deny rules for your actual network ranges.

The public schedule pages consume NHL-hosted data and images. The optional YouTube integration requires a separately supplied API key. MQTT is disabled by default and should not be exposed to untrusted networks without its own authentication and authorization.
