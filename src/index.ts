/**
 * FormCheck — OpenClaw Plugin Entry Point
 * ========================================
 * Registers the `analyze_exercise_form` tool that:
 * 1. Takes a video file path + exercise type
 * 2. Runs the Python MediaPipe pipeline
 * 3. Returns structured pose data + the actual frame images so the LLM can
 *    SEE the lift, not just read measurements
 * 4. The LLM generates corrections grounded in what it observes in the frames
 *    + the biomechanical measurements
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "@sinclair/typebox";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PYTHON_DIR = resolve(__dirname, "..", "python");

export default definePluginEntry({
  id: "formcheck",
  name: "FormCheck — Exercise Form Analyzer",
  description:
    "Analyzes exercise videos for technique corrections using MediaPipe pose estimation. Supports squats, bench press, and deadlifts.",

  register(api) {
    // ── Main tool: analyze_exercise_form ──────────────────────────────────
    api.registerTool({
      name: "analyze_exercise_form",
      description: `Analyze an exercise video for form/technique corrections.

Takes a video file path and exercise type. Runs MediaPipe pose estimation,
computes per-frame joint angles, samples key frames from the video, and
returns BOTH:
  - Structured per-frame measurements + biomechanical findings
  - The actual sampled frame images (so the model can visually verify)

The model is expected to look at the frames AND the measurements together
to produce specific, individualized form feedback — not generic textbook cues.

Supported exercises: squat, bench (bench press), deadlift`,

      parameters: Type.Object({
        video_path: Type.String({
          description: "Absolute path to the exercise video file",
        }),
        exercise_type: Type.Union(
          [
            Type.Literal("squat"),
            Type.Literal("bench"),
            Type.Literal("deadlift"),
          ],
          {
            description:
              "Type of exercise being performed: squat, bench, or deadlift",
          }
        ),
        max_frames: Type.Optional(
          Type.Number({
            description: "Maximum frames to extract for analysis (default: 8)",
            default: 8,
            minimum: 3,
            maximum: 16,
          })
        ),
      }),

      async execute(_id, params) {
        const { video_path, exercise_type, max_frames = 8 } = params;

        // Validate video exists
        if (!existsSync(video_path)) {
          return {
            content: [
              {
                type: "text" as const,
                text: JSON.stringify({
                  error: `Video file not found: ${video_path}`,
                  hint: "The video may still be downloading. Check the media path from the message.",
                }),
              },
            ],
          };
        }

        try {
          // Use the venv Python (has MediaPipe installed)
          const venvPython = resolve(PYTHON_DIR, ".venv", "bin", "python3");
          const pythonPath = existsSync(venvPython) ? venvPython : "python3";
          const scriptPath = resolve(PYTHON_DIR, "formcheck.py");

          const { stdout, stderr } = await execFileAsync(
            pythonPath,
            [
              scriptPath,
              video_path,
              exercise_type,
              "--max-frames",
              String(max_frames),
            ],
            {
              timeout: 90_000, // 90s — heavy MediaPipe model can take ~30s
              maxBuffer: 20 * 1024 * 1024, // 20MB buffer
            }
          );

          if (stderr) {
            console.error("[formcheck] stderr:", stderr);
          }

          const result = JSON.parse(stdout);

          if (result.error) {
            return {
              content: [
                { type: "text" as const, text: JSON.stringify(result) },
              ],
            };
          }

          // Build text summary
          const textSummary = formatForLLM(result, exercise_type);

          // Build image content blocks — one per analyzed frame
          const imageBlocks: Array<{
            type: "image";
            data: string;
            mimeType: string;
          }> = [];
          const frames: any[] = result.frames ?? [];
          for (const f of frames) {
            const path = f.image_path;
            if (!path || !existsSync(path)) continue;
            try {
              const buf = readFileSync(path);
              imageBlocks.push({
                type: "image",
                data: buf.toString("base64"),
                mimeType: "image/jpeg",
              });
            } catch (e) {
              console.error(
                `[formcheck] failed to read frame ${path}:`,
                (e as Error).message
              );
            }
          }

          return {
            content: [
              { type: "text" as const, text: textSummary },
              ...imageBlocks,
            ],
          };
        } catch (err: any) {
          return {
            content: [
              {
                type: "text" as const,
                text: JSON.stringify({
                  error: "Analysis failed",
                  detail: err.message,
                  hint: "Ensure Python 3, MediaPipe, and ffmpeg are installed. Run: pip install -r python/requirements.txt",
                }),
              },
            ],
          };
        }
      },
    });
  },
});

/**
 * Format the raw analysis into a structured prompt for the LLM.
 * The model also receives the frame images as image content blocks AFTER
 * this text — they appear in the same order as the per-frame table below,
 * so frame_index 0 is the first image, frame_index 1 the second, etc.
 */
