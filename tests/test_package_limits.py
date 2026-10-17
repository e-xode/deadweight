"""The plugin directory's file limits, held by the tests and not only by the case exporter.

    python3 -m unittest tests.test_package_limits

Anthropic's plugin pre-submission checklist (read 2026-10-17), "Files in the plugin folder":
"Keep every file that isn't an image or font under 256 KiB" and "Keep the plugin to 512 files or
fewer", each "Held for a reviewer". `cases/*.json` is cut under that size by the maintainer's
exporter, but a contributed `cases.d/*.json` was bounded by nothing (external audit of 0.27.0,
D-05). This repository is the plugin folder: `.claude-plugin/plugin.json` is at its root.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 512


class CaseFiles(unittest.TestCase):
    def test_every_case_file_is_under_256_kib(self) -> None:
        files = sorted((ROOT / "tests" / "cases").glob("*.json")) + sorted((ROOT / "tests" / "cases.d").glob("*.json"))
        self.assertTrue(files, "no case file found")
        for f in files:
            with self.subTest(file=f.relative_to(ROOT).as_posix()):
                self.assertLess(f.stat().st_size, MAX_FILE_BYTES,
                                "split the file: the directory holds a file of 256 KiB or more for a reviewer")


class FileCount(unittest.TestCase):
    def test_the_plugin_holds_512_files_or_fewer(self) -> None:
        # The files a commit would ship: tracked, plus new ones not ignored.
        try:
            r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others",
                                "--exclude-standard"], capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git is not available")
        if r.returncode != 0:
            self.skipTest("not a git checkout")
        files = {p for p in r.stdout.decode("utf-8", "replace").split("\0") if p and (ROOT / p).is_file()}
        self.assertLessEqual(len(files), MAX_FILES)


if __name__ == "__main__":
    unittest.main()
