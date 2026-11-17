#!/usr/bin/env python3
"""Inspect SRT/audio and emit an absolute, non-accumulating frame timeline."""

import argparse
import hashlib
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
CUE_ID = re.compile(r"\s*\d+\s*")
LONG_GAP_MS = 3000
MIN_CUE_DURATION_MS = 300


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


def read_srt(path, fps, warnings, *, min_cue_duration_ms=MIN_CUE_DURATION_MS,
             max_cps=None, source_bytes=None):
    content = path.read_bytes() if source_bytes is None else source_bytes
    raw = content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        raise ValueError("SRT is empty")
    blocks = re.split(r"\n[ \t]*\n+", raw.strip("\n"))
    cues, previous_start, covered_end, covered_end_frame, seen_ids = [], -1, 0, 0, set()
    cps_threshold = Fraction(str(max_cps)) if max_cps is not None else None
    for ordinal, block in enumerate(blocks, 1):
        lines = block.split("\n")
        if len(lines) < 2 or not CUE_ID.fullmatch(lines[0]):
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
        for identifier, timing in zip(lines[2:], lines[3:]):
            if CUE_ID.fullmatch(identifier) and TIMING.fullmatch(timing):
                raise ValueError(f"SRT block {ordinal}: missing blank line before cue {identifier.strip()}")
        text = "\n".join(lines[2:])
        non_whitespace_characters = sum(not character.isspace() for character in text)
        if not non_whitespace_characters:
            warning(warnings, "empty_text", "Subtitle has no visible text", ordinal)
        else:
            duration_ms = end - start
            if duration_ms < min_cue_duration_ms:
                warning(warnings, "short_duration",
                        f"Subtitle duration is {duration_ms} ms (below {min_cue_duration_ms} ms); inspect readability", ordinal)
            if cps_threshold is not None:
                cps = Fraction(non_whitespace_characters * 1000, duration_ms)
                if cps > cps_threshold:
                    warning(warnings, "high_cps",
                            f"Subtitle has {non_whitespace_characters} non-whitespace characters in {duration_ms} ms "
                            f"({float(cps):g} characters/s, above {float(cps_threshold):g}); inspect readability", ordinal)
        if start < covered_end:
            overlap_ms = min(end, covered_end) - start
            warning(warnings, "overlap", f"Subtitle overlaps earlier coverage by {overlap_ms / 1000:g} s", ordinal)
        elif start - covered_end > LONG_GAP_MS:
            warning(warnings, "long_gap", f"Gap before subtitle is {(start - covered_end) / 1000:g} seconds; confirm it is intentional", ordinal)
        start_frame = nearest_frame(start, fps)
        end_frame = max(start_frame + 1, nearest_frame(end, fps))
        if start_frame < covered_end_frame:
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
        covered_end_frame = max(covered_end_frame, end_frame)
    return cues


def audio_duration(path):
    if not path.is_file():
        raise ValueError(f"Audio file does not exist: {path}")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("ffprobe is required for --audio; install FFmpeg or omit --audio")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "stream=codec_type,duration,start_time:stream_tags=duration:stream_disposition=attached_pic:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise ValueError(f"ffprobe failed: {result.stderr.strip() or 'no diagnostic output'}")
    data = json.loads(result.stdout)
    streams = [s for s in data.get("streams", []) if s.get("codec_type") != "attachment"
               and not s.get("disposition", {}).get("attached_pic")]
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ValueError("Input has no audio stream")
    candidates = [audio.get("duration")]
    # Matroska's DURATION tag can be an end timestamp for tracks that start late.
    start_time = audio.get("start_time")
    zero_start = re.fullmatch(r"0+(?:\.0+)?", start_time or "")
    if zero_start:
        tags = {key.upper(): value for key, value in audio.get("tags", {}).items()}
        clock = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d(?:\.\d+)?)", tags.get("DURATION", ""))
        if clock:
            hours, minutes, seconds = clock.groups()
            candidates.append(int(hours) * 3600 + int(minutes) * 60 + Fraction(seconds))
    if len(streams) == 1 and (zero_start or start_time is None):
        candidates.append(data.get("format", {}).get("duration"))
    for candidate in candidates:
        try:
            duration = Fraction(str(candidate))
            if duration > 0:
                return duration
        except (ValueError, ZeroDivisionError):
            pass
    raise ValueError("ffprobe could not determine the first audio stream's duration; supply an extracted narration track")


