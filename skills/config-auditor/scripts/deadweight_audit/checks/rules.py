"""Path-scoped rules in `.claude/rules/`."""
from __future__ import annotations

import re

from ..checks.language import FRENCH_HEURISTIC_THRESHOLD, FRENCH_HEURISTIC_WORDS
from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_list, parse_frontmatter
from ..parsing.globs import glob_match_count
from ..parsing.markdown import strip_code_fences
from ..repo import readable_files, git_ignored, rule_scope_files, tracked_paths
from ..report import Report, house, house_note


RULE_MAX_BYTES = 2048

# "When a subdirectory `CLAUDE.md` or a rules file that loads on demand is over a per-file size
# limit, Claude receives only the start of it ... The limit applies to these files, which load on
# demand: `CLAUDE.md` and `CLAUDE.local.md` in a subdirectory ... Rules files in a subdirectory's
# `.claude/rules/` ... Path-scoped rules in your project's `.claude/rules/` or in
# `~/.claude/rules/` ... 200K context window: 40,000 characters; 1M context window: 200,000
# characters on Claude Opus 4.6 and Claude Sonnet 4.6, and 150,000 characters on later models.
# Before v2.1.309, Claude Code didn't apply this limit" (memory, "Claude ignores the end of my
# subdirectory CLAUDE.md"). The audit cannot see which window a session uses, so it reports the
# smallest limit, as a NOTICE. `~/.claude/rules/` is outside the project and not read, and neither are
# the files a measured file imports with `@path` (the page counts them too: they are not added here).
ONDEMAND_FILE_MAX_CHARS = 40_000
_ONDEMAND_PRUNED = frozenset({"node_modules", "vendor", ".git"})


def _chars(path) -> int | None:
    """Characters of a file as `wc -m` counts them: a CRLF is two, which `read_text` would make one.

    None when it cannot be read as UTF-8 (catch-up and 0.29.0 audits, A-04).
    """
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return len(fh.read())
    except (OSError, UnicodeDecodeError):
        return None


def _ondemand_size(report: Report, rel: str, path, what: str, n: int | None) -> None:
    if n is None or n <= ONDEMAND_FILE_MAX_CHARS:
        return
    report.add(
        "14-ondemand-file-size",
        "NOTICE",
        f"'{rel}' ({what}) is {n:,} characters. It loads on demand, and the limit is "
        f"{ONDEMAND_FILE_MAX_CHARS:,} characters on a 200K context window ({150_000:,} to "
        f"{200_000:,} on a 1M window, which this audit cannot see): past it Claude receives only "
        "the start of the file, ending with a note to read the rest with the Read tool, so the "
        "later instructions are not in context until it does (memory, Claude Code v2.1.309). "
        "Trim it, or move the end into a rules file, which counts on its own. Files it imports "
        "with `@path` count too, and are not added here.",
        str(path),
    )


def _ondemand_files(ctx: AuditContext) -> list[tuple[str, str]]:
    """(relative path, what) of the subdirectory files that load on demand, in the project.

    `CLAUDE.local.md` is looked for beside every tracked file: git ignores it by design (01-claude-local
    warns when it does not), so a list of tracked and unignored files never holds it (0.29.0 audit, A-01).
    A path is pruned by component, not by substring: `src/myvendor/` is not `vendor/` (A-03).
    """
    root = ctx.root
    tracked = tracked_paths(root)
    dirs = set()
    for rel in tracked:
        # Every folder above a tracked file: `api/CLAUDE.local.md` sits in `api/`, which may hold
        # nothing tracked directly (`api/.claude/rules/x.md` is).
        parts = rel.split("/")[:-1]
        dirs.update("/".join(parts[:k]) for k in range(1, len(parts) + 1))
    wanted = set()
    for rel in tracked:
        parts = rel.split("/")
        if _ONDEMAND_PRUNED & set(parts[:-1]) or parts[0] == ctx.claude_dir:
            continue
        if parts[-1] == "CLAUDE.md" and len(parts) > 1:
            wanted.add((rel, "a subdirectory instruction file"))
        elif (rel.endswith(".md") and len(parts) > 3 and ".claude" in parts[1:-2]
              and parts[parts.index(".claude", 1) + 1] == "rules"):
            wanted.add((rel, "a rules file of a subdirectory"))
    for d in dirs:
        if _ONDEMAND_PRUNED & set(d.split("/")) or d.split("/")[0] == ctx.claude_dir:
            continue
        local = f"{d}/CLAUDE.local.md"
        if (root / local).is_file():
            wanted.add((local, "a subdirectory instruction file"))
        # Read from the disk, not from git: a project that ignores `.claude/` keeps its rules there
        # all the same (re-audit of 0.29.0, A-00). A folder with no tracked file is not visited (A-01).
        rules = root / d / ".claude" / "rules"
        if rules.is_dir():
            for f in sorted(rules.rglob("*.md")):
                wanted.add((f.relative_to(root).as_posix(), "a rules file of a subdirectory"))
    return sorted(wanted)


def check_rules(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    for rel, what in _ondemand_files(ctx):
        _ondemand_size(report, rel, root / rel, what, _chars(root / rel))
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
        if fm and fm.get("paths", "").strip():
            _ondemand_size(report, entry.relative_to(root).as_posix(), entry,
                           "a path-scoped rule", _chars(entry))
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
    files = rule_scope_files(root)
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
