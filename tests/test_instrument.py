"""What the auditor assumes about itself, held in place.

    python3 -m unittest discover -s tests

Each test names an assumption that no finding on an audited repository would reveal if
it broke: the auditor reading its own files, its identity, and the state of one audit.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "config-auditor" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from deadweight_audit.catalog import known_check_ids  # noqa: E402
from deadweight_audit.cli import main  # noqa: E402
from deadweight_audit.identity import PACKAGE_DIR, instrument_files  # noqa: E402

CLAUDE_MD = "# shop-api\n\nRun `make test` before any change.\n"


def audit(root: Path) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["--root", str(root), "--json", "--all"])
    return json.loads(out.getvalue())["findings"]


def sha_of(scripts: Path) -> str:
    """The identity as a fresh interpreter computes it for the copied auditor."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from deadweight_audit.identity import audit_sha; print(audit_sha())")
    return subprocess.run([sys.executable, "-B", "-c", code, str(scripts)], capture_output=True,
                          text=True, check=True).stdout.strip()


class Identity(unittest.TestCase):
    """The floor records the auditor's sha; the sha must move exactly when a count can."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = Path(self.tmp.name) / "config-auditor"
        shutil.copytree(SCRIPTS, self.skill / "scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.scripts = self.skill / "scripts"
        self.before = sha_of(self.scripts)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_any_module_changes_it(self) -> None:
        f = self.scripts / "deadweight_audit" / "checks" / "skills.py"
        f.write_text(f.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        self.assertNotEqual(sha_of(self.scripts), self.before)

    def test_the_entry_point_changes_it(self) -> None:
        f = self.scripts / "audit.py"
        f.write_text(f.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        self.assertNotEqual(sha_of(self.scripts), self.before)

    def test_documentation_and_bytecode_do_not(self) -> None:
        (self.skill / "references").mkdir()
        (self.skill / "references" / "x.md").write_text("doctrine\n", encoding="utf-8")
        (self.scripts / "README.md").write_text("notes\n", encoding="utf-8")
        (self.scripts / "deadweight_audit" / "__pycache__").mkdir()
        (self.scripts / "deadweight_audit" / "__pycache__" / "x.pyc").write_bytes(b"\0")
        self.assertEqual(sha_of(self.scripts), self.before)

    def test_line_endings_do_not(self) -> None:
        # git may check the same commit out with CRLF on Windows.
        for f in (self.scripts / "deadweight_audit").rglob("*.py"):
            f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(sha_of(self.scripts), self.before)


class ReadsItself(unittest.TestCase):
    """The auditor reads its own source in three places; each must see the whole package."""

    def test_check_ids_come_from_every_module(self) -> None:
        ids = known_check_ids()
        for expected in ("00-check-crashed", "01-claude-md-lines", "46-doctrine-copy",
                         "55-cursor-rule-ignored", "31-overlay-threshold"):
            self.assertIn(expected, ids)

    def test_documented_flags_are_found_in_the_package(self) -> None:
        # Auditing this plugin, 37 reads the flags its documentation shows from the
        # auditor's source. Found nowhere, it would fall silent instead of failing.
        src = "".join(f.read_text(encoding="utf-8") for f in instrument_files())
        for flag in ("--root", "--json", "--all", "--set-floor", "--check-floor", "--layout"):
            self.assertIn(f'"{flag}"', src)

    def test_no_module_reads_the_references(self) -> None:
        # The identity covers the package's Python source only. A check that read the
        # plugin's references/ at run time would change findings under an unchanged sha -
        # 46 did until 0.21.0. Its vocabulary is frozen in vocabulary/doctrine.py instead.
        readers = []
        for f in PACKAGE_DIR.rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Name) and node.id == "SKILL_DIR":
                    readers.append(f.name)
        self.assertEqual([r for r in readers if r != "identity.py"], [])


class OneAuditLeavesNothing(unittest.TestCase):
    """Until 0.21.0 an overridden threshold was written into the module's globals."""

    def test_an_override_does_not_reach_the_next_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            moved, plain = Path(tmp) / "shop-api", Path(tmp) / "shop-web"
            for root in (moved, plain):
                (root / ".claude").mkdir(parents=True)
                (root / "CLAUDE.md").write_bytes(CLAUDE_MD.encode("utf-8"))
            (moved / ".claude" / "audit.local.json").write_text(json.dumps({"thresholds": {
                "CLAUDE_MD_MAX_LINES": {"value": 1, "reason": "test", "date": "2026-09-29"}}}),
                encoding="utf-8")
            lines = lambda fs: [f for f in fs if f["check"] == "01-claude-md-lines"]  # noqa: E731
            self.assertEqual(len(lines(audit(moved))), 1)
            self.assertEqual(lines(audit(plain)), [])


if __name__ == "__main__":
    unittest.main()
