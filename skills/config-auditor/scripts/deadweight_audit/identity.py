"""The instrument's identity: which auditor produced a count.

A floor records the sha of the auditor that measured it, and `--check-floor` refuses to
compare counts taken by two different auditors (check 34). Until 0.21.0 the auditor was one
file and its sha was that file's. It is now a package, so the identity covers every module
of it - a change in any check changes the sha, and a floor taken before stops comparing.

What it covers is everything that can move a finding: the package's Python source, and
nothing else - no check reads the plugin's references at run time. `46-doctrine-copy`
did until 0.21.0, and a documentation page added to the plugin changed findings in
consuming projects under an unchanged sha; its vocabulary is now frozen in the package
(vocabulary/doctrine.py). A test holds that no module reads references/ again.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
SKILL_DIR = SCRIPTS_DIR.parent


def instrument_files() -> list[Path]:
    """The files that make the instrument: the entry point and every module of the package."""
    return [SCRIPTS_DIR / "audit.py"] + sorted(PACKAGE_DIR.rglob("*.py"))


def audit_sha() -> str:
    """Short sha of the auditor: relative paths and contents, line endings normalised.

    Line endings are normalised because git may check the same commit out with CRLF on
    Windows, and the same auditor must hash the same everywhere (a Windows runner found
    the difference on 2026-09-24). `__pycache__` is left out: only `*.py` is read.
    """
    h = hashlib.sha256()
    try:
        for f in instrument_files():
            h.update(f.relative_to(SCRIPTS_DIR).as_posix().encode("utf-8") + b"\0")
            h.update(f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    except OSError:
        return "unknown"
    return h.hexdigest()[:8]
