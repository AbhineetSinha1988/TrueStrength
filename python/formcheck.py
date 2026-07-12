#!/usr/bin/env python3
"""
FormCheck — Main Entry Point
=============================
Combines video analysis (MediaPipe) + exercise rules to produce
structured form corrections. Called by the OpenClaw plugin.

Usage:
    python formcheck.py <video_path> <exercise_type> [--max-frames 8]

Output:
    JSON with per-frame timestamped pose data + exercise-specific findings.
"""

import argparse
import json
import sys

from analyze_video import extract_frames, analyze_frame, detect_exercise_phase, create_landmarker
from exercise_rules import analyze_exercise


def run(video_path: str, exercise_type: str, max_frames: int = 8, output_dir: str = "/tmp/formcheck"):
    """Full pipeline: extract → pose estimate → rule check → output."""

    # Step 1: Extract frames (now also returns the source frame index for each saved frame)
    try:
        frame_paths, fps, total_frames, source_indices = extract_frames(
            video_path, max_frames, output_dir
        )
    except Exception as e:
        return {"error": f"Frame extraction failed: {str(e)}"}

    if not frame_paths:
        return {"error": "No frames could be extracted from video"}

    # Step 2: Pose estimation
    frames_data = []
    landmarker = create_landmarker()
    for path in frame_paths:
        result = analyze_frame(landmarker, path)
        frames_data.append(result)
    landmarker.close()

    # Step 3: Phase detection
    phases = detect_exercise_phase(frames_data)

    # Build per-frame results with timestamps + frame paths
    frames = []
    for i, (data, phase, src_idx, path) in enumerate(
        zip(frames_data, phases, source_indices, frame_paths)
    ):
        timestamp = round(src_idx / fps, 2) if fps and fps > 0 else None
        entry = {
            "frame_index": i,
            "source_frame": src_idx,
            "timestamp_seconds": timestamp,
            "phase": phase,
            "pose_detected": data is not None,
            "image_path": path,
        }
        if data:
            entry["angles"] = data["angles"]
        frames.append(entry)

    # Step 4: Compute angle summary
    detected = [f for f in frames if f["pose_detected"]]
    if not detected:
        return {"error": "Could not detect pose in any frame. Ensure the full body is visible in the video."}

    angle_keys = detected[0]["angles"].keys()
    angle_summary = {}
    for key in angle_keys:
        vals = [f["angles"][key] for f in detected]
        angle_summary[key] = {
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "range": round(max(vals) - min(vals), 1),
        }

    # Step 5: Exercise-specific rule analysis
    exercise_result = analyze_exercise(exercise_type, angle_summary, frames)

    # Step 6: Assemble output
    duration = round(total_frames / fps, 2) if fps and fps > 0 else None
    output = {
        "video_info": {
            "fps": fps,
            "total_frames": total_frames,
            "duration_seconds": duration,
            "analyzed_frames": len(frame_paths),
        },
        "exercise_type": exercise_type,
        "angle_summary": angle_summary,
        "frames": frames,
        "analysis": exercise_result,
    }

    return output


def main():
    parser = argparse.ArgumentParser(description="FormCheck: Exercise form analyzer")
    parser.add_argument("video_path", help="Path to exercise video")
    parser.add_argument("exercise_type", choices=["squat", "bench", "bench_press", "deadlift"],
                        help="Type of exercise")
    parser.add_argument("--max-frames", type=int, default=8, help="Max frames to analyze")
    parser.add_argument("--output-dir", default="/tmp/formcheck", help="Temp dir for frames")
    args = parser.parse_args()

    result = run(args.video_path, args.exercise_type, args.max_frames, args.output_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
