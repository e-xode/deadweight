"""What Anthropic's plugin directory refuses from an unverified organization, held by the tests.

    python3 -m unittest tests.test_directory_layout

The directory refused 0.35.0 with two blocking reasons: "Files in the plugin's bin/ folder accepted
only from Verified organizations" and "Files outside the allowed types accepted only from Verified
organizations". The portal's instruction for the second names every file that starts with `#!` and
asks that every text file be saved as UTF-8 with no NUL byte. The documentation gives the first:
"Don't include a top-level `bin/` directory in any plugin you distribute through organization
settings. claude.ai rejects a plugin that has one" (claude.com/docs/plugins/org-sync). An executable
bit is not named by either; the directory listed "ships executable files" among its non-blocking
findings, and git's mode 100755 is the only executable mark a repository carries, so it is held too.

Not held here, because it is not known: whether the directory accepts a `.py` or `.sh` file that has
no `#!` line and no executable bit. Anthropic's support could not say.

This repository is the plugin folder (`.claude-plugin/plugin.json` is at its root), and what it ships
is what git tracks. Without git, outside a checkout, or in a checkout whose root is not this folder
(an untracked copy inside another repository, where `ls-files` lists nothing), the tests are skipped:
on Windows outside git a file has no executable bit to read.
"""
from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}


def git(*args: str) -> bytes | None:
    """`git -C ROOT <args>` output, or None when git or the checkout is missing."""
    try:
        r = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(ROOT), *args],
                           capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def tracked() -> list[str] | None:
    out = git("ls-files", "-z")
    return None if out is None else [p for p in out.decode("utf-8", "replace").split("\0") if p]


def toplevel() -> Path | None:
    """The root of the checkout ROOT is in, or None."""
    out = git("rev-parse", "--show-toplevel")
    if out is None:
        return None
    try:
        return Path(out.decode("utf-8", "replace").strip()).resolve()
    except OSError:
        return None


class DirectoryLayout(unittest.TestCase):
    def setUp(self) -> None:
        top = toplevel()
        if top is None:
            self.skipTest("git is not available, or this is not a git checkout")
        if os.path.normcase(str(top)) != os.path.normcase(str(ROOT)):   # drive letter case on Windows
            # An untracked copy inside another repository: `ls-files` succeeds with an empty list,
            # and the tests would pass on nothing (audit of 0.36.0, A-00).
            self.skipTest(f"the checkout is {top}, not the plugin folder {ROOT}")
        files = tracked()
        if files is None:
            self.skipTest("git ls-files failed")
        self.files = files

    def test_no_top_level_bin_folder(self) -> None:
        self.assertEqual([p for p in self.files if p.split("/", 1)[0] == "bin"], [],
                         "claude.ai rejects a plugin with a top-level bin/ (org-sync): use scripts/")

    def test_no_tracked_file_starts_with_a_shebang(self) -> None:
        found = []
        for p in self.files:
            f = ROOT / p
            if not f.is_file():                     # deleted in the working tree, not yet in the index
                continue
            with f.open("rb") as fh:
                head = fh.read(5)
            if head.removeprefix(b"\xef\xbb\xbf").startswith(b"#!"):
                found.append(p)
        self.assertEqual(found, [], "the directory refuses a file that starts with #!: run it as "
                                    "`python3 <file>` or `bash <file>` instead")

    def test_no_tracked_file_has_the_executable_bit(self) -> None:
        out = git("ls-files", "-s", "-z")
        if out is None:
            self.skipTest("git ls-files -s failed")
        modes = [entry.split(b"\t", 1) for entry in out.split(b"\0") if entry]
        found = [path.decode("utf-8", "replace") for meta, path in modes if meta.startswith(b"100755 ")]
        self.assertEqual(found, [], "mode 100755 in the index: git update-index --chmod=-x <file>")

    def test_every_text_file_is_utf8_without_nul(self) -> None:
        found = []
        for p in self.files:
            f = ROOT / p
            if not f.is_file() or f.suffix.lower() in IMAGES:
                continue
            data = f.read_bytes()
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                found.append(f"{p}: not UTF-8")
                continue
            if b"\0" in data:
                found.append(f"{p}: NUL byte")
        self.assertEqual(found, [], "the directory asks for every text file in UTF-8 with no NUL byte")


if __name__ == "__main__":
    unittest.main()
