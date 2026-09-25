# Running on sanctarus

Production copy lives on **sanctarus** (`ssh 192.168.68.77`, see the `sanctarus-infra` repo)
at `/home/mwgreen/git-repos/tomato-streams`, tracking `main`.

| What | Where |
|---|---|
| Web app + API | `tomato-streams.service`, `serve.py --host 0.0.0.0 --port 8765` |
| Public URL | https://tomato.sanctarus.com (cloudflared tunnel → localhost:8765, Cloudflare Access: Matt + Deb) |
| Home network | http://192.168.68.77:8765 — the Apple TV app finds it via Bonjour (it can't pass the Access login) |
| Weekly sync | `tomato-streams-sync.timer`, Sundays 06:00 → `sync.py` |
| Secrets | `.env` on the box only (TMDB, OMDb, Watchmode keys) |
| State | `cache/`, `data/*.json` (incl. `data/watched.json`) on the box only |

## Deploy a change

```sh
git push origin main
ssh 192.168.68.77 /home/mwgreen/git-repos/tomato-streams/scripts/deploy.sh
```

`deploy.sh` pulls, updates Python deps, reinstalls the systemd units if they changed, and
restarts the server.

## First-time setup (done 2026-09-25)

```sh
git clone https://github.com/mwgreen/tomato-streams.git ~/git-repos/tomato-streams
cd ~/git-repos/tomato-streams
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# copy .env, and cache/ + data/ from an existing install to skip the multi-hour first sync
deploy/install.sh
```

## Useful

```sh
journalctl -u tomato-streams -f                 # server log
journalctl -u tomato-streams-sync -n 50         # last sync summary
sudo systemctl start tomato-streams-sync        # sync now
systemctl list-timers tomato-streams-sync.timer
```
