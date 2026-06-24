#!/bin/bash
# SME Terminal — one-click launcher.
# Starts the live-data service (XTS + news + bulk deals) and the local dashboard,
# then opens the browser. No terminal needed — launched by the Desktop app.

# Finder-launched apps get a minimal PATH, so set it explicitly.
export PATH="/Users/kshitizgarg/.nvm/versions/node/v22.9.0/bin:/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

ROOT="/Users/kshitizgarg/sentiment/sme-multibagger-scanner"
cd "$ROOT" || exit 1
mkdir -p data

# Stop any existing instances so we don't double-bind ports.
pkill -f "uvicorn smescanner.live.service" 2>/dev/null
lsof -ti:3030 2>/dev/null | xargs kill -9 2>/dev/null
sleep 1

# 1) Live-data service on :8088 (XTS quotes/depth/chart + NSE news + bulk deals)
PYTHONPATH=src nohup python3 -m uvicorn smescanner.live.service:app \
  --host 127.0.0.1 --port 8088 > data/live_service.log 2>&1 &

# 2) Local dashboard on :3030 (reads local Postgres, full live data)
nohup npm --prefix web run dev -- -p 3030 > data/dashboard.log 2>&1 &

# Wait for the dashboard to be ready (usually a few seconds), then open it.
for _ in $(seq 1 45); do
  curl -s -o /dev/null "http://localhost:3030" && break
  sleep 1
done
open "http://localhost:3030"
