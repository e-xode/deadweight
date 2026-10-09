"""Whether git tracks or ignores a file, asked of git - where the labelled corpus cannot reach:
an audit root below the repository root, and a machine without git.

    python3 -m unittest discover -s tests

The corpus builds each case at the root of a fresh `git init`; these situations need a commit
above the audit root and an empty PATH. Fictional shop throughout.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402
from deadweight_audit.repo import tracked_paths  # noqa: E402

CLAUDE_MD = "# shop-api\n\nRun `make test` before any change.\n"
LOCAL = json.dumps({"permissions": {"allow": ["Bash(make test)"]}}) + "\n"


def run(root: Path) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["--root", str(root), "--json", "--all"])
    return json.loads(out.getvalue())["findings"]


def messages(findings: list[dict], check: str) -> list[str]:
    return [f["message"] for f in findings if f["check"] == check]


class GitSubfolderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.top = Path(self.tmp.name) / "shop-monorepo"
        self.pkg = self.top / "packages" / "shop-api"
        (self.pkg / ".claude").mkdir(parents=True)
        (self.pkg / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        (self.pkg / ".claude" / "settings.local.json").write_text(LOCAL, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.top), "-c", "user.email=shop@example.invalid",
                        "-c", "user.name=shop", *args], check=True, capture_output=True)

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_local_settings_committed_above_the_audit_root_are_reported(self) -> None:
        # audit externe 3, wave 2: `root / ".git"` was tested, so a file committed in the
        # enclosing repository was never looked at from a package folder.
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "shop")
        found = messages(run(self.pkg), "24-settings-local")
        self.assertEqual(len(found), 1, found)
        self.assertIn("COMMITTED", found[0])

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_local_settings_ignored_by_the_enclosing_repository_stay_silent(self) -> None:
        (self.top / ".gitignore").write_text("settings.local.json\n", encoding="utf-8")
        self.git("init", "-q")
        self.assertEqual(messages(run(self.pkg), "24-settings-local"), [])

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_local_settings_neither_tracked_nor_ignored_above_the_root(self) -> None:
        self.git("init", "-q")
        found = messages(run(self.pkg), "24-settings-local")
        self.assertEqual(len(found), 1, found)
        self.assertIn("not ignored", found[0])

    def test_no_git_on_path_crashes_nothing(self) -> None:
        # Without git on PATH, check_settings (24) and the tree walk (tracked_paths) raised
        # FileNotFoundError: 00-check-crashed instead of the findings.
        (self.pkg / ".git").mkdir()
        empty = Path(self.tmp.name) / "empty-bin"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(empty)}):
            found = run(self.pkg)
            walked = tracked_paths(self.pkg)
        self.assertEqual(messages(found, "00-check-crashed"), [])
        self.assertIn("CLAUDE.md", walked)


if __name__ == "__main__":
    unittest.main()
