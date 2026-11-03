#!/usr/bin/env sh
# One command from real data to a phone app: ingest -> export snapshot -> single-file build.
# Run on a machine with internet access. Optional: export GEMINI_API_KEY=... first for AI research.
set -e
cd "$(dirname "$0")/.."
python -m finn.ingest
python scripts/export_snapshot.py
cd ../frontend
[ -d node_modules ] || npm ci
npm run build:demo
echo ""
echo "Done: frontend/dist-demo/index.html  (one file, real data, works on any phone)"
echo "Host it: send it to Claude to republish at your link, or put it on GitHub Pages."
