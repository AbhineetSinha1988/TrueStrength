#!/bin/bash
# FormCheck Plugin — Setup Script
# Run this once to install all dependencies

set -e

echo "========================================="
echo "  FormCheck — Setup"
echo "========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── 1. Check system dependencies ──────────────────────────────────────────

echo ""
echo "[1/5] Checking system dependencies..."

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js not found. Install from https://nodejs.org/"
    exit 1
fi
echo "  ✓ Node.js $(node --version)"

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install from https://python.org/"
    exit 1
fi
echo "  ✓ Python $(python3 --version)"

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "  ⚠ ffmpeg not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "ERROR: ffmpeg not found and Homebrew not available."
        echo "Install ffmpeg: https://ffmpeg.org/download.html"
        exit 1
    fi
fi
echo "  ✓ ffmpeg $(ffmpeg -version 2>&1 | head -1)"

# Check ffprobe
if ! command -v ffprobe &> /dev/null; then
    echo "ERROR: ffprobe not found (should come with ffmpeg)"
    exit 1
fi
echo "  ✓ ffprobe available"

# ── 2. Install Python dependencies ───────────────────────────────────────

echo ""
echo "[2/5] Installing Python dependencies..."

cd "$SCRIPT_DIR"

# Create venv if it doesn't exist
if [ ! -d "python/.venv" ]; then
    python3 -m venv python/.venv
    echo "  ✓ Created Python virtual environment"
fi

source python/.venv/bin/activate
pip install -q -r python/requirements.txt
echo "  ✓ Installed MediaPipe, OpenCV, NumPy"
deactivate

# Download MediaPipe Pose model if not present
MODEL_DIR="$SCRIPT_DIR/python/models"
MODEL_FILE="$MODEL_DIR/pose_landmarker_heavy.task"
if [ ! -f "$MODEL_FILE" ]; then
    echo "  Downloading MediaPipe Pose Landmarker model (30MB)..."
    mkdir -p "$MODEL_DIR"
    curl -sL -o "$MODEL_FILE" \
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
    echo "  ✓ Downloaded pose model"
else
    echo "  ✓ Pose model already present"
fi

# ── 3. Install Node.js dependencies ─────────────────────────────────────

echo ""
echo "[3/5] Installing Node.js dependencies..."

npm install --silent
echo "  ✓ Installed Node.js dependencies"

# ── 4. Build TypeScript ──────────────────────────────────────────────────

echo ""
echo "[4/5] Building TypeScript plugin..."

npx tsc
echo "  ✓ Built to dist/"

# ── 5. Check OpenClaw ────────────────────────────────────────────────────

echo ""
echo "[5/5] Checking OpenClaw..."

if ! command -v openclaw &> /dev/null; then
    echo "  ⚠ OpenClaw CLI not found."
    echo "  Install: npm install -g openclaw"
    echo "  Or see: https://docs.openclaw.ai/installation"
    echo ""
    echo "  After installing OpenClaw, run:"
    echo "    openclaw plugins install $SCRIPT_DIR"
    echo "    openclaw channels add --channel whatsapp"
    echo ""
else
    echo "  ✓ OpenClaw $(openclaw --version 2>/dev/null || echo 'installed')"
    echo ""
    echo "  To install the plugin:"
    echo "    openclaw plugins install $SCRIPT_DIR"
fi

# ── Create temp directory ────────────────────────────────────────────────

mkdir -p /tmp/formcheck

# ── Done ─────────────────────────────────────────────────────────────────

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Update config/openclaw.json5 with your phone number"
echo "  2. Copy config to OpenClaw:"
echo "     cp config/openclaw.json5 ~/.openclaw/openclaw.json"
echo "     cp config/SOUL.md ~/.openclaw/SOUL.md"
echo "  3. Install plugin:"
echo "     openclaw plugins install $SCRIPT_DIR"
echo "  4. Connect WhatsApp:"
echo "     openclaw channels login --channel whatsapp"
echo "  5. Start the gateway:"
echo "     openclaw gateway"
echo ""
echo "Then send a squat/bench/deadlift video to your WhatsApp!"
