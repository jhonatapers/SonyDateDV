import datetime as dt
import io
import json
import os
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gui
import run_gui
import sony_dv_date
from sony_dv_date import VideoError, ass_time, camera_date_text, camera_time_glyphs, extract_subtitles, probe, recording_date


def assert_date_only_command(test, command):
    test.assertEqual(command[command.index("-vf") + 1], "ass=datas.ass:fontsdir=fonts")
    test.assertEqual(command[command.index("-pix_fmt") + 1], "+")
    test.assertEqual(command[command.index("-c:a") + 1], "copy")


class PackagingTests(unittest.TestCase):
    def test_bundled_tools_are_first_on_path(self):
        with patch.object(run_gui.sys, "frozen", True, create=True), \
             patch.dict(os.environ, {"PATH": "original"}):
            run_gui.configure_bundled_tools()
            expected = str(Path(run_gui.__file__).resolve().parent / "bin")
            self.assertEqual(os.environ["PATH"], expected + os.pathsep + "original")

    def test_source_execution_does_not_change_path(self):
        with patch.object(run_gui.sys, "frozen", False, create=True), \
             patch.dict(os.environ, {"PATH": "original"}):
            run_gui.configure_bundled_tools()
            self.assertEqual(os.environ["PATH"], "original")


class ConsoleVisibilityTests(unittest.TestCase):
    def test_gui_hides_all_conversion_subprocesses(self):
        flags = 0x08000000
        app = gui.DVConverterApp.__new__(gui.DVConverterApp)
        app.root = Mock()
        app.progress_var = Mock()
        app.status_label = Mock()
        app.btn_convert = Mock()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.avi"
            source.touch()
            app.selected_files = [str(source)]
            app.output_dir = str(Path(directory) / "output")
            with patch.object(gui, "NO_CONSOLE", flags), \
                 patch.object(gui.shutil, "which", return_value="tool"), \
                 patch.object(gui, "probe", return_value=Fraction(25)) as probe_mock, \
                 patch.object(gui, "extract_subtitles", return_value=(1, 0)) as extract_mock, \
                 patch.object(gui.subprocess, "run") as run_mock:
                app.convert_files()
            self.assertEqual(probe_mock.call_args.kwargs["creationflags"], flags)
            self.assertEqual(extract_mock.call_args.kwargs["creationflags"], flags)
            self.assertEqual(run_mock.call_args.kwargs["creationflags"], flags)
            assert_date_only_command(self, run_mock.call_args.args[0])

    def test_cli_only_overlays_date(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.avi"
            source.touch()
            output = Path(directory) / "output.avi"
            with patch.object(sony_dv_date.sys, "argv", ["sony_dv_date.py", str(source), "-o", str(output)]), \
                 patch.object(sony_dv_date.shutil, "which", return_value="tool"), \
                 patch.object(sony_dv_date, "probe", return_value=Fraction(25)), \
                 patch.object(sony_dv_date, "extract_subtitles", return_value=(1, 0)), \
                 patch.object(sony_dv_date.subprocess, "run") as run_mock:
                self.assertEqual(sony_dv_date.main(), 0)
            assert_date_only_command(self, run_mock.call_args.args[0])

    def test_probe_passes_creation_flags(self):
        response = SimpleNamespace(stdout=json.dumps({"streams": [{
            "codec_name": "dvvideo", "r_frame_rate": "25", "avg_frame_rate": "25",
        }]}))
        with patch("sony_dv_date.subprocess.run", return_value=response) as run_mock:
            self.assertEqual(probe(Path("input.avi"), creationflags=123), Fraction(25))
        self.assertEqual(run_mock.call_args.kwargs["creationflags"], 123)


def frame_with(*packs):
    frame = bytearray(120000)
    for slot, pack in enumerate(packs):
        offset = 80 + 6 + slot * 8
        frame[offset : offset + 5] = bytes(pack)
    return bytes(frame)


class RecordingDateTests(unittest.TestCase):
    def test_reads_recording_date_and_time(self):
        frame = frame_with(
            (0x62, 0xFF, 0xD8, 0xE9, 0x26),
            (0x63, 0xFF, 0xA6, 0xD3, 0xD7),
        )
        self.assertEqual(recording_date(frame), dt.datetime(2026, 9, 18, 17, 53, 26))

    def test_missing_and_invalid_data_are_not_guessed(self):
        self.assertIsNone(recording_date(frame_with((0x62, 0xFF, 0xD8, 0xE9, 0x26))))
        self.assertIsNone(recording_date(frame_with(
            (0x62, 0xFF, 0xFF, 0xFF, 0xFF), (0x63, 0xFF, 0xFF, 0xFF, 0xFF)
        )))
        self.assertIsNone(recording_date(frame_with(
            (0x62, 0xFF, 0x1A, 0xE9, 0x26), (0x63, 0xFF, 0xA6, 0xD3, 0xD7)
        )))

    def test_year_boundary(self):
        frame = frame_with(
            (0x62, 0xFF, 0xC1, 0xE1, 0x99),
            (0x63, 0xFF, 0x80, 0x80, 0xC0),
        )
        self.assertEqual(recording_date(frame), dt.datetime(1999, 1, 1))

    def test_ass_boundaries_preserve_frame_alignment(self):
        fps = Fraction(30000, 1001)
        self.assertEqual(ass_time(30, fps), "0:00:01.00")
        self.assertEqual(ass_time(31, fps), "0:00:01.03")

    def test_camera_date_format_at_midnight_and_afternoon(self):
        afternoon = dt.datetime(2026, 10, 10, 15, 10, 42)
        midnight = dt.datetime(2000, 1, 1)
        self.assertEqual(camera_date_text(afternoon), "OCT 10 2026")
        self.assertEqual("".join(item[2] for item in camera_time_glyphs(afternoon)), "3:10:42PM")
        self.assertEqual(camera_date_text(midnight), "JAN 1 2000")
        self.assertEqual("".join(item[2] for item in camera_time_glyphs(midnight)), "12:00:00AM")

    def test_seconds_and_period_keep_fixed_positions(self):
        first = camera_time_glyphs(dt.datetime(2026, 10, 10, 15, 10, 41))
        second = camera_time_glyphs(dt.datetime(2026, 10, 10, 15, 10, 48))
        self.assertEqual([(x, size) for x, size, _ in first],
                         [(x, size) for x, size, _ in second])
        self.assertEqual(first[-2][0], 226)
        self.assertTrue(all(size == 38 for _, size, _ in first[:-1]))
        self.assertEqual(first[-1], (262, 26, "PM"))


class SubtitleTimingTests(unittest.TestCase):
    def test_packet_gaps_and_backward_dates_preserve_camera_metadata(self):
        first = frame_with((0x62, 0xFF, 0xE4, 0xE9, 0x26),
                           (0x63, 0xFF, 0x93, 0xC4, 0xE0))
        second = frame_with((0x62, 0xFF, 0xE5, 0xE9, 0x26),
                            (0x63, 0xFF, 0xA3, 0x92, 0xE0))
        empty = frame_with()
        process = SimpleNamespace(stdout=io.BytesIO(first + second + empty + first),
                                  wait=lambda: 0)

        def run_probe(command, **kwargs):
            if "-show_packets" in command:
                kwargs["stdout"].write("0\n12\n13\n14\n")
                return SimpleNamespace()
            return SimpleNamespace(stdout=json.dumps({
                "streams": [{"time_base": "1001/30000"}],
                "format": {"start_time": "0"},
            }))

        fps = Fraction(30000, 1001)
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "dates.ass"
            with patch("sony_dv_date.subprocess.run", side_effect=run_probe) as run_mock, \
                 patch("sony_dv_date.subprocess.Popen", return_value=process) as popen_mock:
                self.assertEqual(extract_subtitles(Path("input.avi"), fps, dest, creationflags=123), (4, 1))
            self.assertEqual([call.kwargs["creationflags"] for call in run_mock.call_args_list], [123, 123])
            self.assertEqual(popen_mock.call_args.kwargs["creationflags"], 123)
            dates = [line for line in dest.read_text(encoding="utf-8").splitlines()
                     if line.startswith("Dialogue:") and "SEP " in line]
        self.assertEqual(len(dates), 3)
        self.assertIn(f",{ass_time(0, fps)},{ass_time(12, fps)},", dates[0])
        self.assertTrue(dates[0].endswith("SEP 24 2026"))
        self.assertIn(f",{ass_time(12, fps)},{ass_time(13, fps)},", dates[1])
        self.assertTrue(dates[1].endswith("SEP 25 2026"))
        self.assertIn(f",{ass_time(14, fps)},{ass_time(15, fps)},", dates[2])
        self.assertTrue(dates[2].endswith("SEP 24 2026"))

    def test_missing_packet_timestamp_is_reported(self):
        frame = frame_with((0x62, 0xFF, 0xE4, 0xE9, 0x26),
                           (0x63, 0xFF, 0x93, 0xC4, 0xE0))
        process = SimpleNamespace(stdout=io.BytesIO(frame), wait=lambda: 0, kill=lambda: None)

        def run_probe(command, **kwargs):
            if "-show_packets" in command:
                return SimpleNamespace()
            return SimpleNamespace(stdout=json.dumps({
                "streams": [{"time_base": "1001/30000"}],
                "format": {"start_time": "0"},
            }))

        with tempfile.TemporaryDirectory() as directory:
            with patch("sony_dv_date.subprocess.run", side_effect=run_probe), \
                 patch("sony_dv_date.subprocess.Popen", return_value=process):
                with self.assertRaisesRegex(VideoError, "Timestamp"):
                    extract_subtitles(Path("input.avi"), Fraction(30000, 1001),
                                      Path(directory) / "dates.ass")


if __name__ == "__main__":
    unittest.main()
