"""Replay the labelled cases of `cases/*.json` and `cases.d/*.json` against the auditor.

    python3 -m unittest discover -s tests

Each case is written to a temporary directory and audited IN-PROCESS, one after the
other: besides the expected counts, this holds that one audit leaves nothing behind for
the next - the state of an audit lives in its AuditContext, not in the module.

`cases/*.json` is generated from the maintainer's source and must not be edited by hand - one
file per check family, each kept under the plugin directory's 256 KiB per-file limit;
`cases.d/*.json` holds contributed cases in the same format, replayed the same way.
See CONTRIBUTING.md, "Add a labelled case".
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402



def load_cases(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))["cases"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{path.name}: not a {{\"cases\": [...]}} file ({exc})") from exc


GENERATED = [case for f in sorted((HERE / "cases").glob("*.json")) for case in load_cases(f)]
CONTRIBUTED = {f.name: load_cases(f) for f in sorted((HERE / "cases.d").glob("*.json"))}
CASES = GENERATED + [case for cases in CONTRIBUTED.values() for case in cases]


def audit(root: Path, *opts: str) -> dict:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["--root", str(root), "--json", "--all", *opts])
    return json.loads(out.getvalue())


def case_sensitive(tmp: str) -> bool:
    """Whether this filesystem keeps `a` and `A` apart: macOS and Windows do not by default."""
    probe = Path(tmp) / "case-probe"
    probe.write_bytes(b"")
    try:
        return not (Path(tmp) / "CASE-PROBE").exists()
    finally:
        probe.unlink()


def build(case: dict, tmp: str) -> Path:
    root = Path(tmp) / "shop-api"
    for rel, content in case["files"].items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(content.encode("utf-8"))   # the same bytes on Windows: no newline translation
    root.mkdir(parents=True, exist_ok=True)
    for rel, target in case.get("links", {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        # As git creates it: native separators - on Windows a relative target written with `/`
        # does not resolve (found by CI, 2026-09-30) - and a directory link for a directory.
        native = os.path.normpath(target) if not target.startswith("/") else target
        os.symlink(native, root / rel,
                   target_is_directory=((root / rel).parent / native).is_dir())
    if case.get("gitignore"):
        (root / ".gitignore").write_bytes(case["gitignore"].encode("utf-8"))
    if case.get("git"):
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


class LabelledCases(unittest.TestCase):
    def test_cases(self) -> None:
        for case in CASES:
            with self.subTest(case["id"]), tempfile.TemporaryDirectory() as tmp:
                if case.get("case_sensitive_fs") and not case_sensitive(tmp):
                    continue                          # two names differing by case cannot both exist here
                if case.get("needs_exec_bit") and sys.platform == "win32":
                    continue                          # no execute bit on Windows: os.access(X_OK) is always true
                try:
                    root = build(case, tmp)
                except OSError as exc:            # symlinks need a privilege on Windows
                    self.skipTest(f"{case['id']}: {exc}")
                opts = []
                if case.get("runtime"):           # an InstructionsLoaded log, paths made absolute
                    log = Path(tmp) / "loads.jsonl"
                    log.write_bytes("".join(json.dumps({
                        "hook_event_name": "InstructionsLoaded", "file_path": str(root / e["file"]),
                        **{k: v for k, v in e.items() if k != "file"}}) + "\n"
                        for e in case["runtime"]).encode("utf-8"))
                    opts = ["--runtime", str(log)]
                report = audit(root, *opts)
                findings = report["findings"]
                crashed = [f["message"] for f in findings if f["check"] == "00-check-crashed"]
                seen = Counter((f["check"], f["severity"]) for f in findings)
                gaps = [f"{c} {s}: expected {n}, got {seen.get((c, s), 0)}"
                        for c, s, n in case["expected"] if seen.get((c, s), 0) != n]
                for check, pattern in case.get("forbidden_messages", []):
                    gaps += [f"{check}: forbidden message /{pattern}/"
                             for f in findings if f["check"] == check and re.search(pattern, f["message"])]
                self.assertEqual(crashed, [], "a check crashed")   # a known failure may not crash
                if case.get("known_failure") is True:
                    # A known defect: replayed and reported as a skip with its gaps, so every run
                    # shows it ("OK (skipped=N)", and each one under -v). One that starts passing
                    # fails, as an unexpected success would: drop its flag.
                    self.assertNotEqual(gaps, [], f"{case['id']}: known_failure case now passes - "
                                                  "remove \"known_failure\"")
                    self.skipTest(f"known failure {case['id']}: " + "; ".join(gaps))
                self.assertEqual(gaps, [])

    def test_a_check_held_silent_is_also_seen_firing(self) -> None:
        # A case expecting 0 also passes when the check never fires at all: with 13 such checks
        # switched off, every test still passed (audit, 2026-10-08). So a check with a zero case
        # needs a case where it fires - unless it is retired, or is the crash report.
        from deadweight_audit.catalog import RETIRED_CHECK_IDS
        firing = {c for case in CASES for c, _s, n in case["expected"] if n > 0}
        silent = {c for case in CASES for c, _s, n in case["expected"] if n == 0}
        exempt = set(RETIRED_CHECK_IDS) | {"00-check-crashed"}
        self.assertEqual(sorted(silent - firing - exempt), [])

    # Ids the auditor emits but that no labelled case fires, each with the test that holds it.
    # Empty means every emitted id has a case. An entry needs its reason; none is kept for lack of time.
    NOT_FIRED_BY_A_CASE: dict[str, str] = {
        # A case is one audit without --check-floor: the ratchet only runs under that flag.
        "34-floor": "test_overlay_floor_crash.FloorTest.test_a_swapped_warning_id_is_reported",
        # A case that crashes a check fails test_cases by design: the crash is forced by a mock.
        "00-check-crashed": "test_overlay_floor_crash.CrashTest.test_no_skill_count_after_check_skills_crashed",
        # The corpus format cannot write file permissions: the file is made unreadable here.
        "38-unreadable": "test_cases.UnreadableFile.test_a_file_that_cannot_be_opened_is_reported",
    }

    def test_every_emitted_id_is_seen_firing(self) -> None:
        # The guard above only sees ids a case already names. An id no case names - 17 of 126 on
        # 0.25.0 - passed unseen: switched off, every test still passed. Read the ids from the code.
        firing = {c for case in CASES for c, _s, n in case["expected"] if n > 0}
        self.assertEqual(sorted(emitted_ids() - firing - set(self.NOT_FIRED_BY_A_CASE)), [])


def emitted_ids() -> set[str]:
    """Ids passed literally to `report.add` anywhere in the auditor's source."""
    import ast
    from deadweight_audit.identity import instrument_files
    emitted = set()
    for f in instrument_files():
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add" \
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                emitted.add(n.args[0].value)
    return emitted


