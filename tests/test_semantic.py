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
import unittest.mock
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



class ReferencesOneHop(unittest.TestCase):
    """S1: a file an instruction file points to is read with it - one hop, inside the repository."""

    def plan(self, root: Path):
        from deadweight_audit.context import AuditContext
        from deadweight_semantic import collect
        docs = collect.documents(AuditContext(root=root))
        return docs, collect.plan(docs, 100, {"58", "59"})[0]

    def test_a_linked_reference_is_sent_with_its_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            skill = root / ".claude" / "skills" / "shop-i18n"
            (skill / "references").mkdir()
            (skill / "references" / "keys.md").write_text("Add keys to `locales/fr.json` by hand.\n", encoding="utf-8")
            (skill / "SKILL.md").write_text(SKILL + "\nSee [keys](references/keys.md).\n", encoding="utf-8")
            docs, reqs = self.plan(root)
            ref = ".claude/skills/shop-i18n/references/keys.md"
            self.assertIn(ref, {d.rel for d in docs if d.kind == "reference"})
            focus = [r for r in reqs if r.kind == "focus" and r.focus == ".claude/skills/shop-i18n/SKILL.md"]
            self.assertIn(ref, {d.rel for d in focus[0].docs})

    def test_a_link_out_of_the_repository_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (Path(tmp) / "outside.md").write_text("private notes\n", encoding="utf-8")
            (root / "CLAUDE.md").write_text(CLAUDE_MD + "\nSee [notes](../outside.md).\n", encoding="utf-8")
            docs, _ = self.plan(root)
            self.assertFalse(any("outside" in d.rel for d in docs))

    def test_a_reference_names_nothing_further(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            skill = root / ".claude" / "skills" / "shop-i18n"
            (skill / "references").mkdir()
            (skill / "references" / "a.md").write_text("See [b](b.md).\n", encoding="utf-8")
            (skill / "references" / "b.md").write_text("Second hop.\n", encoding="utf-8")
            (skill / "SKILL.md").write_text(SKILL + "\nSee [a](references/a.md).\n", encoding="utf-8")
            docs, _ = self.plan(root)
            rels = {d.rel for d in docs}
            self.assertIn(".claude/skills/shop-i18n/references/a.md", rels)
            self.assertNotIn(".claude/skills/shop-i18n/references/b.md", rels)


class ClaimsMethod(unittest.TestCase):
    """S2: instructions extracted, grouped by topic, compared across files - offline, one replayed
    answer carrying the three keys each step reads (items, groups, findings)."""

    def replay(self, tmp: str, quotes: list[dict], item_quotes: list[dict]) -> str:
        path = Path(tmp) / "answer-claims.json"
        path.write_text(json.dumps({
            "items": [{"file": q["file"], "subject": "locale json files", "polarity": p,
                       "action": "edit by hand", "quote": q["text"]}
                      for q, p in zip(item_quotes, ("must_not", "must"))],
            "assign": [["s0", "new: locale json files"]],
            "findings": [{"family": "58", "quotes": quotes,
                          "explanation": "One file forbids what the other prescribes."}]}), encoding="utf-8")
        return str(path)

    def run_claims(self, tmp: str, replay: str) -> dict:
        root = Path(tmp) / "shop-api"
        if not root.exists():
            project(tmp)
        r = subprocess.run([sys.executable, str(SEMANTIC), "--root", str(root), "--json", "--method", "claims"],
                           capture_output=True, text=True,
                           env={**ENV, "DEADWEIGHT_SEMANTIC_RESPONSE": replay, "XDG_CACHE_HOME": tmp})
        return json.loads(r.stdout)

    def test_a_contradiction_across_files_stands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_claims(tmp, self.replay(tmp, TRUE_QUOTES, TRUE_QUOTES))
            self.assertEqual([f["check"] for f in out["findings"]], ["58-semantic-contradiction"])
            self.assertEqual(out["stages"]["claims"], 2)
            self.assertEqual(out["stages"]["topics"], 1)

    def test_an_invented_quote_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = [TRUE_QUOTES[0], {"file": TRUE_QUOTES[1]["file"], "text": "Always edit every JSON file by hand."}]
            out = self.run_claims(tmp, self.replay(tmp, bad, TRUE_QUOTES))
            self.assertEqual(out["findings"], [])
            self.assertTrue(out["rejected"])

    def test_an_extracted_quote_that_is_not_in_the_file_is_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = [TRUE_QUOTES[0], {"file": TRUE_QUOTES[1]["file"], "text": "Nothing like this is written."}]
            out = self.run_claims(tmp, self.replay(tmp, TRUE_QUOTES, fake))
            self.assertEqual(out["stages"]["claims"], 1)
            self.assertEqual(out["stages"]["topics"], 0)

    def test_a_second_run_reads_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            replay = self.replay(tmp, TRUE_QUOTES, TRUE_QUOTES)
            self.run_claims(tmp, replay)
            out = self.run_claims(tmp, replay)
            self.assertEqual(out["stages"]["extract"]["requests"], 0)
            self.assertEqual(out["stages"]["extract"]["cached"], 2)


class Copies(unittest.TestCase):
    """The free half of the grouping: quotes that share most of their words, across files only."""

    def test_a_copied_list_joins_two_files_and_not_one(self) -> None:
        from deadweight_semantic.claims import Claim, copies
        a = "Phases run in order: spawn, regen, stock, ambush, combat, patrol, move, extract."
        b = "Phases run in this order: spawn, regen, stock, ambush, combat, patrol, autopilot, move, extract."
        far = "Refunds above the ceiling need a second approval from the shop owner."
        two_files = [Claim("c0", "x.md", "", "fact", "", a), Claim("c1", "y.md", "", "fact", "", b),
                     Claim("c2", "y.md", "", "must", "", far)]
        self.assertEqual([sorted(c.id for c in g) for g in copies(two_files)], [["c0", "c1"]])
        one_file = [Claim("c0", "x.md", "", "fact", "", a), Claim("c1", "x.md", "", "fact", "", b)]
        self.assertEqual(copies(one_file), [])


class Opposed(unittest.TestCase):
    """The free contradiction join: one code anchor, opposite polarity, two files."""

    def test_one_folder_must_and_must_not_in_two_files(self) -> None:
        from deadweight_semantic.claims import Claim, opposed
        add = Claim("c0", "rules/i18n.md", "translation keys", "must", "", "Add keys to `src/locales/en.json`.")
        never = Claim("c1", "rules/locales.md", "locale files", "must_not", "", "Never edit `src/locales/*.json` by hand.")
        same_side = Claim("c2", "rules/locales.md", "locale files", "must", "", "Keep `src/locales/fr.json` sorted.")
        self.assertEqual([sorted(c.id for c in g) for g in opposed([add, never])], [["c0", "c1"]])
        self.assertEqual(opposed([add, same_side]), [])
        lone = Claim("c3", "rules/i18n.md", "locale files", "must_not", "", "Never edit `src/locales/*.json` by hand.")
        self.assertEqual(opposed([add, lone]), [])


class Disowned(unittest.TestCase):
    def test_a_finding_that_calls_itself_weak_mid_sentence_is_rejected(self) -> None:
        from deadweight_semantic.evidence import DISOWNED_RE
        self.assertTrue(DISOWNED_RE.search("The guide uses raw pixels. This is weak: the guide could be mapped to "
                                           "tokens, so it is not a true contradiction."))
        self.assertFalse(DISOWNED_RE.search("The glossary requires parity across en, fr and km; the skill adds "
                                            "keys to en and fr only."))


class Vote(unittest.TestCase):
    """S3: a finding stands only when a majority of the answers give it; the result is cached."""

    def test_unit_of_a_skill_file(self) -> None:
        from deadweight_semantic.run import _unit
        self.assertEqual(_unit(".claude/skills/shop-i18n/references/keys.md"), ".claude/skills/shop-i18n")
        self.assertEqual(_unit("skills/shop-i18n/SKILL.md"), "skills/shop-i18n")
        self.assertEqual(_unit(".claude/agents/release.md"), ".claude/agents/release.md")

    def test_threshold_per_family_and_cache(self) -> None:
        """A duplicate needs 2 answers of 3, a contradiction all 3 (2026-10-08); the count is kept."""
        from unittest import mock
        from deadweight_semantic import claims, transport
        from deadweight_semantic.collect import Doc, Request
        a, b = TRUE_QUOTES[0], TRUE_QUOTES[1]
        req = Request(("58", "59"), [Doc(a["file"], "claims", a["text"]), Doc(b["file"], "claims", b["text"])], "topic")
        sources = {a["file"]: a["text"], b["file"]: b["text"]}

        def hit(fam):
            return json.dumps({"findings": [{"family": fam, "quotes": [a, b], "explanation": "Two rules collide."}]})
        empty = json.dumps({"findings": []})
        answers = iter([hit("58"), hit("58"), empty,      # contradiction 2/3: dropped
                        hit("58"), hit("58"), hit("58"),  # contradiction 3/3: kept
                        hit("59"), empty, hit("59")])     # duplicate 2/3: kept
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}), \
                mock.patch.object(transport, "ask", lambda *a, **k: transport.Answer(next(answers), 0.0, "m")):
            two_of_three = claims.confirm(req, "p1", "m", sources, claims.Stage())[0]
            unanimous = claims.confirm(req, "p2", "m", sources, claims.Stage())[0]
            duplicate = claims.confirm(req, "p3", "m", sources, claims.Stage())[0]
            stage = claims.Stage()
            cached = claims.confirm(req, "p2", "m", sources, stage)[0]
        self.assertEqual(two_of_three, [])
        self.assertEqual([(f["family"], f["votes"]) for f in unanimous], [("58", 3)])
        self.assertEqual([(f["family"], f["votes"]) for f in duplicate], [("59", 2)])
        self.assertEqual(cached, unanimous)
        self.assertEqual((stage.requests, stage.cached), (0, 1))


