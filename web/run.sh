#!/bin/bash
# True Strength — Web App Launcher
# Creates a venv, installs deps, downloads the pose model, starts the server.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "========================================="
echo "  TRUE STRENGTH — web"
echo "========================================="

# ── Python venv + deps ────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[1/4] Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "[1/4] Using existing .venv"
fi
source .venv/bin/activate
echo "[2/4] Installing dependencies (first run can take a few minutes)..."
pip install -q --upgrade pip
pip install -q -r python/requirements.txt -r web/requirements.txt

# ── MediaPipe pose model ─────────────────────────────────────────────────
MODEL="python/models/pose_landmarker_heavy.task"
if [ ! -f "$MODEL" ]; then
    echo "[3/4] Downloading MediaPipe Pose Landmarker model (~30MB)..."
    mkdir -p python/models
    curl -sL -o "$MODEL" \
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
else
    echo "[3/4] Pose model present"
fi

# ── Preflight warnings ───────────────────────────────────────────────────
command -v ffmpeg >/dev/null 2>&1 || echo "⚠  ffmpeg not found — install it (brew install ffmpeg)"
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠  ANTHROPIC_API_KEY not set — analysis will run, but Claude coaching will be disabled."
    echo "   export ANTHROPIC_API_KEY=sk-ant-..."
fi

# ── Launch ───────────────────────────────────────────────────────────────
PORT="${TRUESTRENGTH_PORT:-8574}"
IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "[4/4] Starting server"
echo ""
echo "  On this machine:  http://localhost:$PORT"
echo "  On your phone:    http://$IP:$PORT   (same Wi-Fi network)"
echo ""
exec python -m uvicorn server:app --app-dir web --host 0.0.0.0 --port "$PORT"