REQUIRED_KEYS = {"id", "files", "git", "expected"}
OPTIONAL_KEYS = {"forbidden_messages", "gitignore", "runtime", "links", "needs_exec_bit",
                 "case_sensitive_fs", "known_failure"}
# A public file must not carry the machine or the people it was written from. The private
# release gate reads the real names; this is the part that can be checked in the open.
FICTIONAL = re.compile(r"(shop|ui|api|data)-[\w.-]*|dev|user|a")
LEAKS = (
    ("a home folder that is not a fictional name",
     re.compile(r"(?:/home/|/Users/|[A-Za-z]:\\\\Users\\\\|~/workspace/)([^/\\\s\"`*]+)")),
    ("an email address outside the reserved example domains",
     re.compile(r"[\w.+-]+@([a-z][a-z0-9-]*(?:\.[a-z0-9-]+)*\.[a-z]{2,})\b", re.I)),
    ("a token in a real provider format",
     re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|sk-ant-[\w-]{10,}|AKIA[0-9A-Z]{16}"
                r"|xox[abprs]-[\w-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY)")),
)
SAFE_EMAIL_DOMAIN = re.compile(r"(^|\.)(example\.(com|org|net)|example|test|invalid|localhost)$", re.I)
# `n@AGENTS.md` is an instruction file, not an address: a file-extension "domain" is exempt
# only when its first label is an upper-case file name and the extension lower-case. `.md`,
# `.sh` and `.py` are also country domains (Moldova, Saint Helena, Paraguay): `jdoe@acme.sh`
# and `ceo@bigcorp.md` are addresses.
FILE_NAME_DOMAIN = re.compile(r"[A-Z][A-Z0-9_]*(\.[\w-]+)*\.(md|json|py|sh|txt|ya?ml|toml)")


def leaks(text: str) -> list[str]:
    found = []
    for what, rx in LEAKS:
        for m in rx.finditer(text):
            name = m.group(1)
            if what.startswith("a home") and FICTIONAL.fullmatch(name):
                continue
            if what.startswith("an email") and (SAFE_EMAIL_DOMAIN.search(name)
                                                 or FILE_NAME_DOMAIN.fullmatch(name)):
                continue
            found.append(f"{what}: {m.group(0)!r}")
    return found


def known_ids() -> set[str]:
    from deadweight_audit.catalog import known_check_ids
    # known_check_ids() reads double-quoted "NN[a-z]-name" ids by regex; the ids passed to
    # report.add (AST) add any it would miss - single quotes, another shape. None today.
    return known_check_ids() | emitted_ids()


