#!/bin/bash
# Deploy on sanctarus: pull main, update Python deps, restart the server.
# A sync that is running (tomato-streams-sync.service) is left alone; it picks up
# new code on its next run.
set -euo pipefail
cd /home/mwgreen/git-repos/tomato-streams
git pull --ff-only
.venv/bin/pip install -q -r requirements.txt
if ! cmp -s deploy/tomato-streams.service /etc/systemd/system/tomato-streams.service \
   || ! cmp -s deploy/tomato-streams-sync.timer /etc/systemd/system/tomato-streams-sync.timer \
   || ! cmp -s deploy/tomato-streams-sync.service /etc/systemd/system/tomato-streams-sync.service; then
  deploy/install.sh
else
  sudo systemctl restart tomato-streams
  sleep 3
  systemctl is-active --quiet tomato-streams || { echo "service not active after restart" >&2; exit 1; }
fi
curl -sf http://localhost:8765/api/ping >/dev/null && echo "deployed $(git rev-parse --short HEAD); /api/ping ok"
