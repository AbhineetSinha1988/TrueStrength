#!/usr/bin/env python3
"""
FormCheck Video Analyzer
========================
Extracts frames from an exercise video, runs MediaPipe Pose Landmarker (Tasks API),
computes joint angles, and outputs structured pose data as JSON.

Usage:
    python analyze_video.py <video_path> [--max-frames 8] [--output-dir /tmp/formcheck]

Output:
    JSON to stdout with frame-by-frame pose landmarks and computed angles.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

# ── MediaPipe Pose Landmarker Setup (Tasks API) ──────────────────────────────

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Model path (relative to this script)
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "pose_landmarker_heavy.task")

# Key landmark indices (MediaPipe Pose has 33 landmarks)
LANDMARKS = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_elbow": 13,
    "right_elbow": 14,
    "left_wrist": 15,
    "right_wrist": 16,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_heel": 29,
    "right_heel": 30,
    "left_foot_index": 31,
    "right_foot_index": 32,
}


def calculate_angle(a: list, b: list, c: list) -> float:
    """Calculate angle at point b given three 3D points [x, y, z]."""
    a, b, c = np.array(a), np.array(b), np.array(c)
    ba = a - b
    bc = c - b
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def extract_frames(video_path: str, max_frames: int, output_dir: str) -> tuple:
    """Extract evenly-spaced frames from a video using OpenCV.

    Returns:
        (frame_paths, fps, total_frames, source_indices)
        where source_indices[i] is the original frame number in the source
        video that frame_paths[i] was sampled from. This lets us recover an
        accurate timestamp for each saved frame.
    """
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    if total_frames == 0:
        raise ValueError(f"Could not determine frame count for {video_path}")

    # Calculate which frames to extract (evenly spaced)
    n = min(max_frames, total_frames)
    indices = [int(i * (total_frames - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]

    frame_paths = []
    source_indices = []
    for idx, frame_num in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            path = os.path.join(output_dir, f"frame_{idx:03d}.jpg")
            cv2.imwrite(path, frame)
            frame_paths.append(path)
            source_indices.append(frame_num)

    cap.release()
    return frame_paths, fps, total_frames, source_indices


def analyze_frame(landmarker: PoseLandmarker, frame_path: str) -> dict | None:
    """Run MediaPipe Pose Landmarker on a single frame, return landmarks and angles."""
    image = cv2.imread(frame_path)
    if image is None:
        return None

    # Convert to MediaPipe Image
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    # Detect pose
    result = landmarker.detect(mp_image)

    if not result.pose_landmarks or len(result.pose_landmarks) == 0:
        return None

    pose_landmarks = result.pose_landmarks[0]  # First person detected

    # Extract key landmarks
    landmarks = {}
    for name, idx in LANDMARKS.items():
        lm = pose_landmarks[idx]
        landmarks[name] = {
            "x": round(lm.x, 4),
            "y": round(lm.y, 4),
            "z": round(lm.z, 4),
            "visibility": round(lm.visibility, 3),
        }

    # Helper to get [x, y, z] for angle calculation
    def pt(name):
        lm = landmarks[name]
        return [lm["x"], lm["y"], lm["z"]]

    # ── Compute Key Joint Angles ──────────────────────────────────────────

    angles = {}

    # Knee angles (critical for squats, deadlifts)
    angles["left_knee"] = calculate_angle(pt("left_hip"), pt("left_knee"), pt("left_ankle"))
    angles["right_knee"] = calculate_angle(pt("right_hip"), pt("right_knee"), pt("right_ankle"))

    # Hip angles (hip hinge for deadlifts, squat depth)
    angles["left_hip"] = calculate_angle(pt("left_shoulder"), pt("left_hip"), pt("left_knee"))
    angles["right_hip"] = calculate_angle(pt("right_shoulder"), pt("right_hip"), pt("right_knee"))

    # Elbow angles (critical for bench press)
    angles["left_elbow"] = calculate_angle(pt("left_shoulder"), pt("left_elbow"), pt("left_wrist"))
    angles["right_elbow"] = calculate_angle(pt("right_shoulder"), pt("right_elbow"), pt("right_wrist"))

    # Shoulder angles (bench press arm path, overhead position)
    angles["left_shoulder"] = calculate_angle(pt("left_hip"), pt("left_shoulder"), pt("left_elbow"))
    angles["right_shoulder"] = calculate_angle(pt("right_hip"), pt("right_shoulder"), pt("right_elbow"))

    # Torso lean (spine angle relative to vertical — key for squat/deadlift)
    mid_shoulder = [(pt("left_shoulder")[i] + pt("right_shoulder")[i]) / 2 for i in range(3)]
    mid_hip = [(pt("left_hip")[i] + pt("right_hip")[i]) / 2 for i in range(3)]
    vertical_ref = [mid_hip[0], mid_hip[1] - 1, mid_hip[2]]  # straight up from hip
    angles["torso_lean"] = calculate_angle(mid_shoulder, mid_hip, vertical_ref)

    # Knee-over-toe: horizontal distance (x-axis) between knee and ankle
    angles["left_knee_over_toe"] = round(landmarks["left_knee"]["x"] - landmarks["left_ankle"]["x"], 4)
    angles["right_knee_over_toe"] = round(landmarks["right_knee"]["x"] - landmarks["right_ankle"]["x"], 4)

    # Round all angle values
    angles = {k: round(v, 1) if isinstance(v, float) else v for k, v in angles.items()}

    return {
        "landmarks": landmarks,
        "angles": angles,
    }


def detect_exercise_phase(frames_data: list) -> list:
    """
    Rough phase detection based on knee/hip angles across frames.
    Returns a phase label for each frame.
    """
    phases = []
    for frame in frames_data:
        if frame is None:
            phases.append("unknown")
            continue

        avg_knee = (frame["angles"]["left_knee"] + frame["angles"]["right_knee"]) / 2
        avg_hip = (frame["angles"]["left_hip"] + frame["angles"]["right_hip"]) / 2

        if avg_knee < 100:
            phases.append("bottom")
        elif avg_knee < 140:
            phases.append("mid")
        else:
            phases.append("top")

    return phases


def create_landmarker() -> PoseLandmarker:
    """Create a PoseLandmarker instance with the heavy model."""
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Pose model not found at {MODEL_PATH}. "
            "Run setup.sh to download it, or manually download from: "
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
        )

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionRunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return PoseLandmarker.create_from_options(options)


def main():
    parser = argparse.ArgumentParser(description="Analyze exercise video for form correction")
    parser.add_argument("video_path", help="Path to the exercise video file")
    parser.add_argument("--max-frames", type=int, default=8, help="Max frames to extract")
    parser.add_argument("--output-dir", default="/tmp/formcheck", help="Temp directory for frames")
    args = parser.parse_args()

    if not os.path.exists(args.video_path):
        print(json.dumps({"error": f"Video not found: {args.video_path}"}))
        sys.exit(1)

    # Step 1: Extract frames
    try:
        frame_paths, fps, total_frames, _source_indices = extract_frames(
            args.video_path, args.max_frames, args.output_dir
        )
    except Exception as e:
        print(json.dumps({"error": f"Frame extraction failed: {str(e)}"}))
        sys.exit(1)

    if not frame_paths:
        print(json.dumps({"error": "No frames could be extracted from video"}))
        sys.exit(1)

    # Step 2: Run pose estimation on each frame
    frames_data = []
    landmarker = create_landmarker()
    for path in frame_paths:
        result = analyze_frame(landmarker, path)
        frames_data.append(result)
    landmarker.close()

    # Step 3: Detect movement phases
    phases = detect_exercise_phase(frames_data)

    # Step 4: Build output
    output = {
        "video_info": {
            "fps": fps,
            "total_frames": total_frames,
            "analyzed_frames": len(frame_paths),
            "frame_paths": frame_paths,
        },
        "frames": [],
    }

    for i, (data, phase) in enumerate(zip(frames_data, phases)):
        frame_entry = {
            "frame_index": i,
            "phase": phase,
            "pose_detected": data is not None,
        }
        if data:
            frame_entry["angles"] = data["angles"]
            frame_entry["landmarks"] = data["landmarks"]
        output["frames"].append(frame_entry)

    # Compute summary stats across frames where pose was detected
    detected = [f for f in output["frames"] if f["pose_detected"]]
    if detected:
        angle_keys = detected[0]["angles"].keys()
        summary = {}
        for key in angle_keys:
            vals = [f["angles"][key] for f in detected]
            summary[key] = {
                "min": round(min(vals), 1),
                "max": round(max(vals), 1),
                "range": round(max(vals) - min(vals), 1),
            }
        output["angle_summary"] = summary

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
