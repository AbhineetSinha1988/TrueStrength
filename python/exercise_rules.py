"""
Exercise-Specific Form Rules
=============================
Biomechanical rules for Squats, Bench Press, and Deadlifts.

PHILOSOPHY:
This module emits ONLY raw biomechanical observations + measurements +
severity. It does NOT generate coaching cues — that's the LLM's job after
seeing the actual frames. Hardcoded cues lead to generic textbook responses.

Each finding contains:
  - issue:    short label of the biomechanical fault
  - detail:   measurement-based description (numbers, joints, frame indices)
  - severity: low | medium | high
  - frames:   list of frame indices most relevant to this finding (so the LLM
              can correlate visual evidence with the measurement)
"""

from __future__ import annotations


def _detected(frames: list[dict]) -> list[dict]:
    return [f for f in frames if f.get("pose_detected")]


def _frame_with_min(frames: list[dict], joint: str) -> int | None:
    """Return the frame_index where `joint` angle is at its minimum."""
    candidates = [f for f in _detected(frames) if joint in f.get("angles", {})]
    if not candidates:
        return None
    return min(candidates, key=lambda f: f["angles"][joint])["frame_index"]


def _frame_with_max(frames: list[dict], joint: str) -> int | None:
    candidates = [f for f in _detected(frames) if joint in f.get("angles", {})]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f["angles"][joint])["frame_index"]


# ──────────────────────────────────────────────────────────────────────────
#  SQUAT
# ──────────────────────────────────────────────────────────────────────────

def analyze_squat(angle_summary: dict, frames: list[dict]) -> dict:
    findings = []
    good = []

    detected_frames = _detected(frames)
    if not detected_frames:
        return {"exercise": "squat", "findings": ["Could not detect pose in video"], "good": []}

    bottom_frames = [f for f in detected_frames if f.get("phase") == "bottom"]
    summary = angle_summary

    # ── DEPTH ─────────────────────────────────────────────────────────────
    min_knee_l = summary.get("left_knee", {}).get("min", 180)
    min_knee_r = summary.get("right_knee", {}).get("min", 180)
    deepest_knee = min(min_knee_l, min_knee_r)
    deepest_frame = _frame_with_min(frames, "left_knee" if min_knee_l <= min_knee_r else "right_knee")

    if deepest_knee > 120:
        findings.append({
            "issue": "Insufficient depth",
            "detail": f"Minimum knee flexion only reaches {deepest_knee}° (frame {deepest_frame}). Below-parallel target is ≤100°. Range short by ~{round(deepest_knee - 100, 1)}°.",
            "severity": "high",
            "frames": [deepest_frame] if deepest_frame is not None else [],
        })
    elif deepest_knee > 100:
        findings.append({
            "issue": "Borderline depth",
            "detail": f"Minimum knee flexion {deepest_knee}° at frame {deepest_frame}. Just above the parallel threshold (~100°).",
            "severity": "medium",
            "frames": [deepest_frame] if deepest_frame is not None else [],
        })
    else:
        good.append(f"Depth reached — knee flexion {deepest_knee}° at frame {deepest_frame} (below parallel).")

    # ── KNEE ASYMMETRY AT BOTTOM ──────────────────────────────────────────
    if bottom_frames:
        bf = bottom_frames[0]
        a = bf["angles"]
        knee_diff = abs(a["left_knee"] - a["right_knee"])
        if knee_diff > 15:
            findings.append({
                "issue": "Asymmetric knee flexion at bottom",
                "detail": f"At frame {bf['frame_index']} (bottom): left knee {a['left_knee']}°, right knee {a['right_knee']}° → {knee_diff:.0f}° difference.",
                "severity": "medium",
                "frames": [bf["frame_index"]],
            })

    # ── TORSO LEAN ────────────────────────────────────────────────────────
    max_torso = summary.get("torso_lean", {}).get("max", 0)
    max_torso_frame = _frame_with_max(frames, "torso_lean")
    if max_torso > 55:
        findings.append({
            "issue": "Excessive forward torso lean",
            "detail": f"Torso reaches {max_torso}° from vertical at frame {max_torso_frame}. Threshold for back-loaded posture is ~45°.",
            "severity": "high",
            "frames": [max_torso_frame] if max_torso_frame is not None else [],
        })
    elif max_torso > 40:
        findings.append({
            "issue": "Moderate forward torso lean",
            "detail": f"Torso lean peaks at {max_torso}° (frame {max_torso_frame}). Acceptable for low-bar; high for high-bar squat.",
            "severity": "low",
            "frames": [max_torso_frame] if max_torso_frame is not None else [],
        })
    else:
        good.append(f"Torso stays relatively upright — peak lean {max_torso}°.")

    # ── HIP-RISE-FASTER-THAN-KNEE ─────────────────────────────────────────
    hip_range = summary.get("left_hip", {}).get("range", 0)
    knee_range = summary.get("left_knee", {}).get("range", 0)
    if knee_range > 0 and hip_range / knee_range > 1.4:
        findings.append({
            "issue": "Hip extension outpacing knee extension on the way up",
            "detail": f"Hip range {hip_range}° vs knee range {knee_range}° (ratio {hip_range/knee_range:.2f}). Indicates hips shooting up while torso pitches forward (good-morning pattern).",
            "severity": "high",
            "frames": [],
        })

    # ── RANGE OF MOTION ASYMMETRY ─────────────────────────────────────────
    knee_range_l = summary.get("left_knee", {}).get("range", 0)
    knee_range_r = summary.get("right_knee", {}).get("range", 0)
    if abs(knee_range_l - knee_range_r) > 20:
        findings.append({
            "issue": "Uneven knee range of motion between legs",
            "detail": f"Left knee ROM {knee_range_l}° vs right {knee_range_r}° → {abs(knee_range_l - knee_range_r):.0f}° gap.",
            "severity": "medium",
            "frames": [],
        })

    return {"exercise": "squat", "findings": findings, "good": good}


