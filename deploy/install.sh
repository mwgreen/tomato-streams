#!/bin/bash
# Install / refresh the systemd units on sanctarus. Run from the repo root on the box:
#   deploy/install.sh
# First-time setup (venv, .env, data) is in deploy/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."
sudo install -m 644 deploy/tomato-streams.service deploy/tomato-streams-sync.service \
  deploy/tomato-streams-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tomato-streams.service tomato-streams-sync.timer
sudo systemctl restart tomato-streams.service
sleep 3
systemctl is-active --quiet tomato-streams || { echo "tomato-streams not active" >&2; exit 1; }
systemctl list-timers tomato-streams-sync.timer --no-pager | head -2