class SamePassage(unittest.TestCase):
    """A sentence quoted twice, or with a fragment of itself, contradicts nothing (audit, 2026-10-08)."""

    def test_one_sentence_on_both_sides_is_rejected(self) -> None:
        same = [INTERNAL[1], dict(INTERNAL[1])]
        fragment = [INTERNAL[1], {"file": "CLAUDE.md", "text": "edit the locale JSON files"}]
        for quotes in (same, fragment):
            with self.subTest(quotes=quotes[1]["text"]), tempfile.TemporaryDirectory() as tmp:
                _, out = semantic(project(tmp), answer(tmp, "58", quotes))
                self.assertEqual(out["findings"], [])
                self.assertIn("the two sides are the same passage", [r["why"] for r in out["rejected"]])

    def test_two_sentences_of_one_file_are_two_passages(self) -> None:
        from deadweight_semantic.evidence import _two_passages
        self.assertTrue(_two_passages(INTERNAL))
        self.assertTrue(_two_passages(TRUE_QUOTES))

    def test_a_rule_written_twice_in_one_file_is_a_duplicate(self) -> None:
        # Two copies of one sentence are two passages for a duplicate, never for a contradiction
        # (audit externe 3, g9-00).
        twice = [INTERNAL[1], dict(INTERNAL[1])]
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "CLAUDE.md").write_text(CLAUDE_MD + "\n## Translations\n\nNever edit the locale JSON files by hand.\n",
                                            encoding="utf-8")
            _, dup = semantic(root, answer(tmp, "59", twice, "The same rule is written twice."),
                              "--also", "internal-duplicates")
            _, contra = semantic(root, answer(tmp, "58", twice))
        self.assertEqual([f["check"] for f in dup["findings"]], ["59-semantic-duplicate"], dup["rejected"])
        self.assertEqual(contra["findings"], [])


