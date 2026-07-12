# True Strength

**Send your lift. Get coached.**

True Strength watches a video of your **squat, bench press, or deadlift** and coaches you back like a training partner who never misses a frame — specific, measured, and grounded in *your* rep, not textbook cues.

Two interfaces, one pipeline:

- **WhatsApp agent** — send a video to your linked WhatsApp, get corrections back in chat (built as an [OpenClaw](https://openclaw.ai/) plugin)
- **Web app (mobile-first)** — record/upload in the browser, see the coaching plus the exact frames Claude watched, the biomechanical findings, and every measured joint angle

## How it works

```
your video
  → ffmpeg samples up to 8 key frames
  → MediaPipe Pose Landmarker (33 landmarks per frame)
  → joint angles + movement-phase detection (top / mid / bottom)
  → biomechanical rules emit OBSERVATIONS with severity + frame refs
      (deliberately: measurements only — never coaching cues)
  → Claude receives the measurement table AND the actual frame images
  → Claude writes the coaching — required to cite a specific frame,
      timestamp, or measurement, and to overrule the heuristics
      when the frames contradict them ("trust your eyes")
```

**The cardinal design rule** (from [`config/SOUL.md`](config/SOUL.md)):

> *If your reply could be copy-pasted to any lifter doing the same exercise, you've failed.*

That's why the deterministic layer is forbidden from writing cues: hardcoded cues produce generic responses. The measurement spine keeps Claude honest; Claude's multimodal reasoning makes the feedback human.

## What it checks

| Exercise | What It Checks |
|----------|---------------|
| **Squat** | Depth, knee tracking, forward lean, hip rise, symmetry |
| **Bench Press** | Range of motion, elbow flare/tuck, lockout, symmetry |
| **Deadlift** | Hip hinge, back angle, lockout, knee bend, hitching |

---

## Quick start — Web app

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # coaching runs on Claude
./web/run.sh
```

First run creates a venv, installs deps, and downloads the pose model (~30MB). Then open `http://localhost:8574` — or the LAN URL it prints — on your phone (same Wi-Fi), pick your lift, record or upload a 5–15s clip, and get coached.

- Model: `claude-sonnet-5` by default; override with `TRUESTRENGTH_MODEL`
- Port: `8574`; override with `TRUESTRENGTH_PORT`
- Videos are analyzed in a temp dir and deleted after the response

### Upload from anywhere (public URL)

```bash
./web/tunnel.sh   # requires ngrok (authed); prints https://xxxx.ngrok…/?key=TOKEN
```

Starts the server behind an [ngrok](https://ngrok.com) tunnel with a generated access token — open the printed URL on your phone at the gym and upload over mobile data. Every `/api/*` call must carry the token (`?key=` or `X-API-Key`), so the public URL can't be used to spend your Anthropic credits without it. Pin your own token via `TRUESTRENGTH_TOKEN`.

### API

| Endpoint | What it does |
|---|---|
| `POST /api/upload` | multipart `video` + `exercise` (squat/bench/deadlift) → `{job_id}` immediately; analysis runs in the background |
| `GET /api/result/{job_id}` | `{status: processing}` → full result when done (feedback, frames, findings, angles) |
| `POST /api/analyze` | same input, synchronous — blocks until the full result (simplest for scripts) |
| `GET /api/health` | server status, model, whether auth is on |

```bash
# one-shot from a script
curl -X POST http://localhost:8574/api/analyze -F video=@squat.mp4 -F exercise=squat

# upload-then-poll (what the UI does — survives flaky mobile connections)
curl -X POST http://localhost:8574/api/upload -F video=@squat.mp4 -F exercise=squat
curl http://localhost:8574/api/result/<job_id>
```

## Quick start — WhatsApp agent

Requires [OpenClaw](https://docs.openclaw.ai/installation) and an Anthropic API key.

```bash
# 1. Install Python + Node deps, build the plugin
./setup.sh

# 2. Put YOUR phone number in config/openclaw.json5, then:
cp config/openclaw.json5 ~/.openclaw/openclaw.json
cp config/SOUL.md ~/.openclaw/SOUL.md

# 3. Install the plugin + connect WhatsApp
openclaw plugins install .
openclaw channels login --channel whatsapp

# 4. Run
openclaw gateway
```

Send a video to your own WhatsApp ("Note to Self") with *"check my squat"*. The config ships with `selfChatMode: true` and an allowlist so the bot only ever replies to **you**.

## Project structure

```
TrueStrength/
├── python/                # shared analysis pipeline
│   ├── formcheck.py       #   video → pose → rules → JSON
│   ├── analyze_video.py   #   frame extraction + MediaPipe pose
│   └── exercise_rules.py  #   biomechanics rules (observations only, no cues)
├── web/                   # mobile-first web app
│   ├── server.py          #   FastAPI: /api/analyze → pipeline → Claude
│   ├── static/index.html  #   upload UI (self-contained, no build step)
│   └── run.sh             #   one-command launcher
├── src/index.ts           # OpenClaw plugin — registers analyze_exercise_form
├── config/
│   ├── SOUL.md            # the coach's persona + the anti-generic rule
│   └── openclaw.json5     # WhatsApp channel config (template)
├── docs/                  # diagrams
└── setup.sh               # WhatsApp-plugin setup
```

## Testing the pipeline directly

```bash
source .venv/bin/activate
python python/formcheck.py /path/to/squat.mp4 squat
# → JSON: per-frame angles, phases, findings
```

## Filming tips

- Side angle (sagittal plane) for squat and deadlift; front or 45° for bench
- Full body visible, steady phone, decent lighting
- 5–15 second clips (1–3 reps) work best; one person in frame

## Known limitations

- Single lifter in frame only; camera angle materially affects accuracy
- MediaPipe struggles with very baggy clothing
- No barbell-path tracking yet (pose only)
- Big 3 lifts only — deliberately

## Roadmap

- Annotated frames (skeleton + angle overlays) in responses
- Rep counting and per-rep breakdown
- Progress tracking across sessions
- More lifts: overhead press, rows, pull-ups
- Cost-optimised model routing (the blocker for opening a public beta)

---

Built with [Claude Code](https://claude.com/claude-code) · pose estimation by [MediaPipe](https://developers.google.com/mediapipe) · coached by Claude