# ──────────────────────────────────────────────────────────────────────────
#  BENCH PRESS
# ──────────────────────────────────────────────────────────────────────────

def analyze_bench_press(angle_summary: dict, frames: list[dict]) -> dict:
    findings = []
    good = []

    detected_frames = _detected(frames)
    if not detected_frames:
        return {"exercise": "bench_press", "findings": ["Could not detect pose in video"], "good": []}

    summary = angle_summary
    bottom_frames = [f for f in detected_frames if f.get("phase") == "bottom"]

    # ── ELBOW FLEXION AT BOTTOM ───────────────────────────────────────────
    min_elbow_l = summary.get("left_elbow", {}).get("min", 180)
    min_elbow_r = summary.get("right_elbow", {}).get("min", 180)
    min_elbow = min(min_elbow_l, min_elbow_r)
    min_elbow_frame = _frame_with_min(frames, "left_elbow" if min_elbow_l <= min_elbow_r else "right_elbow")

    if min_elbow < 60:
        findings.append({
            "issue": "Excessive elbow flexion at bottom",
            "detail": f"Minimum elbow angle {min_elbow}° at frame {min_elbow_frame}. Below typical safe range (~70-90°).",
            "severity": "medium",
            "frames": [min_elbow_frame] if min_elbow_frame is not None else [],
        })
    elif min_elbow > 120:
        findings.append({
            "issue": "Insufficient ROM at bottom",
            "detail": f"Minimum elbow angle only {min_elbow}° (frame {min_elbow_frame}). Bar likely not reaching chest.",
            "severity": "high",
            "frames": [min_elbow_frame] if min_elbow_frame is not None else [],
        })
    else:
        good.append(f"Elbow flexion at bottom: {min_elbow}° (frame {min_elbow_frame}) — within target range.")

    # ── SHOULDER FLARE AT BOTTOM ──────────────────────────────────────────
    if bottom_frames:
        bf = bottom_frames[0]
        a = bf["angles"]
        avg_shoulder = (a["left_shoulder"] + a["right_shoulder"]) / 2
        if avg_shoulder > 90:
            findings.append({
                "issue": "Wide elbow flare",
                "detail": f"Shoulder abduction angle {avg_shoulder:.0f}° at frame {bf['frame_index']} (bottom). Above the 75° threshold associated with shoulder impingement risk.",
                "severity": "high",
                "frames": [bf["frame_index"]],
            })
        elif avg_shoulder < 30:
            findings.append({
                "issue": "Elbows tucked very tight",
                "detail": f"Shoulder abduction angle {avg_shoulder:.0f}° at frame {bf['frame_index']}. More triceps-dominant than pec.",
                "severity": "low",
                "frames": [bf["frame_index"]],
            })
        else:
            good.append(f"Elbow flare reasonable — shoulder angle {avg_shoulder:.0f}° at bottom.")

    # ── ASYMMETRY ─────────────────────────────────────────────────────────
    elbow_diff = abs(min_elbow_l - min_elbow_r)
    if elbow_diff > 15:
        findings.append({
            "issue": "Uneven arm flexion",
            "detail": f"Left elbow min {min_elbow_l}° vs right {min_elbow_r}° → {elbow_diff:.0f}° gap.",
            "severity": "medium",
            "frames": [],
        })

    # ── LOCKOUT ───────────────────────────────────────────────────────────
    max_elbow = max(summary.get("left_elbow", {}).get("max", 0), summary.get("right_elbow", {}).get("max", 0))
    if max_elbow < 160:
        findings.append({
            "issue": "Incomplete lockout",
            "detail": f"Maximum elbow extension only {max_elbow}°. Full lockout is 170-180°.",
            "severity": "low",
            "frames": [],
        })

    return {"exercise": "bench_press", "findings": findings, "good": good}


