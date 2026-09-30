"""The project overlay, `.claude/audit.local.json`: exemptions and threshold overrides."""
from __future__ import annotations

import json
from pathlib import Path

from .catalog import CHECK_ID_ALIASES
from .context import AuditContext, STATE_DIR
from .limits import ISO_DATE_RE, MECHANISM_THRESHOLDS, OVERRIDABLE_THRESHOLDS
from .report import Finding, Report


def load_local_config(root: Path) -> dict:
    """The project's overlay. The ONLY thing that may differ between projects.

    `<root>/.claude/audit.local.json`. It lives in the PROJECT, never beside this
    script: shipped as a plugin, this file sits in a version-stamped cache directory
    that is replaced on every update, so anything written next to it is lost.

    Schema:

        {"exemptions": [
            {"check": "11-english-only",
             "path":  "translate/references/glossary.md",
             "reason": "FR/EN glossary, bilingual by nature",
             "date":  "2026-09-22"}]}

    `reason` and `date` are not decoration and not optional. A bare list of exempt
    paths is amnesia: six months on nobody knows why an entry is there, so nobody
    dares remove it, so the list only ever grows - a ratchet pointing the wrong way.
    Carrying the reason puts the decision at the exact place the model looks when
    the check fires, which is why this project needs no separate decision document
    for the ordinary case. Check 31 enforces the shape.

    Absent, unreadable or malformed: no exemption, and the audit says so.
    """
    path = root / STATE_DIR / "audit.local.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {"__error__": str(path)}


def apply_thresholds(ctx: AuditContext, report: Report) -> None:
    """Let a project hold its own number for a DOCTRINE threshold, and say so.

    Schema, in `<project>/.claude/audit.local.json`:

        {"thresholds": {"CLAUDE_MD_MAX_BYTES":
            {"value": 13312, "reason": "ops repository, all hard rules", "date": "2026-09-22"}}}

    `reason` and `date` are required for exactly the same cause as on an
    exemption: a bare number is amnesia. Six months on nobody knows why the
    ceiling is 13 KB, so nobody dares lower it, and the dial only ever turns one
    way.

    Every applied override is reported as INFO on every run. An override nobody
    sees is a doctrine quietly rewritten; one that prints itself is a decision
    anyone can re-open.
    """
    # An unknown key was ignored in silence, so a project writing `thresholds`
    # against an older release got no signal and wondered why nothing moved. A
    # configuration file that accepts everything and applies part of it is worse
    # than one that refuses.
    local = ctx.local
    known = {"exemptions", "thresholds", "profile", "_comment"}
    for k in sorted(set(local) - known):
        report.add("31-overlay-unknown", "WARN",
                   f"`{k}` is not a key this audit reads, so it does nothing. Known keys: "
                   f"{', '.join(sorted(known - {'_comment'}))}.", "")
    over = local.get("thresholds")
    if not isinstance(over, dict):
        return
    for name in sorted(over):
        spec = over[name]
        if name in MECHANISM_THRESHOLDS:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{name}` cannot be overridden: {MECHANISM_THRESHOLDS[name]}. "
                       "Moving this number changes what the audit says, not what the harness "
                       "does.", "")
            continue
        if name not in OVERRIDABLE_THRESHOLDS:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{name}` is not a threshold this audit recognises. Known overridable "
                       f"thresholds: {', '.join(sorted(OVERRIDABLE_THRESHOLDS))}.", "")
            continue
        if not isinstance(spec, dict) or "value" not in spec:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{name}` must be an object with `value`, `reason` and `date`.", "")
            continue
        missing = [k for k in ("reason", "date") if not str(spec.get(k, "")).strip()]
        if missing:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{name}` overrides a doctrine threshold without {' and '.join(missing)}. "
                       "A number with no reason is a number nobody dares change back.", "")
            continue
        if not ISO_DATE_RE.match(str(spec["date"])):
            report.add("31-overlay-threshold", "ERROR",
                       f"`{name}`: `date` must be YYYY-MM-DD.", "")
            continue
        previous = getattr(ctx.limits, name)
        try:
            value = type(previous)(spec["value"])
        except (TypeError, ValueError):
            report.add("31-overlay-threshold", "ERROR",
                       f"`{name}`: `value` is not a {type(previous).__name__}.", "")
            continue
        setattr(ctx.limits, name, value)
        report.add("31-overlay-threshold", "INFO",
                   f"`{name}` {previous} -> {value}, on this project's authority "
                   f"({spec['date']}): {spec['reason']}", "")


