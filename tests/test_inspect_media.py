import json
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
