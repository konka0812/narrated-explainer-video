#!/usr/bin/env python3
"""Inspect SRT/audio and emit an absolute, non-accumulating frame timeline."""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


STAMP = r"(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})"
TIMING = re.compile(r"^\s*" + STAMP + r"\s*-->\s*" + STAMP + r"\s*$")
LONG_GAP_MS = 3000


def milliseconds(parts):
    hours, minutes, seconds, millis = map(int, parts)
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def nearest_frame(ms, fps):
    # Round half up, independently from absolute timestamps (never cumulative).
    frames = Fraction(ms, 1000) * fps
    return (frames.numerator * 2 + frames.denominator) // (2 * frames.denominator)


def warning(warnings, code, message, cue=None):
    item = {"code": code, "message": message}
    if cue is not None:
        item["cueIndex"] = cue
    warnings.append(item)


def read_srt(path, fps, warnings):
    raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        raise ValueError("SRT is empty")
    blocks = re.split(r"\n[ \t]*\n+", raw.strip("\n"))
    cues, previous_start, covered_end, seen_ids = [], -1, 0, set()
    for ordinal, block in enumerate(blocks, 1):
        lines = block.split("\n")
        if len(lines) < 2 or not re.fullmatch(r"\s*\d+\s*", lines[0]):
            raise ValueError(f"SRT block {ordinal}: expected a numeric cue identifier and timing line")
        match = TIMING.fullmatch(lines[1])
        if not match:
            raise ValueError(f"SRT block {ordinal}: invalid timing line {lines[1]!r}")
        start, end = milliseconds(match.groups()[:4]), milliseconds(match.groups()[4:])
        if end <= start:
            raise ValueError(f"SRT block {ordinal}: end time must be later than start time")
        if start < previous_start:
            raise ValueError(f"SRT block {ordinal}: cues are out of chronological order; input was not reordered")
        cue_id = int(lines[0].strip())
        if cue_id in seen_ids:
            warning(warnings, "duplicate_id", f"Repeated source cue identifier {cue_id}", ordinal)
        seen_ids.add(cue_id)
        text = "\n".join(lines[2:])
        if not text.strip():
            warning(warnings, "empty_text", "Subtitle has no visible text", ordinal)
        if start < covered_end:
            warning(warnings, "overlap", f"Subtitle overlaps earlier coverage by {(covered_end - start) / 1000:g} seconds", ordinal)
        elif start - covered_end > LONG_GAP_MS:
            warning(warnings, "long_gap", f"Gap before subtitle is {(start - covered_end) / 1000:g} seconds; confirm it is intentional", ordinal)
        start_frame = nearest_frame(start, fps)
        end_frame = max(start_frame + 1, nearest_frame(end, fps))
        if cues and start_frame < max(c["endFrame"] for c in cues):
            if start >= covered_end:
                warning(warnings, "frame_overlap", "Frame rounding creates an overlap; inspect this boundary", ordinal)
        cues.append({
            "index": ordinal, "sourceId": cue_id, "text": text,
            "startMs": start, "endMs": end,
            "startSeconds": start / 1000, "endSeconds": end / 1000,
            "startFrame": start_frame, "endFrame": end_frame,
            "durationFrames": end_frame - start_frame,
        })
        previous_start, covered_end = start, max(covered_end, end)
    return cues


def audio_duration(path):
    if not path.is_file():
        raise ValueError(f"Audio file does not exist: {path}")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("ffprobe is required for --audio; install FFmpeg or omit --audio")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=duration:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise ValueError(f"ffprobe failed: {result.stderr.strip() or 'no diagnostic output'}")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise ValueError("Input has no audio stream")
    for candidate in (streams[0].get("duration"), data.get("format", {}).get("duration")):
        try:
            duration = Fraction(str(candidate))
            if duration > 0:
                return duration
        except (ValueError, ZeroDivisionError):
            pass
    raise ValueError("ffprobe did not report a positive audio duration")


def write_json(data, output):
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        sys.stdout.write(payload)
        return
    # Build the whole result first, then atomically replace the output.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(payload)
        temp_path.replace(output)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srt", required=True, type=Path)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--fps", default="30", help="Positive frame rate, e.g. 30 or 30000/1001")
    parser.add_argument("--output", type=Path, help="JSON path; defaults to stdout. Parent directory must exist.")
    args = parser.parse_args()
    try:
        fps = Fraction(args.fps)
        if fps <= 0:
            raise ValueError("--fps must be positive")
        srt_path = args.srt.resolve()
        audio_path = args.audio.resolve() if args.audio else None
        output_path = args.output.resolve() if args.output else None
        if output_path in (srt_path, audio_path) and output_path is not None:
            raise ValueError("--output must not overwrite an input file")
        warnings = []
        cues = read_srt(srt_path, fps, warnings)
        subtitle_duration = Fraction(max(c["endMs"] for c in cues), 1000)
        duration = audio_duration(audio_path) if audio_path else None
        if duration is not None:
            if subtitle_duration > duration:
                warning(warnings, "subtitle_past_audio", f"Last subtitle exceeds audio by {float(subtitle_duration - duration):.3f} seconds; verify inputs")
            elif duration - subtitle_duration > Fraction(LONG_GAP_MS, 1000):
                warning(warnings, "long_audio_tail", f"Audio continues {float(duration - subtitle_duration):.3f} seconds after the last subtitle; confirm it is intentional")
        minimum = max(math.ceil(max(subtitle_duration, duration or 0) * fps), max(c["endFrame"] for c in cues))
        data = {
            "schemaVersion": 1,
            "sources": {"srt": str(srt_path), "audio": str(audio_path) if audio_path else None},
            "fps": str(fps), "fpsValue": float(fps),
            "frameRounding": "absolute timestamp, nearest frame, half up; endFrame exclusive; at least one frame per cue",
            "subtitleDurationSeconds": float(subtitle_duration),
            "audioDurationSeconds": float(duration) if duration is not None else None,
            "minimumDurationFrames": minimum,
            "longGapThresholdSeconds": LONG_GAP_MS / 1000,
            "cues": cues, "warnings": warnings,
        }
        write_json(data, output_path)
        return 0
    except (OSError, UnicodeError, ValueError, ZeroDivisionError, subprocess.TimeoutExpired) as error:
        print(f"inspect_media: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