# An exemption may never silence the checks that audit the exemptions, nor the
# ratchet. A release valve able to disconnect its own pressure gauge is not a
# valve: it is a way of not knowing.
UNEXEMPTABLE = frozenset({
    "31-overlay", "31-overlay-parse", "31-overlay-schema", "31-overlay-stale",
    "31-overlay-alias", "31-overlay-unknown-check", "31-overlay-threshold",
    "31-overlay-unused",
    "34-audit-sha", "00-layout",
})


DOWNGRADE_TO = ("WARN", "NOTICE", "INFO")


def apply_overlay(ctx: AuditContext, report: "Report", local: dict) -> None:
    """Drop or downgrade findings the project has formally excused.

    Until 2026-09-22 the overlay reached exactly one check, `11-english-only`:
    an exemption written for any other id was schema-checked, counted in the
    summary, and applied to nothing. Nobody had been bitten because nobody had
    written one - the only exemption anyone wrote was the one that worked.

    `severity` is the addition that makes the file worth writing: without it an
    exemption erases the finding, and the project loses the count it excused.
    With it, the finding stays visible at a severity that does not fail CI, and
    `--check-floor` still watches it grow.
    """
    root = ctx.root
    raw = local.get("exemptions")
    entries = list(enumerate(raw)) if isinstance(raw, list) else []
    entries = [(i, e) for i, e in entries if isinstance(e, dict)]
    if not entries:
        return
    resolved_links: list[tuple[str, Path, str | None, int]] = []
    for i, e in entries:
        chk = CHECK_ID_ALIASES.get(e.get("check"), e.get("check"))
        pth = e.get("path")
        if not isinstance(chk, str) or not isinstance(pth, str) or not pth:
            continue
        if chk in UNEXEMPTABLE:
            continue
        sev = e.get("severity")
        sev = sev if isinstance(sev, str) and sev.upper() in DOWNGRADE_TO else None
        for base in (root / ctx.skills_dir / pth, root / pth):
            if base.exists():
                resolved_links.append((chk, base.resolve(), sev and sev.upper(), i))
                break
    if not resolved_links:
        return
    served: set[int] = set()
    retained: list[Finding] = []
    for f in report.findings:
        target = None
        if f.location:
            try:
                target = Path(f.location).resolve()
            except OSError:
                target = None
        match = next(
            ((sev, i) for chk, base, sev, i in resolved_links
             if chk == f.check and target is not None
             and (target == base or base in target.parents)),
            None)
        if match is None:
            retained.append(f)
            continue
        covered_by, i = match
        served.add(i)
        if covered_by is not None:
            retained.append(Finding(f.check, covered_by, f.message + " [excused by overlay]",
                                   f.location))
    report.findings = retained
    # An exemption that excused nothing on this run. Check 31 already catches an
    # unknown check id and a vanished path; it did not catch the third way an
    # exemption dies - the check still exists, the file still exists, but the
    # auditor stopped firing there (0.10.0 fixed false positives in 22, 28 and 33).
    # Such an entry is harmless today and dangerous later: the day a REAL defect of
    # that check appears under that path, it is hidden without anyone deciding so.
    # INFO, not WARN: a check that only fires in some runs (a threshold, a layout)
    # can leave an exemption idle legitimately.
    overlay = str(root / STATE_DIR / "audit.local.json")
    for chk, _base, _sev, i in resolved_links:
        if i not in served:
            e = raw[i]
            report.add("31-overlay-unused", "NOTICE",
                       f"exemptions[{i}] (`{chk}` on `{e.get('path')}`, {e.get('date')}) "
                       "excused nothing in this run: the finding it was written for is gone. "
                       "Drop it, so it cannot hide a new defect of the same check there.",
                       overlay)
