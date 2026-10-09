"""Path-scoped rules in `.claude/rules/`."""
from __future__ import annotations

import re

from ..checks.language import FRENCH_HEURISTIC_THRESHOLD, FRENCH_HEURISTIC_WORDS
from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_list, parse_frontmatter
from ..parsing.globs import glob_match_count
from ..parsing.markdown import strip_code_fences
from ..repo import readable_files, git_ignored, repo_files
from ..report import Report, house, house_note


RULE_MAX_BYTES = 2048


def check_rules(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    rules_dir = root / ctx.claude_dir / "rules"
    if not rules_dir.is_dir():
        return
    # "Rules are discovered recursively" - a rule in a subdirectory loads, and was
    # audited by nothing.
    for entry in readable_files(rules_dir.rglob("*.md")):
        if not entry.is_file():
            continue
        text = entry.read_text(encoding="utf-8")
        size = entry.stat().st_size

        fm, _ = parse_frontmatter(text)
        if size > RULE_MAX_BYTES:
            # The documented figure is 200 lines per file, rules files included (memory):
            # the finding names it, so a rule well under it is not read as over a doc limit.
            lines = len(text.splitlines())
            scoped = bool(fm and fm.get("paths", "").strip())
            report.add(
                "14-rule-size",
                house(ctx),
                f"Rule '{entry.name}' is {size} bytes (> {RULE_MAX_BYTES}), {lines} lines. If it "
                "carries knowledge, move that into a skill and keep the constraint in the rule"
                # A skill also takes `paths:`, "the same format as path-specific rules"
                # (skills): saying it loads only by description was false (audit externe 3, g4-02).
                + ("; the skill can keep the same `paths:` globs (skills)." if scoped else ".")
                + house_note(f"rules under {RULE_MAX_BYTES} bytes",
                             "one topic per file, and files over 200 lines \"may reduce adherence\", "
                             "each rules file counted separately (memory)"),
                str(entry),
            )

        if fm is not None:
            paths_val = fm.get("paths", "").strip()
            # "Rules without a paths field are loaded unconditionally" (memory): valid,
            # not a defect. The defect is a misnamed key (`globs:`, Cursor's), which
            # 14-rule-unknown-field reports - here it was reported a second time, as a WARN.
            if not paths_val and not {"globs", "glob", "path"} & set(fm):
                report.add(
                    "14-rule-no-paths",
                    "INFO",
                    f"Rule '{entry.name}' has frontmatter but no 'paths:': it loads in every "
                    "session, like CLAUDE.md (memory). Add 'paths:' only if it should not.",
                    str(entry),
                )

        stripped = strip_code_fences(text, indented=True)
        if re.search(r"^\s*//", stripped, re.MULTILINE):
            report.add(
                "14-rule-code-comments",
                house(ctx),
                f"Rule '{entry.name}' contains a // comment outside a code block."
                + house_note("prose only, no code comments", "nothing on this"),
                str(entry),
            )

        words = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ']+", stripped.lower())
        # Distinct words, as check 11 counts them: `pour` is back in the shared list, and
        # counted per occurrence three English "Pour ..." lines reached the threshold alone.
        hits = len(set(words) & FRENCH_HEURISTIC_WORDS)
        if hits >= FRENCH_HEURISTIC_THRESHOLD:
            report.add(
                "14-rule-english-only",
                house(ctx),
                f"Rule '{entry.name}' appears to contain French content ({hits} distinct heuristic words).",
                str(entry),
            )


def check_rule_globs(ctx: AuditContext, report: Report) -> None:
    """Every `paths:` glob in a rule expands to at least one real file.

    A glob that matches nothing never loads its rule: the guardrail is silently
    inert, and nothing about the file itself looks wrong. An unescaped `[` is
    the documented way to produce one by accident — it opens a character class
    instead of matching a literal bracket.
    """
    root = ctx.root
    rules_dir = root / ctx.claude_dir / "rules"
    if not rules_dir.is_dir():
        return
    files = repo_files(root)
    ignored = git_ignored(root)
    for entry in readable_files(rules_dir.rglob("*.md")):
        try:
            fm, _ = parse_frontmatter(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if not fm:
            continue
        for pattern in frontmatter_list(fm.get("paths", "")):
            # A glob rooted in a directory git ignores (`masters/**`) loads its rule on
            # the machines that hold those files and never on a fresh clone. Judged on
            # the disk, the same commit gave 0 findings on one machine and 1 on another
            # (measured 2026-09-23). Asked of git, the answer is the same everywhere -
            # `git check-ignore` evaluates the rules, not the files.
            fixed = re.split(r"[*?\[{]", pattern, maxsplit=1)[0]
            probe = fixed + "x" if fixed.endswith("/") else fixed
            if probe and ignored(probe):
                report.add("22-rule-glob-match", "NOTICE",
                           f"Rule '{entry.name}' glob '{pattern}' points into a path git ignores: "
                           "it loads only where those untracked files exist, so whether it is "
                           "inert depends on the machine. Not counted.", str(entry))
                continue
            if glob_match_count(pattern, files):
                continue
            # Only an UNESCAPED `[` earns the advice: `photos \[2024/**` already follows it.
            bracket = (
                " The unescaped '[' opens a bracket expression, and one that cannot be read as "
                "such makes the pattern invalid (memory) — escape it as '\\[' if a literal "
                "bracket was meant."
                if re.search(r"(?<!\\)\[", pattern)
                else ""
            )
            report.add(
                "22-rule-glob-match",
                "WARN",
                f"Rule '{entry.name}' glob '{pattern}' matches no file in the repository, "
                f"so the rule never loads for it.{bracket}",
                str(entry),
            )
