#!/usr/bin/env python3
"""
True Strength — Web Server
==========================
Mobile-first web interface over the same analysis pipeline the WhatsApp
plugin uses:

    upload video → ffmpeg frames → MediaPipe pose (33 landmarks)
    → joint angles + phase detection → biomechanical rules (observations only)
    → Claude sees the measurements AND the frames → coaching feedback

Run via ./web/run.sh (creates venv, installs deps, downloads pose model).
Requires ANTHROPIC_API_KEY for the coaching step; without it the endpoint
still returns measurements + findings, just no coach write-up.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_DIR = REPO_ROOT / "python"
STATIC_DIR = Path(__file__).resolve().parent / "static"
SOUL_PATH = REPO_ROOT / "config" / "SOUL.md"

DEFAULT_MODEL = os.environ.get("TRUESTRENGTH_MODEL", "claude-sonnet-5")
MAX_UPLOAD_MB = int(os.environ.get("TRUESTRENGTH_MAX_MB", "60"))
MAX_FRAMES = 8
EXERCISES = {"squat", "bench", "deadlift"}

app = FastAPI(title="True Strength")

# ── Claude system prompt ──────────────────────────────────────────────────
WEB_ADDENDUM = """

## Web Response Format (overrides any WhatsApp-specific instructions above)
You are replying inside the True Strength web app, not WhatsApp.
- Keep it under ~200 words. Short lines, generous line breaks.
- Structure: one-line verdict → 1-2 priority fixes (each tied to a frame/
  timestamp/measurement) → one thing they're doing well → one drill or cue
  to try next session.
- Plain text with simple emphasis only. No headers, no tables.
- Same cardinal rule: if the reply could be copy-pasted to any lifter doing
  this exercise, you've failed. Reference what YOU see in THESE frames.
"""


def load_system_prompt() -> str:
    if SOUL_PATH.exists():
        return SOUL_PATH.read_text(encoding="utf-8") + WEB_ADDENDUM
    return (
        "You are True Strength, a direct, specific, encouraging strength "
        "coach analyzing exercise videos. Ground every statement in the "
        "attached frames and measurements — never give generic textbook cues."
        + WEB_ADDENDUM
    )


# ── Pipeline invocation ───────────────────────────────────────────────────
def run_pipeline(video_path: str, exercise: str, frames_dir: str) -> dict:
    """Run python/formcheck.py in a subprocess and parse its JSON output."""
    cmd = [
        sys.executable,
        str(PYTHON_DIR / "formcheck.py"),
        video_path,
        exercise,
        "--max-frames",
        str(MAX_FRAMES),
        "--output-dir",
        frames_dir,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT)
    )
    if proc.returncode != 0:
        return {
            "error": "Analysis pipeline failed",
            "detail": (proc.stderr or proc.stdout or "")[-800:],
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "Pipeline returned invalid JSON", "detail": proc.stdout[-800:]}


# ── Prompt formatting (mirrors src/index.ts formatForLLM) ─────────────────
def format_for_llm(result: dict, exercise: str) -> str:
    analysis = result.get("analysis", {})
    angle_summary = result.get("angle_summary", {})
    video_info = result.get("video_info", {})
    frames = result.get("frames", [])

    out = f"## FormCheck Analysis — {exercise}\n\n"
    out += (
        f"**Video:** {video_info.get('analyzed_frames')} frames sampled "
        f"from {video_info.get('total_frames')} total"
    )
    if video_info.get("duration_seconds") is not None:
        out += (
            f" ({video_info['duration_seconds']}s @ "
            f"{round(video_info.get('fps') or 0)}fps)"
        )
    out += "\n\n### Per-Frame Observations\n"
    out += (
        "Each row corresponds to ONE attached image (in order). Use these to "
        "ground your feedback in the actual frames you can see.\n\n"
    )
    out += "| # | t (s) | phase | key angles |\n|---|-------|-------|------------|\n"
    for f in frames:
        idx = f.get("frame_index")
        ts = f.get("timestamp_seconds", "?")
        phase = f.get("phase")
        if not f.get("pose_detected"):
            out += f"| {idx} | {ts} | {phase} | _no pose detected_ |\n"
            continue
        a = f.get("angles", {})
        cells = []
        if exercise == "squat":
            cells.append(f"knee L/R: {a.get('left_knee')}°/{a.get('right_knee')}°")
            cells.append(f"hip L/R: {a.get('left_hip')}°/{a.get('right_hip')}°")
            cells.append(f"torso lean: {a.get('torso_lean')}°")
        elif exercise == "bench":
            cells.append(f"elbow L/R: {a.get('left_elbow')}°/{a.get('right_elbow')}°")
            cells.append(
                f"shoulder L/R: {a.get('left_shoulder')}°/{a.get('right_shoulder')}°"
            )
        elif exercise == "deadlift":
            cells.append(f"hip L/R: {a.get('left_hip')}°/{a.get('right_hip')}°")
            cells.append(f"knee L/R: {a.get('left_knee')}°/{a.get('right_knee')}°")
            cells.append(f"torso lean: {a.get('torso_lean')}°")
        out += f"| {idx} | {ts} | {phase} | {'; '.join(cells)} |\n"

    out += "\n### Angle Summary (across all frames)\n"
    for joint, data in angle_summary.items():
        out += (
            f"- **{joint}:** {data.get('min')}° → {data.get('max')}° "
            f"(range {data.get('range')}°)\n"
        )

    out += "\n### Biomechanical Findings\n"
    findings = analysis.get("findings") or []
    if findings:
        for f in findings:
            if isinstance(f, str):
                out += f"- {f}\n"
                continue
            out += f"- **[{(f.get('severity') or '').upper()}] {f.get('issue')}**\n"
            out += f"  {f.get('detail')}\n"
            if f.get("frames"):
                out += f"  See frame(s): {', '.join(map(str, f['frames']))}\n"
            out += "\n"
    else:
        out += "_No biomechanical issues detected from the rule layer._\n"

    good = analysis.get("good") or []
    if good:
        out += "\n### What the rules consider OK\n"
        for g in good:
            out += f"- {g}\n"

    out += """
