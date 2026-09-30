"""Twin skills and their division-of-responsibilities tables."""
from __future__ import annotations

import re
from pathlib import Path

from ..context import AuditContext
from ..repo import is_vendored_skill
from ..report import Report


DIVISION_HEADING_RE = re.compile(r"^#{1,6}\s+.*division of responsibilities", re.IGNORECASE | re.MULTILINE)


POINTER_RE = re.compile(r"→\s*([a-z0-9][a-z0-9-]*)")


DIVISION_OWNER_NOISE_RE = re.compile(r"`|\*\*|\(this skill\)|\(the (?:method|facts)\)|➜ See skill:")


DIVISION_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")


def division_table_rows(body: str) -> list[tuple[str, str]] | None:
    """Return (concern, owner) rows of the first Division of responsibilities table.

    None when the heading is absent. Concern and owner are normalised: whitespace
    collapsed, backticks, bold markers, `(this skill)` and `➜ See skill:` removed.
    The owner is the first token of the second cell, so `shop-ssr (this skill)` and
    `**shop-ssr**` both resolve to `shop-ssr`.
    """
    heading = DIVISION_HEADING_RE.search(body)
    if not heading:
        return None
    section = body[heading.end():]
    next_heading = re.search(r"^#{1,6}\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or DIVISION_SEPARATOR_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in {"concern", ""}:
            continue
        concern = " ".join(DIVISION_OWNER_NOISE_RE.sub("", cells[0]).split())
        owner_cell = DIVISION_OWNER_NOISE_RE.sub("", cells[1]).strip()
        owner = owner_cell.split()[0] if owner_cell else ""
        rows.append((concern, owner))
    return rows


# Measured 2026-09-27, 8 real twin pairs x 4 arms x 3 repetitions, 1,152 runs per model: adding
# the table to both bodies moved "the right skill was loaded" by -0.3 pts on Opus 5.5 (95% CI
# -3.8..+3.1) and +0.4 pts on Haiku 4.5 (-3.8..+4.6). The table sits in the body, read only
# after selection; it can only repair a wrong first pick, which was 3.5 % (Opus) and 8.8 %
# (Haiku) of runs - and it repaired none of them. NOTICE under every profile, until a second
# null measurement retires the check (evals/CONVENTIONS.md).
TWIN_TABLE_SEVERITY = "NOTICE"


def check_twin_division_tables(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """Mutually anti-triggering skills must both carry a division table that names the twin.

    Twin pairs are detected mechanically: A's description points at B with
    `→ B` and B's points back at A. Pointers naming an agent rather than a
    skill are ignored. Three things are asserted, each a NOTICE: the heading is
    present on both sides; each table has a row owned by the twin; and the
    concern text of the row naming the pair reads identically on both sides.
    The tables are family-wide, so their other rows may differ. A vendored
    skill cannot carry the heading in its upstream SKILL.md, so its
    references/ overlay counts too.
    """
    bodies: dict[str, str] = {}
    pointers: dict[str, set[str]] = {}
    for name, meta in skills.items():
        try:
            bodies[name] = Path(meta["path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        skill_dir = Path(meta["path"]).parent
        if is_vendored_skill(skill_dir):
            for overlay in sorted((skill_dir / "references").glob("*.md")):
                try:
                    bodies[name] += "\n" + overlay.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
        targets = {m.group(1) for m in POINTER_RE.finditer(meta.get("description", ""))}
        pointers[name] = targets & set(skills)

    pairs = sorted(
        {
            tuple(sorted((name, target)))
            for name, targets in pointers.items()
            for target in targets
            if target != name and name in pointers.get(target, set())
        }
    )
    tables = {name: division_table_rows(body) for name, body in bodies.items()}
    for first, second in pairs:
        for name, twin in ((first, second), (second, first)):
            if name not in bodies:
                continue
            rows = tables.get(name)
            if rows is None:
                # Only claim the twin documents the split when it does: with both sides
                # bare, "only '<twin>'" was printed for each side at once (2026-09-27).
                if tables.get(twin) is None:
                    consequence = f"and neither does '{twin}': no side documents the split"
                else:
                    consequence = f"so only '{twin}' documents the split"
                report.add(
                    "27-twin-division-table",
                    TWIN_TABLE_SEVERITY,
                    f"Twin pair '{first}' <-> '{second}': '{name}' has no "
                    f"'Division of responsibilities' heading, {consequence}.",
                    skills[name]["path"],
                )
                continue
            if not any(owner == twin for _, owner in rows):
                report.add(
                    "27-twin-division-row",
                    TWIN_TABLE_SEVERITY,
                    f"Twin pair '{first}' <-> '{second}': the table in '{name}' has no row owned by "
                    f"'{twin}', so a reader of '{name}' never learns what '{twin}' takes.",
                    skills[name]["path"],
                )
        first_rows, second_rows = tables.get(first), tables.get(second)
        if first_rows is None or second_rows is None:
            continue
        first_about_second = {c for c, o in first_rows if o == second}
        second_about_itself = {c for c, o in second_rows if o == second}
        second_about_first = {c for c, o in second_rows if o == first}
        first_about_itself = {c for c, o in first_rows if o == first}
        for reader, subject, seen, claimed in (
            (first, second, first_about_second, second_about_itself),
            (second, first, second_about_first, first_about_itself),
        ):
            if seen and claimed and not (seen & claimed):
                report.add(
                    "27-twin-division-text",
                    TWIN_TABLE_SEVERITY,
                    f"Twin pair '{first}' <-> '{second}': '{reader}' says '{subject}' owns "
                    f"'{sorted(seen)[0][:80]}' but '{subject}' words its own row as "
                    f"'{sorted(claimed)[0][:80]}'. The row naming the pair must read identically on both sides.",
                    skills[reader]["path"],
                )