# ──────────────────────────────────────────────────────────────────────────
#  DEADLIFT
# ──────────────────────────────────────────────────────────────────────────

def analyze_deadlift(angle_summary: dict, frames: list[dict]) -> dict:
    findings = []
    good = []

    detected_frames = _detected(frames)
    if not detected_frames:
        return {"exercise": "deadlift", "findings": ["Could not detect pose in video"], "good": []}

    summary = angle_summary

    # ── HIP HINGE ─────────────────────────────────────────────────────────
    min_hip_l = summary.get("left_hip", {}).get("min", 180)
    min_hip_r = summary.get("right_hip", {}).get("min", 180)
    min_hip = min(min_hip_l, min_hip_r)
    min_hip_frame = _frame_with_min(frames, "left_hip" if min_hip_l <= min_hip_r else "right_hip")

    if min_hip > 130:
        findings.append({
            "issue": "Insufficient hip flexion at start",
            "detail": f"Minimum hip angle {min_hip}° at frame {min_hip_frame}. Hinge depth shallow — most load shifts to lumbar extensors.",
            "severity": "high",
            "frames": [min_hip_frame] if min_hip_frame is not None else [],
        })
    elif min_hip < 60:
        findings.append({
            "issue": "Hips very low at start",
            "detail": f"Minimum hip angle {min_hip}° at frame {min_hip_frame}. Position resembles a squat more than a hinge.",
            "severity": "medium",
            "frames": [min_hip_frame] if min_hip_frame is not None else [],
        })
    else:
        good.append(f"Hip hinge depth {min_hip}° at frame {min_hip_frame} — in expected range.")

    # ── LOCKOUT TORSO ─────────────────────────────────────────────────────
    min_torso = summary.get("torso_lean", {}).get("min", 0)
    min_torso_frame = _frame_with_min(frames, "torso_lean")
    if min_torso > 15:
        findings.append({
            "issue": "Incomplete lockout — torso not vertical at top",
            "detail": f"Minimum torso lean {min_torso}° from vertical (frame {min_torso_frame}). Should be ≤5° at full lockout.",
            "severity": "medium",
            "frames": [min_torso_frame] if min_torso_frame is not None else [],
        })
    else:
        good.append(f"Lockout torso vertical — minimum lean {min_torso}°.")

    # ── KNEE FLEXION ──────────────────────────────────────────────────────
    min_knee = min(summary.get("left_knee", {}).get("min", 180), summary.get("right_knee", {}).get("min", 180))
    if min_knee < 90:
        findings.append({
            "issue": "Excessive knee flexion at start",
            "detail": f"Minimum knee angle {min_knee}°. More knee bend than typical conventional setup (~110-130°).",
            "severity": "medium",
            "frames": [],
        })

    # ── HIP/KNEE LOCKOUT SEQUENCING ───────────────────────────────────────
    hip_range = summary.get("left_hip", {}).get("range", 0)
    knee_range = summary.get("left_knee", {}).get("range", 0)
    if knee_range > 0 and hip_range > 0:
        ratio = hip_range / knee_range
        if ratio < 0.5:
            findings.append({
                "issue": "Knees extending well before hips (hitching pattern)",
                "detail": f"Hip ROM {hip_range}° vs knee ROM {knee_range}° (ratio {ratio:.2f}). Knees lock first, then hips drag the torso up.",
                "severity": "high",
                "frames": [],
            })

    # ── HIP SYMMETRY ──────────────────────────────────────────────────────
    hip_diff = abs(min_hip_l - min_hip_r)
    if hip_diff > 15:
        findings.append({
            "issue": "Asymmetric hip position",
            "detail": f"Left hip min {min_hip_l}° vs right {min_hip_r}° → {hip_diff:.0f}° gap. Possible side shift.",
            "severity": "medium",
            "frames": [],
        })

    return {"exercise": "deadlift", "findings": findings, "good": good}


# ── Public API ────────────────────────────────────────────────────────────────

EXERCISE_ANALYZERS = {
    "squat": analyze_squat,
    "bench_press": analyze_bench_press,
    "bench": analyze_bench_press,
    "deadlift": analyze_deadlift,
}


def analyze_exercise(exercise_type: str, angle_summary: dict, frames: list[dict]) -> dict:
    """Run exercise-specific analysis. Returns findings dict (no canned cues)."""
    exercise_type = exercise_type.lower().replace(" ", "_")
    analyzer = EXERCISE_ANALYZERS.get(exercise_type)
    if not analyzer:
        return {
            "exercise": exercise_type,
            "error": f"Unknown exercise: {exercise_type}. Supported: {list(EXERCISE_ANALYZERS.keys())}",
        }
    return analyzer(angle_summary, frames)