def inspect_audio(path):
    if not path.is_file():
        raise ValueError(f"Audio file does not exist: {path}")

    def identity():
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    original = identity()

    def check_unchanged():
        try:
            unchanged = identity() == original
        except FileNotFoundError:
            unchanged = False
        if not unchanged:
            raise ValueError("Audio input changed during inspection; retry with a stable file")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    check_unchanged()
    # ffprobe opens the source independently. These checks catch ordinary edits
    # or replacements during hashing/probing without copying large media files;
    # inputs must remain stable during inspection, not be adversarially modified.
    try:
        duration = audio_duration(path)
    finally:
        check_unchanged()
    return duration, {"sha256": digest.hexdigest()}


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
    parser.add_argument("--min-cue-duration-ms", default=MIN_CUE_DURATION_MS, type=int,
                        help="Warn below this duration in original milliseconds (default: 300); 0 disables. Non-negative integer.")
    parser.add_argument("--max-cps", type=float,
                        help="Opt-in reading-speed warning above this positive, finite number of non-whitespace characters/second.")
    parser.add_argument("--output", type=Path, help="JSON path; defaults to stdout. Parent directory must exist.")
    args = parser.parse_args()
    try:
        fps = Fraction(args.fps)
        if fps <= 0:
            raise ValueError("--fps must be positive")
        if args.min_cue_duration_ms < 0:
            raise ValueError("--min-cue-duration-ms must be a non-negative integer (0 disables)")
        if args.max_cps is not None and (not math.isfinite(args.max_cps) or args.max_cps <= 0):
            raise ValueError("--max-cps must be a finite positive number; omit it to disable")
        srt_path = args.srt.resolve()
        audio_path = args.audio.resolve() if args.audio else None
        output_path = args.output.resolve() if args.output else None
        if output_path in (srt_path, audio_path) and output_path is not None:
            raise ValueError("--output must not overwrite an input file")
        warnings = []
        # Hash the exact bytes used for decoding, including BOM/newline choices.
        srt_bytes = srt_path.read_bytes()
        cues = read_srt(srt_path, fps, warnings, min_cue_duration_ms=args.min_cue_duration_ms,
                        max_cps=args.max_cps, source_bytes=srt_bytes)
        subtitle_duration = Fraction(max(c["endMs"] for c in cues), 1000)
        duration, audio_fingerprint = inspect_audio(audio_path) if audio_path else (None, None)
        if duration is not None:
            if subtitle_duration > duration:
                warning(warnings, "subtitle_past_audio", f"Last subtitle exceeds audio by {float(subtitle_duration - duration):.3f} seconds; verify inputs")
            elif duration - subtitle_duration > Fraction(LONG_GAP_MS, 1000):
                warning(warnings, "long_audio_tail", f"Audio continues {float(duration - subtitle_duration):.3f} seconds after the last subtitle; confirm it is intentional")
        minimum = max(math.ceil(max(subtitle_duration, duration or 0) * fps), max(c["endFrame"] for c in cues))
        data = {
            "schemaVersion": 1,
            "sources": {"srt": str(srt_path), "audio": str(audio_path) if audio_path else None},
            "sourceFingerprints": {
                "srt": {"sha256": hashlib.sha256(srt_bytes).hexdigest()},
                "audio": audio_fingerprint,
            },
            "fps": str(fps), "fpsValue": float(fps),
            "frameRounding": "absolute timestamp, nearest frame, half up; endFrame exclusive; at least one frame per cue",
            "subtitleDurationSeconds": float(subtitle_duration),
            "audioDurationSeconds": float(duration) if duration is not None else None,
            "minimumDurationFrames": minimum,
            "longGapThresholdSeconds": LONG_GAP_MS / 1000,
            "subtitleWarningThresholds": {
                "minCueDurationMs": args.min_cue_duration_ms, "maxCps": args.max_cps,
            },
            "cues": cues, "warnings": warnings,
        }
        write_json(data, output_path)
        return 0
    except (OSError, UnicodeError, ValueError, ZeroDivisionError, subprocess.TimeoutExpired) as error:
        print(f"inspect_media: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
