"""Findings, the report that collects them, severities, and the text rendering."""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import CHECKS, SECURITY_CHECKS_EXTRA
from .context import AuditContext


# House conventions: choices this plugin makes that Anthropic does not document.
# Three families (evals/CONVENTIONS.md). A convention a MEASUREMENT supports is a
# WARN where that measurement applies. A convention Anthropic CONTRADICTS is checked
# on Anthropic's rule, and the house preference is a NOTICE. A convention with no
# source and no measurement is a NOTICE - unless the project opts into this plugin's
# conventions with `"profile": "house"` in its overlay. The same finding carries the
# documented alternative either way: the severity says whether there is a defect,
# the message says where the rule comes from.
def house(ctx: AuditContext) -> str:
    """Severity of a house convention with no source and no measurement."""
    return "WARN" if ctx.profile == "house" else "NOTICE"


HOUSE_MARKER = " House convention of this plugin: "


def house_note(convention: str, anthropic: str) -> str:
    return f"{HOUSE_MARKER}{convention}. Anthropic documents: {anthropic}."


SEVERITY_ORDER = {"OK": 0, "INFO": 1, "NOTICE": 2, "WARN": 3, "ERROR": 4}


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    location: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, check: str, severity: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(check, severity, message, location))

    def has_errors(self) -> bool:
        return any(f.severity == "ERROR" for f in self.findings)

    def counts(self) -> dict[str, int]:
        c = {"OK": 0, "INFO": 0, "NOTICE": 0, "WARN": 0, "ERROR": 0}
        for f in self.findings:
            c[f.severity] = c.get(f.severity, 0) + 1
        return c


# How many findings of one check the text report shows before rolling up the
# rest. A report that prints 188 dead anchors is not read: the reader learns
# the number, not the anchors, and pays 188 lines for it. The JSON output and
# the floor still carry every finding - this ceiling is a display decision, not
# a detection one, which is why it belongs here and not in a check.
ROLLUP_AFTER = 5


def print_text_report(report: Report, show_all: bool = False, profile: str = "doc") -> None:
    by_sev: dict[str, list[Finding]] = {"ERROR": [], "WARN": [], "NOTICE": [], "INFO": [], "OK": []}
    # Under the doc profile a house convention is not a defect, and on a sample of 150
    # public repositories (2026-09-27) it was most of what a reader saw: 423 notices
    # for one clause alone. Shown as one line; --all and --json keep every finding,
    # and the counts - which floors compare - are unchanged.
    house_counts: dict[str, int] = {}
    # The security family first, whatever its grade: a leaked key reads before a missing
    # description. Display only - the counts a floor compares are unchanged.
    security = [f for f in report.findings if f.check.startswith("50-security")
                or f.check in SECURITY_CHECKS_EXTRA]
    if security:
        print(f"\n=== SECURITY ({len(security)}) ===")
        for f in sorted(security, key=lambda x: -SEVERITY_ORDER.get(x.severity, 0)):
            loc = f" [{f.location}]" if f.location else ""
            print(f"  {f.severity} [{f.check}] {f.message}{loc}")
    for f in report.findings:
        if f in security:
            continue
        if (profile == "doc" and not show_all and f.severity == "NOTICE"
                and HOUSE_MARKER in f.message):
            house_counts[f.check] = house_counts.get(f.check, 0) + 1
            continue
        by_sev.setdefault(f.severity, []).append(f)
    for sev in ("ERROR", "WARN", "NOTICE", "INFO"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        extra = len(house_counts) and sum(house_counts.values()) if sev == "NOTICE" else 0
        print(f"\n=== {sev} ({len(items) + extra}) ===")
        seen: dict[str, int] = {}
        for f in items:
            seen[f.check] = seen.get(f.check, 0) + 1
            if not show_all and seen[f.check] > ROLLUP_AFTER:
                continue
            loc = f" [{f.location}]" if f.location else ""
            print(f"  [{f.check}] {f.message}{loc}")
        if not show_all:
            for chk, n in seen.items():
                if n > ROLLUP_AFTER:
                    print(f"  [{chk}] ... and {n - ROLLUP_AFTER} more of the same "
                          f"({n} total). Run with --all, or --json, to see them.")
        if sev == "NOTICE" and house_counts:
            detail = ", ".join(f"{c} x{n}" for c, n in sorted(house_counts.items()))
            print(f"  [house] {sum(house_counts.values())} notice(s) from this plugin's own conventions, "
                  f"not the documentation ({detail}). Run with --all to list them, or set "
                  "\"profile\": \"house\" in .claude/audit.local.json to adopt them.")
    if house_counts and not by_sev.get("NOTICE"):
        detail = ", ".join(f"{c} x{n}" for c, n in sorted(house_counts.items()))
        print(f"\n=== NOTICE ({sum(house_counts.values())}) ===")
        print(f"  [house] {sum(house_counts.values())} notice(s) from this plugin's own conventions, "
              f"not the documentation ({detail}). Run with --all to list them, or set "
              "\"profile\": \"house\" in .claude/audit.local.json to adopt them.")
    # Four severities, two kinds. ERROR, WARN and NOTICE each point at something in
    # this configuration; INFO is a measurement every run emits (the layout, the
    # budget, a coverage rate), so it never reaches zero and is never counted. The
    # last line is the one a model summarising this output repeats: it may say
    # "passed" only when nothing above points anywhere. Until 0.12.0 it said so over
    # 19 notices on one fleet repository, and the orchestrator relayed "0 error(s),
    # 0 warning(s)" as the whole audit.
    counts = report.counts()
    print(
        f"\nExecuted {len(CHECKS)} check groups. "
        f"Summary: {counts['ERROR']} error(s), {counts['WARN']} warning(s), "
        f"{counts['NOTICE']} notice(s)."
    )
    if not report.has_errors() and counts["WARN"] == 0:
        if counts["NOTICE"]:
            print(f"No error or warning. {counts['NOTICE']} notice(s) above: report them "
                  "too - each one names a file, and none is a clean bill.")
        else:
            print("All checks passed.")
    if counts["INFO"]:
        print(f"{counts['INFO']} measurement(s) (INFO) above are not findings: give their count "
              "and offer to show them.")