class OtherFamilies(unittest.TestCase):
    """60, 61 and 62 had no replay: each fires on request, and only on request."""

    def test_each_family_fires_when_asked(self) -> None:
        cases = (("descriptions", "60", [{"file": ".claude/skills/shop-i18n/SKILL.md",
                                          "text": "Translate the shop storefront. Do not use for refunds."}]),
                 ("untestable", "61", [INTERNAL[0]]),
                 ("misplaced", "62", [INTERNAL[1]]))
        for option, family, quotes in cases:
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root, ans = project(tmp), answer(tmp, family, quotes, "The passage shows it.")
                _, plain = semantic(root, ans)
                _, asked = semantic(root, ans, "--also", option)
                self.assertEqual(plain["findings"], [])
                self.assertEqual({f["check"] for f in asked["findings"]},
                                 {f"{family}-semantic-" + {"60": "description-mismatch", "61": "untestable",
                                                           "62": "misplaced"}[family]})

    def test_62_promises_only_what_its_request_can_carry(self) -> None:
        # 62 is asked with CLAUDE.md and the rules only: a skill reference is not in that request.
        from deadweight_semantic.families import FAMILIES
        self.assertNotIn("skill reference", FAMILIES["62"][1])


class Options(unittest.TestCase):
    def test_the_hint_names_an_option_that_exists(self) -> None:
        from deadweight_semantic.run import Result
        text = Result(model="m", internal_skipped=2).render()
        self.assertIn("--also internal-duplicates", text)
        self.assertNotIn("--semantic-also", text)

    def test_skill_duplicates_is_accepted_and_said_to_do_nothing(self) -> None:
        from deadweight_semantic.families import ON_REQUEST
        self.assertNotIn("skill-duplicates", ON_REQUEST)
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            r = subprocess.run([sys.executable, str(SEMANTIC), "--root", str(root), "--json",
                                "--also", "skill-duplicates"], capture_output=True, text=True,
                               env={**ENV, "DEADWEIGHT_SEMANTIC_RESPONSE": answer(tmp, "58", TRUE_QUOTES)})
        self.assertEqual(r.returncode, 0)
        self.assertIn("no effect", r.stderr)

    def test_help_says_linked_files_are_sent(self) -> None:
        r = subprocess.run([sys.executable, str(SEMANTIC), "--help"], capture_output=True, text=True)
        self.assertIn("one hop", " ".join(r.stdout.split()))


