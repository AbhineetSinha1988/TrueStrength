#!/bin/bash
# True Strength — Public Tunnel Launcher
# Starts the web server (token-protected) + an ngrok tunnel, and prints the
# shareable URL. Use this to upload lift videos from anywhere (gym, mobile
# data) while the server runs on this machine.
#
# Requires: ngrok installed & authed (https://ngrok.com), ANTHROPIC_API_KEY set.
# Stop everything:  pkill -f "uvicorn server:app"; pkill -f "ngrok http"
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PORT="${TRUESTRENGTH_PORT:-8574}"

command -v ngrok >/dev/null 2>&1 || { echo "ngrok not found — brew install ngrok, then 'ngrok config add-authtoken ...'"; exit 1; }
[ -z "$ANTHROPIC_API_KEY" ] && echo "⚠  ANTHROPIC_API_KEY not set — coaching will be disabled."

# ── Access token (protects your Anthropic credits on the public URL) ──────
if [ -z "$TRUESTRENGTH_TOKEN" ]; then
    TRUESTRENGTH_TOKEN=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 20)
    echo "Generated access token (set TRUESTRENGTH_TOKEN to pin your own)."
fi
export TRUESTRENGTH_TOKEN

# ── venv (same as run.sh) ─────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "First run — creating venv + installing deps..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip -q install -r python/requirements.txt -r web/requirements.txt
MODEL="python/models/pose_landmarker_heavy.task"
if [ ! -f "$MODEL" ]; then
    mkdir -p python/models
    curl -sL -o "$MODEL" "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
fi

# ── Start server + tunnel ─────────────────────────────────────────────────
pkill -f "uvicorn server:app" 2>/dev/null || true
pkill -f "ngrok http" 2>/dev/null || true
sleep 1

nohup python -m uvicorn server:app --app-dir web --host 127.0.0.1 --port "$PORT" \
    > /tmp/truestrength-server.log 2>&1 &
nohup ngrok http "$PORT" --log /tmp/truestrength-ngrok.log > /dev/null 2>&1 &

echo "Waiting for tunnel..."
PUBLIC_URL=""
for i in $(seq 1 20); do
    sleep 1
    PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
        | python3 -c "import json,sys; ts=json.load(sys.stdin).get('tunnels',[]); print(next((t['public_url'] for t in ts if t['public_url'].startswith('https')), ''))" 2>/dev/null || true)
    [ -n "$PUBLIC_URL" ] && break
done
[ -z "$PUBLIC_URL" ] && { echo "Tunnel did not come up — check /tmp/truestrength-ngrok.log"; exit 1; }

echo ""
echo "========================================================"
echo "  TRUE STRENGTH is public:"
echo ""
echo "  Open on your phone:"
echo "    $PUBLIC_URL/?key=$TRUESTRENGTH_TOKEN"
echo ""
echo "  API (curl):"
echo "    curl -X POST '$PUBLIC_URL/api/upload?key=$TRUESTRENGTH_TOKEN' \\"
echo "         -F video=@lift.mp4 -F exercise=squat"
echo "    curl '$PUBLIC_URL/api/result/<job_id>?key=$TRUESTRENGTH_TOKEN'"
echo ""
echo "  Keep this Mac awake. Stop with:"
echo "    pkill -f 'uvicorn server:app'; pkill -f 'ngrok http'"
echo "========================================================"
