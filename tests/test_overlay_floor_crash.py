"""The ratchet and the dispatcher, on what a single audit run cannot show.

    python3 -m unittest discover -s tests

The labelled corpus runs one audit per case, without `--check-floor`, and counts a crashed
check as a failure: the floor comparison and a crash of check_skills are held here.
Fictional shop throughout.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit import registry  # noqa: E402
from deadweight_audit.cli import main  # noqa: E402
from deadweight_audit.identity import audit_sha  # noqa: E402

CLAUDE_MD = "# shop-api\n\nRun `make test` before any change.\n"
SKILL = ("---\nname: shop-notes\ndescription: Keep the shop team's working notes on refunds. "
         "Do not use for customer-facing text.\ncolour: blue\n---\n\nRead this first.\n")


def run(root: Path, *extra: str) -> tuple[int, list[dict]]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = main(["--root", str(root), "--json", "--all", *extra])
    return rc, json.loads(out.getvalue())["findings"]


class FloorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "shop-api"
        (self.root / ".claude" / "skills" / "shop-notes").mkdir(parents=True)
        (self.root / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
        (self.root / ".claude" / "skills" / "shop-notes" / "SKILL.md").write_text(SKILL, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def floor(self, **data) -> None:
        f = self.root / ".claude" / "audit" / "floor.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"date": "2026-10-08", "layout": "project", **data}), encoding="utf-8")

    def test_a_swapped_warning_id_is_reported(self) -> None:
        # audit externe 2026-10-08, P1-D2-07 / P2-D2-04: same totals, different id.
        _, findings = run(self.root)
        warns = sorted(f["check"] for f in findings if f["severity"] == "WARN")
        self.assertIn("02-skill-unknown-field", warns)
        self.floor(audit_sha=audit_sha(), errors=0, warnings=len(warns),
                   error_ids=[], warning_ids=["32-skill-name-reserved"])
        rc, findings = run(self.root, "--check-floor")
        swap = [f for f in findings if f["check"] == "34-floor" and f["severity"] == "WARN"]
        self.assertEqual(len(swap), 1, findings)
        self.assertIn("02-skill-unknown-field", swap[0]["message"])
        self.assertEqual(rc, 0)   # counts-only contract: a WARN, not a CI failure

    def test_a_floor_without_ids_compares_counts_only(self) -> None:
        _, findings = run(self.root)
        warns = sum(1 for f in findings if f["severity"] == "WARN")
        self.floor(audit_sha=audit_sha(), errors=0, warnings=warns)
        _, findings = run(self.root, "--check-floor")
        self.assertEqual([f["severity"] for f in findings if f["check"] == "34-floor"], ["INFO"])

    def test_the_sha_message_claims_nothing_about_releases(self) -> None:
        # audit externe 2026-10-08, P2-D2-06: "most releases do not" was false.
        self.floor(audit_sha="00000000", errors=0, warnings=0, error_ids=[], warning_ids=[])
        _, findings = run(self.root, "--check-floor")
        msg = next(f["message"] for f in findings if f["check"] == "34-floor")
        self.assertNotIn("most releases do not", msg)
        self.assertIn("detects no regression", msg)


class CrashTest(unittest.TestCase):
    def crashed_run(self, claude_md: str = CLAUDE_MD, agent: str | None = None) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shop-api"
            (root / ".claude" / "skills" / "shop-notes").mkdir(parents=True)
            (root / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
            (root / ".claude" / "skills" / "shop-notes" / "SKILL.md").write_text(SKILL, encoding="utf-8")
            if agent is not None:
                (root / ".claude" / "agents").mkdir()
                (root / ".claude" / "agents" / "shop-refunder.md").write_text(agent, encoding="utf-8")
            boom = mock.Mock(side_effect=UnicodeDecodeError("utf-8", b"\xe9", 0, 1, "invalid"))
            boom.__name__ = "check_skills"
            with mock.patch.object(registry, "check_skills", boom):
                _, findings = run(root)
        return findings

    def test_no_skill_count_after_check_skills_crashed(self) -> None:
        # audit externe 2026-10-08, P1-A--05 / P2-A--07: an empty list read as "0 skills".
        findings = self.crashed_run()
        crashed = [f for f in findings if f["check"] == "00-check-crashed"]
        self.assertTrue(any("check_description_overlap" in f["message"] for f in crashed), crashed)
        for check in ("33-description-overlap", "29-listing-budget-derived"):
            self.assertFalse([f for f in findings if f["check"].startswith(check[:3])], check)
        # 17 still runs, as a lower bound that says the skills were not measured.
        budget = [f["message"] for f in findings if f["check"] == "17-always-loaded-budget"]
        self.assertTrue(budget, findings)
        for msg in budget:
            self.assertIn("not measured", msg)
            self.assertNotIn("skill descriptions 0", msg)

    def test_findings_that_do_not_read_the_skill_list_survive(self) -> None:
        # audit externe 3, g--01: a crash of check_skills hid an over-budget CLAUDE.md and an
        # agent's unknown tool and model, none of which reads the skill list.
        big = CLAUDE_MD + "\n".join(f"- Refund rule {i}: check the order ledger first." for i in range(1100))
        agent = ("---\nname: shop-refunder\ndescription: Issue shop refunds.\n"
                 "tools: Read, Frobnicate\nmodel: gpt-4\n---\n\nRefund.\n")
        findings = self.crashed_run(big, agent)
        checks = {f["check"] for f in findings}
        self.assertIn("23-agent-tools", checks, findings)
        self.assertIn("23-agent-model", checks, findings)
        budget = [f for f in findings if f["check"] == "17-always-loaded-budget"]
        self.assertTrue(any("Exceeds the hard budget" in f["message"] and "at least" in f["message"]
                            for f in budget), budget)

    def test_rule_import_agent_findings_survive_check_skills_crash(self) -> None:
        # audit externe 3, g8-00: skipping every check that took the skill list also
        # dropped a rule's `globs:`, a missing import and an unknown agent tool.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "shop-api"
            (root / ".claude" / "skills" / "shop-notes").mkdir(parents=True)
            (root / ".claude" / "rules").mkdir(parents=True)
            (root / ".claude" / "agents").mkdir(parents=True)
            (root / "CLAUDE.md").write_text(CLAUDE_MD + "\n@docs/shop-missing.md\n", encoding="utf-8")
            (root / ".claude" / "skills" / "shop-notes" / "SKILL.md").write_text(SKILL, encoding="utf-8")
            (root / ".claude" / "rules" / "shop-api.md").write_text(
                "---\nglobs: src/api/**\n---\nValidate every request body.\n", encoding="utf-8")
            (root / ".claude" / "agents" / "shop-reviewer.md").write_text(
                "---\nname: shop-reviewer\ndescription: Review shop-api changes for refund bugs. "
                "Do not use for UI work.\ntools: Read, Grepp\n---\n\nReview.\n", encoding="utf-8")
            boom = mock.Mock(side_effect=RuntimeError("forced"))
            boom.__name__ = "check_skills"
            with mock.patch.object(registry, "check_skills", boom):
                _, findings = run(root)
        checks = {f["check"] for f in findings}
        for check in ("14-rule-unknown-field", "01-claude-md-import", "23-agent-tools"):
            self.assertIn(check, checks)
        crashed = [f["message"] for f in findings if f["check"] == "00-check-crashed"]
        self.assertTrue(crashed and "check_companions" not in crashed[0], crashed)


if __name__ == "__main__":
    unittest.main()