class NotReviewed(unittest.TestCase):
    """Commands, CLAUDE.local.md, nested CLAUDE.md and AGENTS.md are not collected: the report names them."""

    FILES = (".claude/commands/shop-deploy.md", "CLAUDE.local.md", "packages/api/CLAUDE.md", "AGENTS.md")

    def build(self, tmp: str) -> Path:
        root = project(tmp)
        for rel in self.FILES:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("Never edit the locale JSON files by hand.\n", encoding="utf-8")
        return root

    def test_files_left_out_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, out = semantic(self.build(tmp), answer(tmp, "58", TRUE_QUOTES))
        self.assertEqual(sorted(out["instruction_files_not_reviewed"]), sorted(self.FILES))

    def test_a_file_an_instruction_file_imports_is_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.build(tmp)
            (root / "CLAUDE.md").write_text(CLAUDE_MD + "\n@CLAUDE.local.md\n", encoding="utf-8")
            _, out = semantic(root, answer(tmp, "58", TRUE_QUOTES))
        self.assertNotIn("CLAUDE.local.md", out["instruction_files_not_reviewed"])
        self.assertIn("CLAUDE.local.md", out["files_sent"])

    def test_a_claude_md_symlinked_to_agents_md_is_reviewed(self) -> None:
        # memory: "A CLAUDE.md symlinked to AGENTS.md [...] Claude reads the content once" - sent
        # as CLAUDE.md, AGENTS.md is not a file left out (audit externe 3, g9-02).
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "AGENTS.md").write_bytes(CLAUDE_MD.encode("utf-8"))
            (root / "CLAUDE.md").unlink()
            (root / "CLAUDE.md").symlink_to("AGENTS.md")
            _, out = semantic(root, answer(tmp, "58", TRUE_QUOTES))
        self.assertIn("CLAUDE.md", out["files_sent"])
        self.assertNotIn("AGENTS.md", out.get("instruction_files_not_reviewed", []))

    def test_the_text_report_says_it(self) -> None:
        from deadweight_semantic.run import Result
        text = Result(model="m", not_reviewed=list(self.FILES)).render()
        self.assertIn("4 instruction file(s) this layer does not collect were NOT reviewed", text)


