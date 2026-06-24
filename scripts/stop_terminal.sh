#!/bin/bash
# Stop the SME Terminal services (live-data service + local dashboard).
export PATH="/Users/kshitizgarg/.nvm/versions/node/v22.9.0/bin:/usr/bin:/bin"
pkill -f "uvicorn smescanner.live.service" 2>/dev/null
lsof -ti:3030 2>/dev/null | xargs kill -9 2>/dev/null
osascript -e 'display notification "Live service & dashboard stopped." with title "SME Terminal"' 2>/dev/null
