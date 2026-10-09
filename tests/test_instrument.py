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
import os
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



class HomeDirectory(unittest.TestCase):
    """The home directory holds USER-scope configuration: project rules are not applied to it
    (anthropics/claude-code#93109, 2026-10-08: 8 errors and 6 warnings on one machine)."""

    def test_home_is_not_audited_as_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".claude" / "agents").mkdir(parents=True)
            (home / ".claude" / "settings.json").write_text('{"permissions": {"defaultMode": "plan"}}\n')
            r = subprocess.run([sys.executable, str(SCRIPTS / "audit.py"), "--root", str(home), "--json"],
                               capture_output=True, text=True, env={**os.environ, "HOME": str(home)})
            findings = json.loads(r.stdout)["findings"]
            self.assertEqual([f for f in findings if f["severity"] in ("ERROR", "WARN")], [])
            self.assertTrue(any("home directory" in f["message"] for f in findings if f["check"] == "00-layout"))


class Overlay(unittest.TestCase):
    """The overlay's own ids: a renamed id keeps working, and only emitted ids are exemptable."""

    def write(self, root: Path, exemptions: list[dict], thresholds: dict | None = None) -> None:
        (root / ".claude").mkdir(parents=True, exist_ok=True)
        (root / "CLAUDE.md").write_bytes(CLAUDE_MD.encode("utf-8"))
        local = {"exemptions": [{"path": "CLAUDE.md", "reason": "test", "date": "2026-10-08", **e}
                                for e in exemptions]}
        if thresholds:
            local["thresholds"] = thresholds
        (root / ".claude" / "audit.local.json").write_text(json.dumps(local), encoding="utf-8")

    def test_an_alias_is_reported_and_still_exempts(self) -> None:
        # An alias added for this test only: patch.dict restores the shipped aliases after it,
        # which later tests in the same process rely on (audit externe 3, g9-01).
        from unittest import mock
        from deadweight_audit.catalog import CHECK_ID_ALIASES
        with mock.patch.dict(CHECK_ID_ALIASES, {"01-claude-md-lines-old": "01-claude-md-lines"}):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "shop-api"
                self.write(root, [{"check": "01-claude-md-lines-old"}],
                           {"CLAUDE_MD_MAX_LINES": {"value": 1, "reason": "test", "date": "2026-10-08"}})
                found = audit(root)
        checks = [f["check"] for f in found]
        self.assertIn("31-overlay-alias", checks)
        self.assertNotIn("01-claude-md-lines", checks)
        self.assertNotIn("31-overlay-unknown-check", checks)

    def test_the_alias_test_leaves_the_shipped_aliases_in_place(self) -> None:
        # Run in-process before or after the labelled cases, the test above must not erase
        # `34-audit-sha` -> `34-floor` (audit externe 3, g9-01). A test-hygiene guard: it checks
        # the test suite, not the auditor, and passes on an auditor without the fix; the alias
        # in a full run is the labelled case 31-alias-34-audit-sha (external audit 4, te-01).
        from deadweight_audit.catalog import CHECK_ID_ALIASES
        before = dict(CHECK_ID_ALIASES)
        self.test_an_alias_is_reported_and_still_exempts()
        self.assertEqual(CHECK_ID_ALIASES, before)
        self.assertEqual(CHECK_ID_ALIASES.get("34-audit-sha"), "34-floor")

    @staticmethod
    def emitted() -> set[str]:
        """Ids passed literally to `report.add`. known_check_ids() cannot answer this: it reads
        every quoted id in the package, the lists that name them included."""
        out = set()
        for f in instrument_files():
            for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add" \
                        and n.args and isinstance(n.args[0], ast.Constant):
                    out.add(n.args[0].value)
        return out

    def test_every_unexemptable_id_is_emitted(self) -> None:
        # Until 0.23.0 the set named `34-audit-sha`, which no code emits (the ratchet is 34-floor).
        from deadweight_audit.overlay import UNEXEMPTABLE
        self.assertEqual(sorted(UNEXEMPTABLE - self.emitted()), [])

    def test_no_check_group_reads_as_an_id_nothing_emits(self) -> None:
        # "43-mcp" in CHECKS made an exemption for `43-mcp` pass the typo guard and excuse nothing.
        import re
        from deadweight_audit.catalog import CHECKS
        ids = [c for c in CHECKS if re.fullmatch(r"\d{2}-[a-z0-9-]+", c)]
        self.assertEqual(sorted(set(ids) - self.emitted()), [])


if __name__ == "__main__":
    unittest.main()
