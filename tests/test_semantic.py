"""The semantic layer stays apart from the auditor that counts - checked without any network.

    python3 -m unittest discover -s tests

A fixed answer is replayed through DEADWEIGHT_SEMANTIC_RESPONSE: the tests are about what the
layer does with an answer, not about what a model would say.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "config-auditor" / "scripts"
AUDIT = SCRIPTS / "audit.py"
SEMANTIC = SCRIPTS / "semantic.py"
sys.path.insert(0, str(SCRIPTS))

CLAUDE_MD = "# shop-api\n\nRun `make test` before any change.\nNever edit the locale JSON files by hand.\n"
SKILL = ("---\nname: shop-i18n\ndescription: Translate the shop storefront. Do not use for refunds.\n---\n\n"
         "Edit `locales/fr.json` by hand to add a missing key.\n")
TRUE_QUOTES = [{"file": "CLAUDE.md", "text": "Never edit the locale JSON files by hand."},
               {"file": ".claude/skills/shop-i18n/SKILL.md", "text": "Edit `locales/fr.json` by hand to add a missing key."}]
INTERNAL = [{"file": "CLAUDE.md", "text": "Run `make test` before any change."},
            {"file": "CLAUDE.md", "text": "Never edit the locale JSON files by hand."}]
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def project(tmp: str) -> Path:
    root = Path(tmp) / "shop-api"
    (root / ".claude" / "skills" / "shop-i18n").mkdir(parents=True)
    (root / "CLAUDE.md").write_bytes(CLAUDE_MD.encode("utf-8"))
    (root / ".claude" / "skills" / "shop-i18n" / "SKILL.md").write_bytes(SKILL.encode("utf-8"))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def answer(tmp: str, family: str, quotes: list[dict], explanation: str = "One file forbids what the other prescribes.") -> str:
    path = Path(tmp) / f"answer-{family}.json"
    path.write_text(json.dumps({"findings": [{"family": family, "quotes": quotes, "explanation": explanation}]}),
                    encoding="utf-8")
    return str(path)


def semantic(root: Path, replay: str, *opts: str) -> tuple[int, dict]:
    r = subprocess.run([sys.executable, str(SEMANTIC), "--root", str(root), "--json", *opts],
                       capture_output=True, text=True, env={**ENV, "DEADWEIGHT_SEMANTIC_RESPONSE": replay})
    return r.returncode, json.loads(r.stdout)


class ApartFromTheAuditor(unittest.TestCase):
    """The auditor that counts is not touched: same bytes, same sha, same floors."""

    def test_the_layer_is_not_in_the_identity(self) -> None:
        from deadweight_audit.identity import instrument_files
        names = [f.relative_to(SCRIPTS).as_posix() for f in instrument_files()]
        self.assertFalse([n for n in names if n.startswith("deadweight_semantic") or n == "semantic.py"])

    def test_the_audit_never_imports_it(self) -> None:
        # An import at load time would make the layer part of every audit, and of the instrument.
        code = ("import sys, io, contextlib; sys.path.insert(0, sys.argv[1]); "
                "from deadweight_audit.cli import main\n"
                "with contextlib.redirect_stdout(io.StringIO()): main(['--root', sys.argv[2], '--json'])\n"
                "print(any(m.startswith('deadweight_semantic') for m in sys.modules))")
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([sys.executable, "-B", "-c", code, str(SCRIPTS), str(project(tmp))],
                                 capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "False")

    def test_it_writes_no_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            subprocess.run([sys.executable, str(AUDIT), "--root", str(root), "--set-floor"],
                           capture_output=True, env=ENV)
            floor = (root / ".claude" / "audit" / "floor.json").read_bytes()
            rc, out = semantic(root, answer(tmp, "58", TRUE_QUOTES))
            self.assertEqual((root / ".claude" / "audit" / "floor.json").read_bytes(), floor)
        self.assertEqual(rc, 0)
        self.assertFalse(out["counted"])


class Evidence(unittest.TestCase):
    def test_a_finding_with_its_quotes_stands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, out = semantic(project(tmp), answer(tmp, "58", TRUE_QUOTES))
        self.assertEqual([f["check"] for f in out["findings"]], ["58-semantic-contradiction"])

    def test_an_invented_quote_rejects_the_finding(self) -> None:
        invented = [TRUE_QUOTES[0], {"file": ".claude/skills/shop-i18n/SKILL.md",
                                     "text": "Always edit the locale files by hand when a key is missing."}]
        with tempfile.TemporaryDirectory() as tmp:
            _, out = semantic(project(tmp), answer(tmp, "58", invented))
        self.assertEqual(out["findings"], [])
        # The replayed answer reaches every request; those that did not ask for 58 reject it for
        # that reason. The one that did must reject it for the invented quote.
        self.assertTrue(any(r["why"].startswith("invented") for r in out["rejected"]))

    def test_a_disowned_finding_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, out = semantic(project(tmp), answer(tmp, "58", TRUE_QUOTES, "Weak; not reported as a real contradiction."))
        self.assertEqual(out["findings"], [])
        self.assertTrue(any(r["why"].startswith("disowned") for r in out["rejected"]))


class WhatIsShown(unittest.TestCase):
    """Defaults decided on 2026-10-01 from measured precision: 58 and 59 between files."""

    def test_a_duplicate_inside_one_file_is_on_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, ans = project(tmp), answer(tmp, "59", INTERNAL, "Stated twice in one file.")
            _, plain = semantic(root, ans)
            _, also = semantic(root, ans, "--also", "internal-duplicates")
        self.assertEqual(plain["findings"], [])
        self.assertGreater(plain["internal_duplicates_not_shown"], 0)
        self.assertEqual({f["check"] for f in also["findings"]}, {"59-semantic-duplicate"})

    def test_families_not_requested_are_not_asked(self) -> None:
        from deadweight_audit.context import AuditContext
        from deadweight_semantic import collect
        with tempfile.TemporaryDirectory() as tmp:
            docs = collect.documents(AuditContext(root=project(tmp)))
            asked = {f for r in collect.plan(docs, 100)[0] for f in r.families}
            more = {f for r in collect.plan(docs, 100, {"58", "59", "61"})[0] for f in r.families}
        self.assertEqual(asked, {"58", "59"})
        self.assertIn("61", more)

    def test_bad_options_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            alias = subprocess.run([sys.executable, str(SEMANTIC), "--root", str(root), "--model", "sonnet"],
                                   capture_output=True, text=True)
            unknown = subprocess.run([sys.executable, str(SEMANTIC), "--root", str(root), "--also", "everything"],
                                     capture_output=True, text=True)
        self.assertEqual((alias.returncode, unknown.returncode), (2, 2))


class Transport(unittest.TestCase):
    def test_a_missing_claude_is_retried_then_reported(self) -> None:
        # A Claude Code update leaves `claude` missing for a few seconds (2026-10-01, twice).
        from deadweight_semantic import transport
        calls = []
        real_run, real_wait = transport.subprocess.run, transport.RETRY_WAIT

        def missing(*a, **k):
            calls.append(1)
            raise FileNotFoundError(2, "No such file or directory", "claude")
        transport.subprocess.run, transport.RETRY_WAIT = missing, 0
        os.environ.pop("DEADWEIGHT_SEMANTIC_RESPONSE", None)
        try:
            ans = transport.ask("s", "p", "claude-sonnet-5-5")
        finally:
            transport.subprocess.run, transport.RETRY_WAIT = real_run, real_wait
        self.assertEqual(len(calls), transport.RETRIES + 1)
        self.assertIn("FileNotFoundError", ans.error)


if __name__ == "__main__":
    unittest.main()
