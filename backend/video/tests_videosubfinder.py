"""How the VideoSubFinder binary is delivered: the download group and the missing-binary error."""
import os
import stat
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "hardsub"))
from vid_under import views_download as vd  # noqa: E402
import vsf  # noqa: E402

BINARY_SHA256 = "2d9e4bc170408eee05326094b4fc89f0c79b017d7a3ba2e767801c8adb2e85fa"


class DownloadGroupTests(SimpleTestCase):
    def test_group_describes_the_binary(self):
        files = vd.MODEL_GROUPS["videosubfinder"]["files"]
        self.assertEqual(len(files), 1)
        f = files[0]
        self.assertEqual(f["size"], 47121988)
        self.assertEqual(f["sha256"], BINARY_SHA256)
        self.assertTrue(f["executable"])

    def test_it_lands_next_to_the_settings_the_program_reads(self):
        f = vd.MODEL_GROUPS["videosubfinder"]["files"][0]
        path = vd._file_path(f)
        backend = Path(__file__).resolve().parent.parent
        self.assertEqual(path, backend / "third_party" / "videosubfinder" / "linux" / "VideoSubFinderCli")
        self.assertTrue((path.parent / "settings" / "general.cfg").exists())
        self.assertTrue((path.parent / "VideoSubFinderCli.run").exists())

    def test_exec_bit_only_for_programs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            path.write_bytes(b"x")
            path.chmod(0o644)
            vd._apply_file_mode({"executable": False}, path)
            self.assertFalse(path.stat().st_mode & stat.S_IXUSR)
            vd._apply_file_mode({"executable": True}, path)
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR)


class MissingBinaryTests(SimpleTestCase):
    def test_error_says_where_to_get_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = vsf.VSF_DIR
            vsf.VSF_DIR = tmp
            try:
                with self.assertRaises(FileNotFoundError) as caught:
                    vsf.find_intervals("video.mp4", (0, 0, 10, 10), (100, 100))
            finally:
                vsf.VSF_DIR = original
        self.assertIn("videosubfinder", str(caught.exception))
