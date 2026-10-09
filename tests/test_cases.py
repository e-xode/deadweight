"""Replay the labelled cases of `cases.json` against the auditor.

    python3 -m unittest discover -s tests

Each case is written to a temporary directory and audited IN-PROCESS, one after the
other: besides the expected counts, this holds that one audit leaves nothing behind for
the next - the state of an audit lives in its AuditContext, not in the module.
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
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402

CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]


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
                if case.get("known_failure"):
                    continue                      # a known defect: kept to be seen, not to fail
                self.assertEqual(crashed, [], "a check crashed")
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


if __name__ == "__main__":
    unittest.main()