def format_problems(case: object, known: set[str]) -> list[str]:
    """What is wrong with one contributed case, as messages; [] when it is well formed."""
    from deadweight_audit.report import SEVERITY_ORDER
    if not isinstance(case, dict):
        return ["a case is an object"]
    problems = []
    missing, unknown = sorted(REQUIRED_KEYS - set(case)), sorted(set(case) - REQUIRED_KEYS - OPTIONAL_KEYS)
    if missing:
        return [f"missing keys: {missing}"]
    if unknown:
        problems.append(f"unknown keys: {unknown}")
    if not isinstance(case["id"], str):
        problems.append("id must be a string")
    if not isinstance(case["git"], bool):
        problems.append("git must be true or false")
    if not isinstance(case["files"], dict) or not all(isinstance(v, str) for v in case["files"].values()):
        return problems + ["files: an object of path -> string content"]
    if not case["expected"]:
        problems.append("a case expects at least one count")
    for item in case["expected"]:
        if not (isinstance(item, list) and len(item) == 3):
            problems.append(f"not [check, severity, n]: {item}")
            continue
        check, severity, n = item
        if check not in known:
            problems.append(f"expected: a check id the auditor does not emit: {check}")
        if severity not in SEVERITY_ORDER:
            problems.append(f"expected: unknown severity {severity!r}")
        if not (isinstance(n, int) and not isinstance(n, bool) and n >= 0):
            problems.append(f"expected: count {n!r}")
    forbidden = case.get("forbidden_messages", [])
    for item in forbidden if isinstance(forbidden, list) else [forbidden]:
        if not (isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item)):
            problems.append(f"forbidden_messages: not [check, regex]: {item}")
            continue
        if item[0] not in known:
            problems.append(f"forbidden_messages: check id the auditor does not emit: {item[0]}")
        try:
            re.compile(item[1])
        except re.error as exc:
            problems.append(f"forbidden_messages: bad regex {item[1]!r}: {exc}")
    for flag in ("known_failure", "needs_exec_bit", "case_sensitive_fs"):
        if flag in case and not isinstance(case[flag], bool):
            problems.append(f"{flag} must be true or false, not {case[flag]!r}")
    if not isinstance(case.get("gitignore", ""), str):
        problems.append("gitignore must be a string")
    links = case.get("links", {})
    if not (isinstance(links, dict) and all(isinstance(v, str) for v in links.values())):
        problems.append("links must be an object of path -> target")
        links = {}
    runtime = case.get("runtime", [])
    if not (isinstance(runtime, list) and all(isinstance(e, dict) and isinstance(e.get("file"), str)
                                              for e in runtime)):
        problems.append("runtime must be a list of {\"file\": ...} events")
    for rel in [*case["files"], *links]:
        parts = rel.replace("\\", "/").split("/")
        if rel.startswith(("/", "\\")) or re.match(r"[A-Za-z]:", rel) or ".." in parts:
            problems.append(f"path must stay inside the case: {rel}")
    problems += leaks(json.dumps(case, ensure_ascii=False))
    return problems


