"""Evals: schema, coverage, and what a case can actually judge."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..context import AuditContext
from ..parsing.frontmatter import parse_frontmatter
from ..repo import readable_files
from ..report import Report, house, house_note


# Not `expectations`: skill-creator saves evals.json with "just the prompts" and drafts
# the assertions while the first runs go (skill-creator SKILL.md, "Don't write assertions
# yet"). Requiring them gave 20 ERRORs to a suite at that step (public sample, 2026-09-27).
EVALS_REQUIRED_KEYS = ("id", "prompt", "expected_output")


EVALS_ANTI_NAME_TOKENS = ("anti-trigger", "not-trigger", "should-not", "defer", "negative", "near-miss")


EVALS_ANTI_EXPECTATION_TOKENS = ("defer", "does not trigger", "should not")


def looks_like_anti_trigger(case: dict) -> bool:
    label = f"{case.get('id', '')} {case.get('name', '')}".lower()
    if any(token in label for token in EVALS_ANTI_NAME_TOKENS):
        return True
    expectations = case.get("expectations")
    if isinstance(expectations, list):
        for expectation in expectations:
            lowered = str(expectation).lower()
            if any(token in lowered for token in EVALS_ANTI_EXPECTATION_TOKENS):
                return True
    return False


# Wording that states a mechanical fact about the run: whether a tool was called.
# `tool_used` answers it exactly; an llm grader reads the last message and may not
# see the trajectory at all. Measured on this plugin 2026-09-22: a rubric opening
# with "The run must load the `config-auditor` skill" passed 3 runs out of 5 in
# which the skill was never loaded. The judge was not capricious - it was blind.
JUDGED_FACT_RE = re.compile(
    r"must (?:not |NOT )?(?:load|call|invoke|use) ", re.IGNORECASE
)


def eval_case_dirs(root: Path) -> list[Path]:
    """Case directories `claude plugin eval` would run: `evals/**/case.yaml or prompt.md`.

    At any depth, as the harness globs. Until 0.14.0 only `evals/<case>/` was read, so a
    suite grouped as `evals/<skill>/<case>/` - a layout the harness runs - was invisible
    to both this check and the coverage figure. `results/` holds run transcripts, not
    cases, and a folder inside a case (its fixture, its graders) is not another case.
    """
    base = root / "evals"
    if not base.is_dir():
        return []
    found: list[Path] = []
    for marker in sorted(list(base.rglob("case.yaml")) + list(base.rglob("prompt.md"))):
        case = marker.parent
        rel = case.relative_to(base).parts
        if not rel or rel[0] == "results" or any(x.startswith(".") for x in rel):
            continue
        if case not in found:
            found.append(case)
    return [c for c in found if not any(o != c and o in c.parents for o in found)]


def skills_of_case(case: Path, base: Path, names: list[str]) -> set[str]:
    """The skills a case exercises, read from the case rather than guessed from the layout.

    First the `tool_used` graders on `Skill`: their `input_match` names the skill the run
    must (or must not) load, which is what a coverage figure is about. Then, for a case
    with no such grader, a path segment under `evals/` equal to a skill name. A case
    that names none is attributed to nobody - it proves nothing about any one skill.
    """
    named: set[str] = set()
    gdir = case / "graders"
    for g in readable_files(gdir.glob("*.md")) if gdir.is_dir() else []:
        try:
            fm, _ = parse_frontmatter(g.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        fm = fm or {}
        if fm.get("type") != "tool_used" or fm.get("tool") != "Skill" or not fm.get("input_match"):
            continue
        try:
            rx = re.compile(str(fm["input_match"]))
        except re.error:
            continue
        named |= {n for n in names
                  if rx.search(f'"skill": "{n}"') or rx.search(f'"skill":"{n}"')
                  or rx.search(f'"skill": "plugin:{n}"')}
    if not named:
        named = {part for part in case.relative_to(base).parts if part in names}
    return named


def check_eval_quality(ctx: AuditContext, report: Report) -> None:
    """Whether a suite can fail - not whether it is well formed.

    Check 26 says the suite parses. These three say it measures something. All
    three come from defects found by hand on this plugin's own suite on
    2026-09-22, each of which check 26 declared sound:

    - a fact entrusted to a judge who cannot see it (the judge passed runs in
      which the skill was never loaded);
    - a case whose every grader is an opinion, so nothing about it is exact;
    - a suite with no fixture, whose cases ask about files that do not exist.
    """
    root = ctx.root
    case_dirs = eval_case_dirs(root)
    if not case_dirs:
        return
    without_fixture = 0
    for folder in case_dirs:
        types: list[str] = []
        headings: list[str] = []
        gdir = folder / "graders"
        if gdir.is_dir():
            for g in readable_files(gdir.glob("*.md")):
                try:
                    raw_text = g.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                # parse_frontmatter returns (fields, end line), not a body: the rubric
                # is what follows, and searching the whole file is equivalent here
                # because no frontmatter key carries that wording.
                fm, _ = parse_frontmatter(raw_text)
                t = str((fm or {}).get("type", ""))
                types.append(t)
                if t == "llm":
                    headings.append(raw_text)
        if not types:
            continue
        mechanical = [t for t in types if t != "llm" and t != "baseline"]
        judged_fact = any(JUDGED_FACT_RE.search(r) for r in headings)
        if judged_fact and not any(t == "tool_used" for t in types):
            report.add(
                "39-eval-judged-fact",
                "WARN",
                f"Case '{folder.name}': an llm rubric states a fact about the run "
                "(\"must load\" / \"must not call\") and the case carries no `tool_used` "
                "grader. The judge reads the last message, not the trajectory, so it can "
                "pass a run that did the opposite. Add `type: tool_used` with `tool: Skill` "
                "(and `min: 0`, `max: 0`, `arm: both` when absence is the point) and let the "
                "rubric grade only what has to be judged.",
                str(folder),
            )
        elif not mechanical:
            report.add(
                "39-eval-all-llm",
                "NOTICE",
                f"Case '{folder.name}': every grader is an llm judge. Whatever in it can "
                "be counted is being voted on instead - measured on this plugin, a judge "
                "carries a standard deviation near 0.49 where a counter carries 0.000.",
                str(folder),
            )
        if not (folder / "case.yaml").is_file():
            without_fixture += 1
        else:
            try:
                if "scaffold_script" not in (folder / "case.yaml").read_text(encoding="utf-8"):
                    without_fixture += 1
            except (OSError, UnicodeDecodeError):
                without_fixture += 1
    if without_fixture == len(case_dirs):
        report.add(
            "39-eval-no-fixture",
            "NOTICE",
            f"None of the {len(case_dirs)} eval case(s) declares a `scaffold_script`, so every "
            "case runs against an empty workspace. A rubric that asks the run to measure a "
            "CLAUDE.md, a skill or a budget is asking about files that are not there, and "
            "fails for a reason that has nothing to do with the skill. Either give the case "
            "a fixture (`case.yaml`, run with --scaffold) or grade doctrine rather than a "
            "measurement.",
            str(root / "evals"),
        )


def check_evals(ctx: AuditContext, report: Report) -> None:
    """Schema and coverage of each skill's eval suite.

    Until 2026-09-22 a skill with no `evals/` directory was skipped in silence: a
    BAD suite was an error while NO suite was invisible. That is backwards, and it
    is the falsifiability pathology applied to tests - a skill with no evals cannot
    be shown wrong, only trusted. Absence is now reported, once, as a coverage
    figure rather than one finding per skill: a warning that fires sixty times is a
    warning people learn to scroll past.
    """
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    if not skills_dir.is_dir():
        return
    dirs = [d for d in sorted(skills_dir.iterdir()) if d.is_dir()]
    # Two layouts count as a suite. The house one, `<skill>/evals/evals.json`, and the
    # one `claude plugin eval` actually runs: case directories anywhere under the root's
    # `evals/`, each holding `case.yaml` or `prompt.md`. Until 2026-09-22 this check
    # knew only the first, so it reported 0% coverage on a plugin whose suite had just
    # been made executable - it punished the migration it had itself provoked.
    #
    # Until 0.14.0 the second counted only in plugin layout, only one level deep, and
    # all-or-nothing: three cases anywhere marked EVERY skill covered. A project whose
    # suite runs through `claude plugin eval` read 0%, and a plugin with three cases on
    # one skill of forty-five read 100% - the silent error, the one nobody reports.
    # Coverage is now per skill, from what each case names.
    names = [d.name for d in dirs]
    official = root / "evals"
    covered: set[str] = set()
    for case in eval_case_dirs(root):
        covered |= skills_of_case(case, official, names)
    if not covered and len(dirs) == 1 and eval_case_dirs(root):
        covered = set(names)          # one skill: every case is about it
    withed = [d for d in dirs
              if (d / "evals" / "evals.json").is_file() or d.name in covered]
    if dirs:
        pct = len(withed) / len(dirs)
        missing = [d.name for d in dirs if d not in withed]
        detail = (" Without: " + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
                  if missing else "")
        # A house convention: it fired on 47 of ~53 repositories with skills in a public
        # sample (2026-09-27) - a check that says yes 89% of the time measures adoption.
        report.add(
            "26-evals-coverage",
            house(ctx) if pct < ctx.limits.EVALS_COVERAGE_WARN else "INFO",
            f"Eval coverage: {len(withed)}/{len(dirs)} skills carry an eval suite "
            f"({pct:.0%}). A skill with no suite cannot be shown wrong - it can only be "
            f"trusted.{detail}"
            + (house_note("an eval suite per skill", "build evaluations first (skill authoring "
                          "best practices), with no per-skill coverage")
               if pct < ctx.limits.EVALS_COVERAGE_WARN else ""),
            str(skills_dir),
        )
    for skill_dir in dirs:
        path = skill_dir / "evals" / "evals.json"
        if not path.is_file():
            continue
        name = skill_dir.name
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.add("26-evals-schema", "ERROR", f"evals.json in '{name}' does not parse: {exc}", str(path))
            continue
        if not isinstance(data, dict) or "skill_name" not in data or "evals" not in data:
            # Another format than skill-creator's (a list of {query, should_trigger}, an
            # object of `cases`) is a suite some other runner reads: nothing in Claude Code
            # consumes evals.json, so nothing fails. 6 ERRORs on two fresh public samples
            # (2026-09-27), all such suites. A parse failure stays an ERROR.
            report.add(
                "26-evals-schema",
                "NOTICE",
                f"evals.json in '{name}' is not skill-creator's schema (an object carrying "
                "'skill_name' and 'evals'): its runner will not read it, if that is the one "
                "meant. Another runner's format is fine.",
                str(path),
            )
            continue
        # "Name matching the skill's frontmatter" (skill-creator schemas.md) - not the
        # folder: compared to the folder, 3 suites whose skill_name was exactly the
        # frontmatter name were ERRORs (third public sample, 2026-09-27).
        fm_name = ""
        try:
            fm_skill, _ = parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
            fm_name = (fm_skill or {}).get("name", "").strip()
        except (OSError, UnicodeDecodeError):
            pass
        if data["skill_name"] not in {name, fm_name} - {""}:
            report.add(
                "26-evals-schema",
                "ERROR",
                f"evals.json in '{name}' declares skill_name '{data['skill_name']}', which is "
                f"neither the frontmatter name{f' ({fm_name!r})' if fm_name else ''} nor the folder.",
                str(path),
            )
        cases = data["evals"]
        # projection evals/1
        if isinstance(data, dict) and data.get("schema") == "evals/1":
            # Schema evals/1 (2026-09-20): the expectations live under `assertions`.
            # Projected onto the historical keys in memory, so the checks downstream
            # stay unchanged. The file itself is never rewritten.
            cases = [
                c if not isinstance(c, dict) else {
                    **c,
                    "expectations": c.get("expectations")
                    or [a.get("text", "") for a in (c.get("assertions") or []) if isinstance(a, dict)]
                    or [f"selects skill {c.get('expected_skill', '')}"],
                    "expected_output": c.get("expected_output")
                    or ((c.get("assertions") or [{}])[0] or {}).get("text", "")
                    or f"selects skill {c.get('expected_skill', '')}",
                }
                for c in cases
            ]
        if not isinstance(cases, list):
            report.add("26-evals-schema", "ERROR", f"'evals' in '{name}' is not a list.", str(path))
            continue

        ids: list = []
        without_assertions = 0
        for position, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                report.add("26-evals-schema", "ERROR", f"Eval #{position} in '{name}' is not an object.", str(path))
                continue
            missing = [key for key in EVALS_REQUIRED_KEYS if key not in case]
            if missing:
                report.add(
                    "26-evals-schema",
                    "ERROR",
                    f"Eval #{position} in '{name}' is missing: {', '.join(missing)}.",
                    str(path),
                )
            if "expectations" not in case:
                without_assertions += 1
            expectations = case.get("expectations")
            if "expectations" in case and (
                not isinstance(expectations, list)
                or not expectations
                or not all(isinstance(item, str) for item in expectations)
            ):
                report.add(
                    "26-evals-schema",
                    "ERROR",
                    f"Eval #{position} in '{name}' has an 'expectations' value that is not a non-empty list of strings.",
                    str(path),
                )
            if "id" in case:
                if isinstance(case["id"], bool) or not isinstance(case["id"], (int, str)):
                    report.add(
                        "26-evals-schema",
                        "ERROR",
                        f"Eval #{position} in '{name}' has an 'id' that is neither an integer nor a slug string.",
                        str(path),
                    )
                else:
                    ids.append(case["id"])

        if without_assertions:
            report.add("26-evals-schema", "NOTICE",
                       f"{without_assertions} eval(s) in '{name}' carry no 'expectations' yet: they "
                       "can be run, not graded. skill-creator drafts them during the first runs.",
                       str(path))
        duplicates = sorted({str(i) for i in ids if ids.count(i) > 1})
        if duplicates:
            report.add(
                "26-evals-schema",
                "ERROR",
                f"Duplicate eval id(s) in '{name}': {', '.join(duplicates)}.",
                str(path),
            )
        id_types = {type(i).__name__ for i in ids}
        if len(id_types) > 1:
            report.add(
                "26-evals-id-type",
                "WARN",
                f"evals.json in '{name}' mixes integer and slug ids. Pick one form per file.",
                str(path),
            )
        elif id_types == {"str"}:
            report.add(
                "26-evals-id-type",
                "INFO",
                f"evals.json in '{name}' uses slug string ids where the documented schema says integer. "
                "Accepted — the file is internally consistent.",
                str(path),
            )

        if len(cases) < ctx.limits.EVALS_MIN_COUNT:
            report.add(
                "26-evals-count",
                "WARN",
                f"'{name}' has {len(cases)} eval(s) (official minimum {ctx.limits.EVALS_MIN_COUNT}).",
                str(path),
            )
        if cases and not any(looks_like_anti_trigger(c) for c in cases if isinstance(c, dict)):
            report.add(
                "26-evals-anti-trigger",
                "WARN",
                f"'{name}' has no anti-trigger eval. Heuristic: an id or name containing "
                f"{', '.join(EVALS_ANTI_NAME_TOKENS)}, or an expectation containing "
                f"{', '.join(EVALS_ANTI_EXPECTATION_TOKENS)}. A suite that only tests triggering "
                "never tests the boundary.",
                str(path),
            )
