import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import inspect_media


class InspectMediaTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.srt = self.directory / "captions.srt"

    def inspect(self, text, *options):
        self.srt.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, inspect_media.__file__, "--srt", str(self.srt), *options],
            capture_output=True, text=True,
        )

    def test_missing_separator_keeps_existing_timeline(self):
        output = self.directory / "timeline.json"
        output.write_text("previous timeline", encoding="utf-8")
        result = self.inspect(
            "1\n00:00:00,000 --> 00:00:01,000\n甲\n"
            "2\n00:00:01,000 --> 00:00:02,000\n乙\n",
            "--output", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing blank line before cue 2", result.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "previous timeline")

    def test_numeric_text_and_fractional_frame_rate(self):
        result = self.inspect(
            "1\n00:00:00,050 --> 00:00:01,001\n42\n答案\n", "--fps", "30000/1001",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        timeline = json.loads(result.stdout)
        cue, = timeline["cues"]
        self.assertEqual(cue["text"], "42\n答案")
        self.assertEqual((cue["startFrame"], cue["endFrame"]), (1, 30))
        self.assertEqual(timeline["warnings"], [])

    def test_overlap_measures_only_shared_time(self):
        result = self.inspect(
            "1\n00:00:00,000 --> 00:00:10,000\n甲\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n乙\n\n"
            "3\n00:00:09,000 --> 00:00:12,000\n丙\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        warnings = json.loads(result.stdout)["warnings"]
        self.assertEqual([w["cueIndex"] for w in warnings], [2, 3])
        for warning in warnings:
            self.assertEqual(warning["code"], "overlap")
            self.assertEqual(warning["message"], "Subtitle overlaps earlier coverage by 1 s")

    def test_short_duration_uses_original_milliseconds_and_preserves_text(self):
        text = "  甲\t\n乙  "
        for duration, expected_codes in ((299, ["short_duration"]), (300, [])):
            with self.subTest(duration=duration):
                result = self.inspect(
                    f"1\n00:00:00,000 --> 00:00:00,{duration:03}\n{text}\n", "--fps", "1",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                timeline = json.loads(result.stdout)
                cue, = timeline["cues"]
                self.assertEqual(cue["text"], text)
                self.assertEqual((cue["startMs"], cue["endMs"]), (0, duration))
                self.assertEqual((cue["startFrame"], cue["endFrame"]), (0, 1))
                self.assertEqual([w["code"] for w in timeline["warnings"]], expected_codes)
                self.assertEqual(timeline["subtitleWarningThresholds"], {"minCueDurationMs": 300, "maxCps": None})

    def test_short_duration_threshold_can_be_changed_or_disabled(self):
        for threshold, expected_codes in ((500, ["short_duration"]), (300, []), (0, [])):
            with self.subTest(threshold=threshold):
                result = self.inspect(
                    "1\n00:00:00,000 --> 00:00:00,400\n甲\n",
                    "--min-cue-duration-ms", str(threshold),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                timeline = json.loads(result.stdout)
                self.assertEqual([w["code"] for w in timeline["warnings"]], expected_codes)
                self.assertEqual(timeline["subtitleWarningThresholds"]["minCueDurationMs"], threshold)
        result = self.inspect(
            "1\n00:00:00,000 --> 00:00:00,001\n甲\n", "--min-cue-duration-ms", "0",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["warnings"], [])

    def test_cps_is_opt_in_and_counts_non_whitespace_in_original_duration(self):
        text = " 甲乙\t丙 \n丁\u3000戊 "
        for options, expected_codes in (((), []), (("--max-cps", "25"), []),
                                        (("--max-cps", "24.9"), ["high_cps"])):
            with self.subTest(options=options):
                result = self.inspect(
                    f"1\n00:00:00,000 --> 00:00:00,200\n{text}\n",
                    "--fps", "1", "--min-cue-duration-ms", "0", *options,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                timeline = json.loads(result.stdout)
                self.assertEqual(timeline["cues"][0]["text"], text)
                self.assertEqual([w["code"] for w in timeline["warnings"]], expected_codes)
                if expected_codes:
                    warning, = timeline["warnings"]
                    self.assertEqual(warning["cueIndex"], 1)
                    self.assertIn("5 non-whitespace characters in 200 ms", warning["message"])

    def test_empty_text_retains_its_own_warning(self):
        result = self.inspect(
            "1\n00:00:00,000 --> 00:00:00,001\n \t\n", "--max-cps", "1",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        timeline = json.loads(result.stdout)
        self.assertEqual(timeline["cues"][0]["text"], " \t")
        self.assertEqual([w["code"] for w in timeline["warnings"]], ["empty_text"])

    def test_invalid_warning_thresholds_keep_existing_timeline(self):
        output = self.directory / "timeline.json"
        output.write_text("previous timeline", encoding="utf-8")
        cases = [("--min-cue-duration-ms", value) for value in ("-1", "0.5", "nan")]
        cases += [("--max-cps", value) for value in ("0", "-1", "nan", "inf", "1e1000")]
        for option, value in cases:
            with self.subTest(option=option, value=value):
                result = self.inspect(
                    "1\n00:00:00,000 --> 00:00:01,000\n甲\n",
                    option, value, "--output", str(output),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(option, result.stderr)
                self.assertEqual(output.read_text(encoding="utf-8"), "previous timeline")

    def test_srt_fingerprints_are_stable_and_follow_file_content(self):
        texts = ["\ufeff1\r\n00:00:00,000 --> 00:00:01,000\r\n甲\r\n"] * 2
        texts.append("1\n00:00:00,000 --> 00:00:01,000\n乙\n")
        fingerprints = []
        for text in texts:
            result = self.inspect(text)
            self.assertEqual(result.returncode, 0, result.stderr)
            timeline = json.loads(result.stdout)
            self.assertEqual(timeline["schemaVersion"], 1)
            self.assertEqual(timeline["sources"], {"srt": str(self.srt.resolve()), "audio": None})
            self.assertIsNone(timeline["sourceFingerprints"]["audio"])
            fingerprint = timeline["sourceFingerprints"]["srt"]["sha256"]
            self.assertEqual(fingerprint, hashlib.sha256(text.encode("utf-8")).hexdigest())
            fingerprints.append(fingerprint)
        self.assertEqual(fingerprints[0], fingerprints[1])
        self.assertNotEqual(fingerprints[0], fingerprints[2])

    def test_audio_fingerprints_are_stable_and_follow_file_content(self):
        self.srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n甲\n", encoding="utf-8")
        audio = self.directory / "narration.wav"
        output = self.directory / "timeline.json"
        argv = [inspect_media.__file__, "--srt", str(self.srt), "--audio", str(audio), "--output", str(output)]
        fingerprints = []
        for content in (b"first", b"first", b"other"):
            audio.write_bytes(content)
            with patch.object(sys, "argv", argv), patch.object(inspect_media, "audio_duration", return_value=1):
                self.assertEqual(inspect_media.main(), 0)
            timeline = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(timeline["sources"]["audio"], str(audio.resolve()))
            fingerprint = timeline["sourceFingerprints"]["audio"]["sha256"]
            self.assertEqual(fingerprint, hashlib.sha256(content).hexdigest())
            fingerprints.append(fingerprint)
        self.assertEqual(fingerprints[0], fingerprints[1])
        self.assertNotEqual(fingerprints[0], fingerprints[2])

    def test_audio_edit_during_probe_keeps_existing_timeline(self):
        self.srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n甲\n", encoding="utf-8")
        audio = self.directory / "narration.wav"
        audio.write_bytes(b"first")
        original_stat = audio.stat()
        output = self.directory / "timeline.json"
        output.write_text("previous timeline", encoding="utf-8")
        argv = [inspect_media.__file__, "--srt", str(self.srt), "--audio", str(audio), "--output", str(output)]

        def edit_during_probe(path):
            path.write_bytes(b"other")
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1))
            return 1

        with patch.object(sys, "argv", argv), \
                patch.object(inspect_media, "audio_duration", side_effect=edit_during_probe), \
                patch.object(sys, "stderr", new_callable=io.StringIO) as stderr:
            self.assertNotEqual(inspect_media.main(), 0)
        self.assertIn("changed during inspection; retry", stderr.getvalue())
        self.assertEqual(output.read_text(encoding="utf-8"), "previous timeline")

    def test_frame_rounding_overlap_uses_earlier_coverage(self):
        result = self.inspect(
            "1\n00:00:00,000 --> 00:00:00,001\n甲\n\n"
            "2\n00:00:00,001 --> 00:00:00,002\n乙\n\n"
            "3\n00:00:01,000 --> 00:00:01,001\n丙\n",
            "--fps", "1", "--min-cue-duration-ms", "0",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        warnings = json.loads(result.stdout)["warnings"]
        self.assertEqual([(w["code"], w["cueIndex"]) for w in warnings], [("frame_overlap", 2)])

    def duration_from_probe(self, streams):
        audio = self.directory / "narration"
        audio.touch()
        report = {"streams": streams, "format": {"duration": "6.000000"}}
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps(report))
        with patch.object(shutil, "which", return_value="ffprobe"), \
                patch.object(subprocess, "run", return_value=response):
            return inspect_media.audio_duration(audio)

    def test_container_fallback_for_standalone_audio_with_cover(self):
        cover = {"codec_type": "video", "disposition": {"attached_pic": 1}}
        self.assertEqual(self.duration_from_probe([cover, {"codec_type": "audio"}]), 6)

    def test_ambiguous_stream_duration_fails(self):
        for first_audio in (
            {"codec_type": "audio"},
            {"codec_type": "audio", "start_time": "2.000000", "tags": {"DURATION": "00:00:03"}},
        ):
            with self.subTest(stream=first_audio), self.assertRaisesRegex(ValueError, "first audio stream"):
                self.duration_from_probe([first_audio, {"codec_type": "audio", "duration": "6"}])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires FFmpeg")
    def test_real_two_track_audio_uses_first_track(self):
        audio = self.directory / "two-tracks.mka"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1",
             "-f", "lavfi", "-i", "sine=duration=6", "-map", "0:a", "-map", "1:a",
             "-c:a", "pcm_s16le", str(audio)], check=True,
        )
        result = self.inspect("1\n00:00:00,000 --> 00:00:02,000\n甲\n", "--audio", str(audio))
        self.assertEqual(result.returncode, 0, result.stderr)
        timeline = json.loads(result.stdout)
        self.assertEqual(timeline["audioDurationSeconds"], 1)
        self.assertEqual(timeline["minimumDurationFrames"], 60)
        self.assertEqual([w["code"] for w in timeline["warnings"]], ["subtitle_past_audio"])