class ContributedCaseFormat(unittest.TestCase):
    """What `cases.d/*.json` must hold. The replay above says whether a case passes; this says
    whether it is a case at all - a key spelt wrong would otherwise be silently ignored."""

    def test_every_contributed_case_is_well_formed(self) -> None:
        known = known_ids()
        for name, cases in CONTRIBUTED.items():
            for i, case in enumerate(cases):
                with self.subTest(f"{name} #{i} {case.get('id', '?') if isinstance(case, dict) else '?'}"):
                    self.assertEqual(format_problems(case, known), [])

    def test_the_format_check_refuses_what_would_silently_check_nothing(self) -> None:
        # Negative controls: each broken field must be named, or a typo turns an assertion off.
        known = known_ids()
        good = {"id": "contrib-format", "files": {"CLAUDE.md": "# shop-api\n"}, "git": True,
                "expected": [["19-frontmatter-quoting", "WARN", 0]]}
        self.assertEqual(format_problems(good, known), [])
        broken = {
            "forbidden_messages": ([["28-skill-anchor", "refund"]], "forbidden_messages: check id"),
            "known_failure": ("no", "known_failure must be true or false"),
            "needs_exec_bit": (1, "needs_exec_bit must be true or false"),
            "case_sensitive_fs": ("yes", "case_sensitive_fs must be true or false"),
            "runtime": ([{"path": "x"}], "runtime"),
            "links": (["a"], "links"),
            "gitignore": (["*.log"], "gitignore"),
        }
        for key, (value, message) in broken.items():
            with self.subTest(key):
                problems = format_problems({**good, key: value}, known)
                self.assertTrue(any(message in p for p in problems), problems)
        bad_regex = format_problems({**good, "forbidden_messages": [["28-skill-anchors", "("]]}, known)
        self.assertTrue(any("bad regex" in p for p in bad_regex), bad_regex)
        typo = format_problems({**good, "forbiden_messages": []}, known)
        self.assertTrue(any("unknown keys" in p for p in typo), typo)

    def test_the_generated_cases_are_there(self) -> None:
        # An empty or missing `cases/` folder would replay nothing and pass every test above.
        self.assertGreater(len(GENERATED), 0, "tests/cases/*.json holds no case")

    def test_case_ids_are_unique_across_both_sources(self) -> None:
        seen = Counter(case.get("id") for case in CASES)
        self.assertEqual(sorted(i for i, n in seen.items() if n > 1), [])

    def test_the_leak_patterns_catch_what_they_name(self) -> None:
        # Negative control: a pattern that matches nothing passes every file.
        for text in ("/home/jdoe/src", "~/workspace/acme-portal", "C:\\\\Users\\\\jdoe",
                     "ops@acme-corp.com", "Ops@Acme-Corp.COM", "ghp_" + "a" * 36, "AKIA" + "A" * 16,
                     "jdoe@acme.sh", "ceo@bigcorp.md", "x@company.com.py", "ops@shop-corp.json"):
            self.assertNotEqual(leaks(text), [], text)
        for text in ("/home/shop-author/x", "/home/dev/x", "~/workspace/shop-docs/a.md",
                     "refunds@shop.example.com", "n@AGENTS.md", "n@AGENTS.override.md",
                     "shop-db-mcp@1.4.2",
                     "Bearer xxxxxxxxxxxxxxxxxxxxxxxx"):
            self.assertEqual(leaks(text), [], text)


class KnownFailureIsVisible(unittest.TestCase):
    """A known_failure case is reported as a skip naming its gaps; one that passes fails."""

    def replay(self, *cases: dict) -> unittest.TestResult:
        result = unittest.TestResult()
        with unittest.mock.patch(f"{__name__}.CASES", list(cases)):
            LabelledCases("test_cases").run(result)
        return result

    BASE = {"files": {"CLAUDE.md": "# shop-api\n\nRun `make test` before any change.\n"},
            "git": False, "known_failure": True}

    def test_a_known_failure_is_a_skip_with_its_gaps(self) -> None:
        result = self.replay({**self.BASE, "id": "contrib-known-gap",
                              "expected": [["01-claude-md-exists", "INFO", 7]]})
        self.assertEqual((result.failures, result.errors), ([], []))
        reasons = [reason for _test, reason in result.skipped]
        self.assertTrue(any("contrib-known-gap" in r and "01-claude-md-exists INFO: expected 7" in r
                            for r in reasons), reasons)

    def test_a_crash_in_a_known_failure_fails(self) -> None:
        from deadweight_audit import registry
        boom = unittest.mock.Mock(side_effect=RuntimeError("forced"))
        boom.__name__ = "check_skills"
        with unittest.mock.patch.object(registry, "check_skills", boom):
            result = self.replay({**self.BASE, "id": "contrib-known-crash",
                                  "expected": [["01-claude-md-exists", "INFO", 7]]})
        self.assertEqual(len(result.failures), 1, result.skipped)
        self.assertIn("a check crashed", result.failures[0][1])

    def test_a_known_failure_that_passes_fails(self) -> None:
        result = self.replay({**self.BASE, "id": "contrib-known-fixed",
                              "expected": [["19-frontmatter-quoting", "WARN", 0]]})
        self.assertEqual(len(result.failures), 1)
        self.assertIn("now passes", result.failures[0][1])


class UnreadableFile(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "chmod 000 does not stop Windows or root from reading")
    def test_a_file_that_cannot_be_opened_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rules = Path(tmp) / ".claude" / "rules"
            rules.mkdir(parents=True)
            (rules / "shop-api.md").write_text("Run `make test` before any change.\n", encoding="utf-8")
            (rules / "shop-ui.md").write_text("Keep components under 200 lines.\n", encoding="utf-8")
            (rules / "shop-api.md").chmod(0)
            try:
                findings = audit(Path(tmp))["findings"]
            finally:
                (rules / "shop-api.md").chmod(0o600)
        hits = [f for f in findings if f["check"] == "38-unreadable"]
        self.assertEqual([(f["severity"], "shop-api.md" in f["message"], "shop-ui.md" in f["message"]) for f in hits],
                         [("WARN", True, False)])


if __name__ == "__main__":
    unittest.main()
