#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Restarting the systemd-managed NHL synchronizer..."
sudo systemctl restart nhl-dashboard-sync.service
systemctl status nhl-dashboard-sync.service --no-pager
