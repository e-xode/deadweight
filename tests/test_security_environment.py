"""check_security where the labelled corpus cannot reach: a subfolder of a repository,
a machine without git, a Windows path module.

    python3 -m unittest discover -s tests

The corpus builds each case at the root of a fresh `git init` and runs on the host's OS;
these three situations need a commit above the audit root, an empty PATH and `ntpath`.
Fictional shop throughout.
"""
from __future__ import annotations

import contextlib
import io
import json
import ntpath
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.checks import security  # noqa: E402
from deadweight_audit.cli import main  # noqa: E402

CLAUDE_MD = "# shop-api\n\nRun `make test` before any change.\n"
BLANKET = json.dumps({"permissions": {"allow": ["Bash(*)"]}}) + "\n"


def run(root: Path) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["--root", str(root), "--json", "--all"])
    return json.loads(out.getvalue())["findings"]


def grades(findings: list[dict], check: str) -> list[str]:
    return [f["severity"] for f in findings if f["check"] == check]


class SecurityEnvironmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.top = Path(self.tmp.name) / "shop-monorepo"
        self.top.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @unittest.skipUnless(shutil.which("git"), "needs git")
    def test_tracked_local_settings_in_a_subfolder_stay_shared(self) -> None:
        # audit externe 3, g2-01: the repository is ABOVE the audit root (a monorepo package).
        pkg = self.top / "packages" / "shop-api"
        (pkg / ".claude").mkdir(parents=True)
        (pkg / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        (pkg / ".claude" / "settings.local.json").write_text(BLANKET, encoding="utf-8")
        git = ["git", "-C", str(self.top), "-c", "user.email=shop@example.invalid", "-c", "user.name=shop"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "shop"], check=True)
        self.assertEqual(grades(run(pkg), "50-security-broad-allow"), ["ERROR"])

    def test_no_git_on_path_keeps_the_strict_grade(self) -> None:
        # audit externe 3, g2-02: git absent must not stop check_security.
        root = self.top
        (root / ".git").mkdir()
        (root / ".claude").mkdir()
        (root / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        (root / ".claude" / "settings.local.json").write_text(BLANKET, encoding="utf-8")
        empty = Path(self.tmp.name) / "empty-bin"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(empty)}):
            findings = run(root)
        self.assertEqual(grades(findings, "50-security-broad-allow"), ["ERROR"])
        self.assertFalse([f for f in findings if f["check"] == "00-check-crashed"
                          and "check_security" in f["message"]])

    def test_git_that_cannot_answer_is_not_quoted_as_tracking(self) -> None:
        # Git missing (or refusing a dubious owner) keeps the strict grade, but the message does
        # not say the file reaches everyone, which git never confirmed (external audit 4, se-00b).
        root = self.top
        (root / ".git").mkdir()
        (root / ".claude").mkdir()
        (root / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        (root / ".claude" / "settings.local.json").write_text(BLANKET, encoding="utf-8")
        empty = Path(self.tmp.name) / "empty-bin"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"PATH": str(empty)}):
            found = [f for f in run(root) if f["check"] == "50-security-broad-allow"]
        self.assertEqual([f["severity"] for f in found], ["ERROR"])
        self.assertIn("if git tracks it (git could not answer)", found[0]["message"])

    def test_parent_directories_are_reported_with_windows_paths(self) -> None:
        # audit externe 3, g2-03: on Windows os.path is ntpath, whose normpath gives '..\\x'.
        root = self.top
        (root / ".claude").mkdir()
        (root / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        (root / ".claude" / "settings.json").write_text(json.dumps(
            {"permissions": {"additionalDirectories": ["../shop-web", "..\\shop-lib", "~"]}}),
            encoding="utf-8")
        win_os = types.SimpleNamespace(**{**vars(os), "path": ntpath})
        with mock.patch.object(security, "os", win_os):
            findings = run(root)
        msgs = [f["message"] for f in findings if f["check"] == "50-security-directories"]
        self.assertEqual(len(msgs), 3, msgs)
        self.assertTrue(any("'../shop-web'" in m for m in msgs))
        self.assertTrue(any("'..\\shop-lib'" in m for m in msgs))


if __name__ == "__main__":
    unittest.main()
