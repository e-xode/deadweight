"""The ratchet: counts frozen in `.claude/audit/floor.json`, compared on every run."""
from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

from .context import STATE_DIR
from .identity import audit_sha
from .report import Report


def floor_path(root: Path) -> Path:
    return root / STATE_DIR / "audit" / "floor.json"


def set_floor(root: Path, report: Report, layout: str) -> Path | None:
    """Freeze the current counts as the floor this configuration may not fall below."""
    counts = report.counts()
    # The floor carries the check ids, not just the counts. They were the only thing
    # the run-history file held that this one did not - and a committed floor beats a
    # jsonl series on every other axis: `git log -p` on this file is the same
    # trajectory, timestamped to the second, with an author and a reason. The measure
    # belongs to the script, the judgement to the commit message.
    data = {
        "date": _date.today().isoformat(),
        "layout": layout,
        "audit_sha": audit_sha(),
        "errors": counts.get("ERROR", 0),
        "warnings": counts.get("WARN", 0),
        "error_ids": sorted({f.check for f in report.findings if f.severity == "ERROR"}),
        "warning_ids": sorted({f.check for f in report.findings if f.severity == "WARN"}),
    }
    out = floor_path(root)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return None
    return out


def check_floor(root: Path, report: Report) -> int:
    """Compare against the frozen floor. Returns an exit code contribution.

    This is what turns a report into a ratchet. A measurement with no floor is a
    measurement people learn to ignore: the numbers move, nobody is accountable for
    the direction, and six months later the configuration has drifted with every
    individual step looking reasonable.

    The floor records the sha of this script, and the comparison REFUSES to run
    across a change of instrument. A count taken with a different auditor is not a
    worse or better state - it is a different measurement, and comparing the two
    silently is how an instrument change gets read as progress.
    """
    path = floor_path(root)
    if not path.is_file():
        report.add("34-floor", "NOTICE",
                   "No floor recorded. `--set-floor` freezes the current counts; until then "
                   "nothing stops the configuration from drifting upward.", str(path))
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        report.add("34-floor", "ERROR", "floor.json is unreadable or not valid JSON.", str(path))
        return 1
    counts = report.counts()
    err, warn = counts.get("ERROR", 0), counts.get("WARN", 0)
    f_err, f_warn = int(data.get("errors", 0)), int(data.get("warnings", 0))
    if data.get("audit_sha") != audit_sha():
        report.add("34-floor", "WARN",
                   f"Floor was set by auditor `{data.get('audit_sha')}`, this run is "
                   f"`{audit_sha()}`. Counts across two instruments are not comparable, "
                   f"so nothing is compared: now {err} error(s), {warn} warning(s), the "
                   f"floor said {f_err}/{f_warn}. Read them side by side, then re-set "
                   f"deliberately: `--set-floor`. A plugin release only reaches here when "
                   f"it changed the auditor itself - most releases do not.", str(path))
        return 0
    if err > f_err or warn > f_warn:
        report.add("34-floor", "ERROR",
                   f"Regression against the floor of {data.get('date')}: {err} error(s) / "
                   f"{warn} warning(s) against {f_err}/{f_warn}. Fix it, or raise the floor "
                   "on purpose and say why.", str(path))
        return 1
    if err < f_err or warn < f_warn:
        report.add("34-floor", "NOTICE",
                   f"Below the floor of {data.get('date')} ({err}/{warn} against "
                   f"{f_err}/{f_warn}). Lower it with `--set-floor` so the gain is kept.",
                   str(path))
    else:
        report.add("34-floor", "INFO",
                   f"At the floor of {data.get('date')} ({f_err} error(s), {f_warn} warning(s)).",
                   str(path))
    return 0
