"""A memory file that is not UTF-8 does not stop the CLAUDE.md check.

    python3 -m unittest discover -s tests

The corpus writes its files in UTF-8, so a Latin-1 CLAUDE.local.md cannot be expressed
there (audit externe 3, g4-00): measuring every memory file read each one strictly, and
one personal, gitignored file in a legacy encoding crashed check_claude_md, losing the
01-agents-md-unread warning and every other finding of that check.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402


def audit(root: Path) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["--root", str(root), "--json", "--all"])
    return json.loads(out.getvalue())["findings"]


class MemoryFileEncoding(unittest.TestCase):
    def _run(self, latin1_name: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shop-api"
            (root / ".claude").mkdir(parents=True)
            (root / "CLAUDE.md").write_text("# shop-api\n\nUse pnpm.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# shop-api\n\nRun `pnpm test`.\n", encoding="utf-8")
            (root / latin1_name).write_bytes(b"Notes caf\xe9 perso\n")
            return audit(root)

    def test_latin1_local_memory_keeps_findings(self):
        for name in ("CLAUDE.local.md", ".claude/CLAUDE.md"):
            with self.subTest(name=name):
                found = self._run(name)
                checks = {f["check"] for f in found}
                self.assertNotIn("00-check-crashed", checks)
                self.assertIn("01-agents-md-unread", checks)

    def test_no_negative_comment_count(self):
        # Each replaced byte counts 3 bytes decoded and 1 on disk: measured against the disk,
        # the "HTML comments not injected" figure went negative (external audit 4, cl-01).
        found = self._run("CLAUDE.local.md")
        size = [f["message"] for f in found if f["check"] == "01-claude-md-size"
                and f["message"].startswith("CLAUDE.local.md")]
        self.assertEqual(len(size), 1)
        self.assertNotIn("-", size[0].split("<=")[1])
        self.assertNotIn("HTML comments", size[0])

if __name__ == "__main__":
    unittest.main()