class VoteOnQuotes(unittest.TestCase):
    """A vote counts for a finding only when it quotes the same passages (audit, 2026-10-08)."""

    A2 = {"file": "CLAUDE.md", "text": "Run `make test` before any change."}
    B2 = {"file": ".claude/skills/shop-i18n/SKILL.md", "text": "Translate the shop storefront."}

    def setUp(self) -> None:
        from deadweight_semantic.collect import Doc, Request
        a, b = TRUE_QUOTES
        self.texts = {a["file"]: a["text"] + "\n\n" + self.A2["text"], b["file"]: b["text"] + "\n\n" + self.B2["text"]}
        self.req = Request(("58", "59"), [Doc(f, "claims", t) for f, t in self.texts.items()], "topic")

    def confirm(self, answers: list[str], prompt: str = "p", stage=None):
        from unittest import mock
        from deadweight_semantic import claims, transport
        it = iter(answers)

        def ask(*a, **k):
            text = next(it)
            return transport.Answer("", 0.0, "m", text[len("ERROR:"):]) if text.startswith("ERROR:") \
                else transport.Answer(text, 0.0, "m")
        with mock.patch.object(transport, "ask", ask):
            return claims.confirm(self.req, prompt, "m", self.texts, stage or claims.Stage())

    @staticmethod
    def hit(*quotes) -> str:
        return json.dumps({"findings": [{"family": "58", "quotes": list(quotes), "explanation": "Two rules collide."}]})

    def test_three_different_contradictions_are_not_one_unanimous_one(self) -> None:
        a, b = TRUE_QUOTES
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
            kept = self.confirm([self.hit(a, b), self.hit(self.A2, self.B2), self.hit(a, self.B2)])[0]
        self.assertEqual(kept, [])

    def test_a_shorter_excerpt_of_the_same_passage_is_the_same_vote(self) -> None:
        a, b = TRUE_QUOTES
        short = {"file": b["file"], "text": "Edit `locales/fr.json` by hand"}
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
            kept = self.confirm([self.hit(a, b), self.hit(a, short), self.hit(a, b)])[0]
        self.assertEqual([f["votes"] for f in kept], [3])

    def run_orders(self, answers: list[str]) -> list[list[tuple]]:
        """The kept (votes, first quote) of every order of the answers."""
        import itertools
        out = []
        for order in itertools.permutations(range(len(answers))):
            with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
                kept = self.confirm([answers[i] for i in order])[0]
            out.append([(f["votes"], f["quotes"][0]["text"]) for f in kept])
        return out

    def paragraph(self) -> dict:
        from deadweight_semantic.collect import Doc, Request
        a, _ = TRUE_QUOTES
        full = {"file": a["file"], "text": a["text"] + " " + self.A2["text"]}
        self.texts = {a["file"]: full["text"], self.B2["file"]: self.texts[self.B2["file"]]}
        self.req = Request(("58", "59"), [Doc(f, "claims", t) for f, t in self.texts.items()], "topic")
        return full

    def test_the_order_of_the_answers_does_not_decide(self) -> None:
        # A fragment that every answer holds is kept in every order (audit externe 3, g9-03).
        a, b = TRUE_QUOTES
        full = self.paragraph()
        answers = [self.hit(full, b), self.hit(a, b), self.hit(a, b)]
        self.assertEqual(self.run_orders(answers), [[(3, a["text"])]] * 6)

    def test_a_broad_answer_does_not_bridge_two_narrow_findings(self) -> None:
        # The paragraph holds both sentences; each sentence came back in 2 answers of 3. Grouped
        # through any member, the three were one 3/3 contradiction (external audit 4, se-00).
        a, b = TRUE_QUOTES
        full = self.paragraph()
        answers = [self.hit(full, b), self.hit(a, b), self.hit(self.A2, b)]
        self.assertEqual(self.run_orders(answers), [[]] * 6)

    def test_two_unanimous_findings_stay_two(self) -> None:
        # Every answer gave both narrow findings, one also gave the paragraph: two findings with
        # 3 votes each, not one paragraph-sized one (external audit 4, se-00).
        a, b = TRUE_QUOTES
        full = self.paragraph()
        both = json.loads(self.hit(a, b))["findings"] + json.loads(self.hit(self.A2, b))["findings"]
        broad = json.loads(self.hit(full, b))["findings"]
        answers = [json.dumps({"findings": both}), json.dumps({"findings": both + broad}), json.dumps({"findings": both})]
        for got in self.run_orders(answers):
            self.assertEqual(sorted(got), sorted([(3, a["text"]), (3, self.A2["text"])]))

    def test_a_failed_vote_is_not_cached(self) -> None:
        from deadweight_semantic import claims
        a, b = TRUE_QUOTES
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
            failed = self.confirm(["ERROR: rate limited"] * 3)[0]
            stage = claims.Stage()
            later = self.confirm([self.hit(a, b)] * 3, stage=stage)[0]
        self.assertEqual(failed, [])
        self.assertEqual((stage.requests, stage.cached), (3, 0))
        self.assertEqual([f["votes"] for f in later], [3])


class MainIsLast(unittest.TestCase):
    def test_running_a_test_file_directly_runs_all_of_it(self) -> None:
        # unittest.main() exits: a class defined after it never ran when the file was run alone.
        import ast
        for f in sorted(HERE.glob("test_*.py")):
            body = ast.parse(f.read_text(encoding="utf-8")).body
            mains = [i for i, n in enumerate(body) if isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)]
            with self.subTest(f.name):
                self.assertIn(mains, ([], [len(body) - 1]))


if __name__ == "__main__":
    unittest.main()