---
**Instructions for you (the model):**
1. LOOK at the attached frames before writing anything. Reference what you actually see (bar position, foot placement, hand position, where the lifter looks, equipment, camera angle).
2. Use the per-frame table to know which timestamp/phase each image is from.
3. Combine visual observation + the measurements to write coaching feedback that is *specific to this lifter on this rep* — not generic textbook cues.
4. Quote concrete evidence: "at frame 3 (t=1.8s, bottom) your right knee tracks ~10° more than your left" — not "watch your knee tracking".
5. Skip any rule-finding that isn't visible/relevant in the frames. The rules are heuristic; trust your eyes when they conflict.
6. Keep it tight: 1-2 priority fixes max, written like a training partner who just watched the set."""
    return out


def coach_with_claude(summary: str, frame_images: list[bytes]) -> tuple[str | None, str | None]:
    """Send measurements + frames to Claude. Returns (feedback, error)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, "ANTHROPIC_API_KEY not set — returning measurements only."
    try:
        import anthropic

        client = anthropic.Anthropic()
        content: list[dict] = [{"type": "text", "text": summary}]
        for img in frame_images[:MAX_FRAMES]:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(img).decode(),
                    },
                }
            )
        msg = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=4000,  # headroom: newer models may spend tokens thinking before the reply
            system=load_system_prompt(),
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or None, None
    except Exception as e:  # surface, don't crash — measurements still useful
        return None, f"Claude call failed: {e}"


# ── Routes ────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model": DEFAULT_MODEL,
        "anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@app.post("/api/analyze")
async def analyze(video: UploadFile = File(...), exercise: str = Form(...)):
    exercise = exercise.strip().lower()
    if exercise not in EXERCISES:
        return JSONResponse(
            {"error": f"Unknown exercise '{exercise}'. Use squat, bench, or deadlift."}
        )

    workdir = tempfile.mkdtemp(prefix="truestrength-")
    try:
        # Save upload with a size cap
        suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
        video_path = os.path.join(workdir, f"upload{suffix}")
        size = 0
        with open(video_path, "wb") as out:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    return JSONResponse(
                        {"error": f"Video too large (max {MAX_UPLOAD_MB}MB). "
                                  "Trim to 5-15 seconds — 1-3 reps is ideal."}
                    )
                out.write(chunk)

        frames_dir = os.path.join(workdir, "frames")
        result = run_pipeline(video_path, exercise, frames_dir)
        if result.get("error"):
            return JSONResponse({"error": result["error"], "detail": result.get("detail")})

        # Collect frame images (for Claude + UI thumbnails)
        frame_images: list[bytes] = []
        ui_frames: list[dict] = []
        for f in result.get("frames", []):
            entry = {
                "index": f.get("frame_index"),
                "timestamp": f.get("timestamp_seconds"),
                "phase": f.get("phase"),
                "pose_detected": f.get("pose_detected"),
            }
            path = f.get("image_path")
            if path and os.path.exists(path):
                data = open(path, "rb").read()
                frame_images.append(data)
                entry["image"] = base64.b64encode(data).decode()
            ui_frames.append(entry)

        summary = format_for_llm(result, exercise)
        feedback, coach_error = coach_with_claude(summary, frame_images)

        return JSONResponse(
            {
                "feedback": feedback,
                "coach_error": coach_error,
                "model": DEFAULT_MODEL,
                "exercise": exercise,
                "video_info": result.get("video_info"),
                "frames": ui_frames,
                "findings": (result.get("analysis") or {}).get("findings", []),
                "good": (result.get("analysis") or {}).get("good", []),
                "angle_summary": result.get("angle_summary"),
            }
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