function formatForLLM(result: any, exerciseType: string): string {
  const { analysis, angle_summary, video_info, frames } = result;

  let out = `## FormCheck Analysis — ${exerciseType}\n\n`;
  out += `**Video:** ${video_info.analyzed_frames} frames sampled from ${video_info.total_frames} total`;
  if (video_info.duration_seconds != null) {
    out += ` (${video_info.duration_seconds}s @ ${Math.round(
      video_info.fps ?? 0
    )}fps)`;
  }
  out += `\n\n`;

  // ── Per-frame table — this is what makes feedback specific ─────────────
  out += `### Per-Frame Observations\n`;
  out += `Each row corresponds to ONE attached image (in order). Use these to ground your feedback in the actual frames you can see.\n\n`;
  out += `| # | t (s) | phase | key angles |\n`;
  out += `|---|-------|-------|------------|\n`;
  for (const f of frames as any[]) {
    if (!f.pose_detected) {
      out += `| ${f.frame_index} | ${f.timestamp_seconds ?? "?"} | ${f.phase} | _no pose detected_ |\n`;
      continue;
    }
    const a = f.angles;
    const cells: string[] = [];
    if (exerciseType === "squat") {
      cells.push(`knee L/R: ${a.left_knee}°/${a.right_knee}°`);
      cells.push(`hip L/R: ${a.left_hip}°/${a.right_hip}°`);
      cells.push(`torso lean: ${a.torso_lean}°`);
    } else if (exerciseType === "bench") {
      cells.push(`elbow L/R: ${a.left_elbow}°/${a.right_elbow}°`);
      cells.push(`shoulder L/R: ${a.left_shoulder}°/${a.right_shoulder}°`);
    } else if (exerciseType === "deadlift") {
      cells.push(`hip L/R: ${a.left_hip}°/${a.right_hip}°`);
      cells.push(`knee L/R: ${a.left_knee}°/${a.right_knee}°`);
      cells.push(`torso lean: ${a.torso_lean}°`);
    }
    out += `| ${f.frame_index} | ${f.timestamp_seconds ?? "?"} | ${f.phase} | ${cells.join("; ")} |\n`;
  }
  out += `\n`;

  // ── Aggregate angle summary ────────────────────────────────────────────
  out += `### Angle Summary (across all frames)\n`;
  for (const [joint, data] of Object.entries(angle_summary) as any) {
    out += `- **${joint}:** ${data.min}° → ${data.max}° (range ${data.range}°)\n`;
  }
  out += `\n`;

  // ── Findings (no canned cues — measurements only) ──────────────────────
  out += `### Biomechanical Findings\n`;
  if (analysis.findings && analysis.findings.length > 0) {
    for (const f of analysis.findings) {
      if (typeof f === "string") {
        out += `- ${f}\n`;
        continue;
      }
      out += `- **[${(f.severity ?? "").toUpperCase()}] ${f.issue}**\n`;
      out += `  ${f.detail}\n`;
      if (Array.isArray(f.frames) && f.frames.length > 0) {
        out += `  See frame(s): ${f.frames.join(", ")}\n`;
      }
      out += `\n`;
    }
  } else {
    out += `_No biomechanical issues detected from the rule layer._\n`;
  }

  if (analysis.good && analysis.good.length > 0) {
    out += `\n### What the rules consider OK\n`;
    for (const g of analysis.good) {
      out += `- ${g}\n`;
    }
  }

  out += `\n---
**Instructions for you (the model):**
1. LOOK at the attached frames before writing anything. Reference what you actually see (bar position, foot placement, hand position, where the lifter looks, equipment, camera angle).
2. Use the per-frame table to know which timestamp/phase each image is from.
3. Combine visual observation + the measurements to write coaching feedback that is *specific to this lifter on this rep* — not generic textbook cues.
4. Quote concrete evidence: "at frame 3 (t=1.8s, bottom) your right knee tracks ~10° more than your left" — not "watch your knee tracking".
5. Skip any rule-finding that isn't visible/relevant in the frames. The rules are heuristic; trust your eyes when they conflict.
6. Keep the WhatsApp reply tight: 1-2 priority fixes max, written like a training partner who just watched the set.`;

  return out;
}
