"""The overlay audits itself: every exemption has a reason and a date."""
from __future__ import annotations


from ..catalog import CHECK_ID_ALIASES, RETIRED_CHECK_IDS, known_check_ids
from ..context import AuditContext, STATE_DIR
from ..limits import ISO_DATE_RE
from ..overlay import DOWNGRADE_TO, UNEXEMPTABLE
from ..report import Report


def check_project_overlay(ctx: AuditContext, report: Report, local: dict) -> None:
    """The consuming project's overlay, audited by the plugin that reads it.

    The plugin cannot hold a project's decisions - it is the same bytes in every
    project that installs it. What it CAN hold is the schema and the detector. So
    the record lives in the project and the shape of the record is enforced here.

    An exemption without a reason is a decision nobody can review; an exemption
    without a date is a decision nobody can age out; an exemption whose path no
    longer exists is a claim about a file that is gone - the same defect as a dead
    anchor, caught by the same kind of check.
    """
    root = ctx.root
    path = root / STATE_DIR / "audit.local.json"
    if "__error__" in local:
        report.add("31-overlay-parse", "ERROR",
                   "audit.local.json is unreadable or is not valid JSON: no exemption is "
                   "applied, so unrelated checks below may fire.", str(path))
        return
    if not path.is_file():
        report.add("31-overlay", "INFO",
                   "No .claude/audit.local.json: this project grants no exemption. "
                   "Absent is a valid state - do not go looking for one.", str(path))
        return

    profile = local.get("profile")
    if profile is not None and str(profile).strip().lower() not in ("house", "doc"):
        # Any other value falls back to "doc" in main(), so a typo silently turns the
        # house conventions back into INFO - the opposite of what was written.
        report.add("31-overlay-schema", "WARN",
                   f'`profile` is `{profile}`; only "house" and "doc" are read, so this '
                   'overlay runs the default profile ("doc").', str(path))

    raw = local.get("exemptions")
    if raw is None:
        # An overlay that carries only `thresholds` is legitimate since 0.4.0, and
        # one that carries only `profile` since 0.10.0: a project may hold its own
        # doctrine number, or its severity profile, without granting any exemption.
        # 0.10.0 added `profile` and left this test alone, so a profile-only overlay
        # - exactly what the README suggests - was reported as an ERROR that "does
        # nothing". Every key that changes a run must be listed here.
        if local.get("thresholds") or profile is not None:
            return
        report.add("31-overlay-schema", "ERROR",
                   "audit.local.json has none of `exemptions`, `thresholds` or `profile`, "
                   'so it does nothing. Schema: {"profile": "house", "exemptions": '
                   '[{"check", "path", "reason", "date"}], "thresholds": {"<NAME>": '
                   '{"value", "reason", "date"}}}.', str(path))
        return
    if not isinstance(raw, list):
        report.add("31-overlay-schema", "ERROR",
                   "`exemptions` must be a list of objects.", str(path))
        return

    valid = known_check_ids()
    stale = 0
    for i, e in enumerate(raw):
        where = f"exemptions[{i}]"
        if not isinstance(e, dict):
            report.add("31-overlay-schema", "ERROR", f"{where} is not an object.", str(path))
            continue
        for key in ("check", "path", "reason", "date"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                report.add(
                    "31-overlay-schema", "ERROR",
                    f"{where} has no `{key}`. An exemption without a reason is a decision "
                    "nobody can review; without a date, one nobody can age out.", str(path))
        chk, pth = e.get("check"), e.get("path")
        if isinstance(chk, str) and chk in CHECK_ID_ALIASES:
            new = CHECK_ID_ALIASES[chk]
            # "Still works" next to the WARN below saying the entry is ignored told the
            # user both, and invited an update to an id ignored too (external audit 3, g8-03).
            tail = (f"`{new}` cannot be exempted (see the 31-overlay-schema finding on this "
                    "entry), so the entry has no effect under either id." if new in UNEXEMPTABLE
                    else "The old id still works and always will; update it when convenient.")
            report.add("31-overlay-alias", "NOTICE",
                       f"{where} names `{chk}`, renamed to `{new}`. {tail}", str(path))
            chk = CHECK_ID_ALIASES[chk]
        if isinstance(chk, str) and chk in RETIRED_CHECK_IDS:
            report.add("31-overlay-retired", "NOTICE",
                       f"{where} exempts `{chk}`, a check retired in {RETIRED_CHECK_IDS[chk]}. "
                       "It excuses nothing any more; remove the entry when convenient.", str(path))
        elif isinstance(chk, str) and valid and chk not in valid:
            report.add("31-overlay-unknown-check", "WARN",
                       f"{where} exempts `{chk}`, which this audit never emits. Stale entry, "
                       "or a typo that makes the exemption silently inert.", str(path))
        sev = e.get("severity")
        if sev is not None and (not isinstance(sev, str) or sev.upper() not in DOWNGRADE_TO):
            report.add("31-overlay-schema", "WARN",
                       f"{where} has severity `{sev}`, which is neither WARN nor INFO. An "
                       "exemption may lower a finding, never raise or invent one; this one "
                       "is ignored and the finding is dropped outright.", str(path))
        if isinstance(chk, str) and chk in UNEXEMPTABLE:
            report.add("31-overlay-schema", "WARN",
                       f"{where} exempts `{chk}`, which audits the overlay or the ratchet "
                       "itself. It is ignored: a valve that can disconnect its own gauge is "
                       "not a valve.", str(path))
        if isinstance(e.get("date"), str) and not ISO_DATE_RE.match(e["date"]):
            report.add("31-overlay-schema", "WARN",
                       f"{where} date `{e['date']}` is not YYYY-MM-DD.", str(path))
        if isinstance(pth, str) and pth:
            if not ((root / ctx.skills_dir / pth).exists() or (root / pth).exists()):
                stale += 1
                report.add("31-overlay-stale", "WARN",
                           f"{where} exempts `{pth}`, which no longer exists. A stale exemption "
                           "is a dead anchor in the overlay: drop it.", str(path))

    dates = sorted(e["date"] for e in raw
                   if isinstance(e, dict) and isinstance(e.get("date"), str)
                   and ISO_DATE_RE.match(e["date"]))
    oldest = f", oldest {dates[0]}" if dates else ""
    report.add("31-overlay", "INFO",
               f"Project overlay: {len(raw)} exemption(s){oldest}, {stale} stale. "
               "Each one is a check this project decided not to answer - review them as a "
               "list, not one at a time.", str(path))
