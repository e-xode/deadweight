"""Other agents reading the same repository: AGENTS.md, Cursor, Copilot."""
from __future__ import annotations

import re

from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_list, parse_frontmatter
from ..parsing.globs import glob_match_count
from ..parsing.markdown import injected_memory, strip_code_fences
from ..repo import claude_md_path, git_ignored, is_specimen_path, repo_files
from ..report import Report


# A folder whose conventional name says its content is not this repository's own working
# configuration: third-party code, specimens meant to be copied elsewhere, examples and test
# data. Derived from GitHub Linguist's vendor.yml (`vendors?/`, `testdata/`, `tests/fixtures/`,
# `.xctemplate/`, `docs/templates/`) and from `20`'s template exclusion (0.17.0). Another tool's
# files under one of them were read as the repository's own: 97 false WARNs in 2 of 166 fresh
# public repositories - vendored upstream templates and generator skeletons (2026-09-28).
# What CLAUDE.md can name that only Claude Code has: its built-in slash commands, its tools
# named as tools, and the .claude/ folders no other agent reads. Not counted: subagents (Cursor
# has .cursor/agents/, Copilot has custom agents - 60 of 68 first findings were the word
# "subagent", 2026-09-29), .claude/skills/ (Cursor loads it), .claude/rules/ (Copilot in VS Code
# reads it). Used where another agent is known to read CLAUDE.md.
CLAUDE_ONLY_RE = re.compile(
    r"(?<![\w/.-])/(?:compact|clear|memory|agents|hooks|init|permissions|context|mcp|doctor|"
    r"resume|skills|plugin|config|model|rewind)\b(?![/?])"
    r"|`(?:Task|TodoWrite|Skill|NotebookEdit|WebFetch|WebSearch)(?:\([^`]*\))?`"
    r"|\b(?:Task|TodoWrite|Skill|WebFetch|NotebookEdit) tool\b"
    r"|\.claude/(?:agents|hooks|commands|settings(?:\.local)?\.json)\b",
    re.IGNORECASE)
# `/mcp`, `/config`, `/model` are also HTTP routes, and an MCP server's CLAUDE.md names its
# own: "MCP at /mcp", "backend API + MCP /mcp" - 4 findings in 2 of 513 fresh repositories
# (2026-09-29). A slash word after a verb, a preposition or a route word is a path, and so
# is one that continues (`/mcp/sse`, `/config?x`).
HTTP_ROUTE_BEFORE_RE = re.compile(
    r"(?:\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|at|on|endpoint|route|path|MCP|API)|https?:)\s*[`'\"]?$")


def _tool_patterns(raw: str) -> list[str]:
    """Another tool's glob field as patterns: a YAML list, or commas outside braces.

    `**/*.{ts,tsx}` is ONE pattern - split on every comma it became `**/*.{ts` and `tsx`,
    which match nothing: 17 false WARNs in 5 public repositories (2026-09-28). And an
    `applyTo` written as a YAML block list read as one pattern with newlines in it.
    """
    raw = str(raw or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    elif "\n" in raw or raw.startswith("- "):
        return frontmatter_list(raw)
    return [p.strip().strip("'\"") for p in re.split(r",(?![^{]*\})", raw) if p.strip().strip("'\"")]


def _tool_glob_matches(patterns: list[str], files: list[str]) -> bool:
    """Whether any of another tool's globs matches a file, read leniently.

    Neither Cursor nor Copilot documents whether `*.ts` reaches subdirectories: a
    pattern with no `/` is also tried as `**/<pattern>`. Doubt is paid in missed
    findings, not in false ones.
    """
    for p in patterns:
        p = p[2:] if p.startswith("./") else p
        tries = [p] if "/" in p else [p, "**/" + p]
        if any(glob_match_count(t, files) for t in tries):
            return True
    return False


def check_other_tools(ctx: AuditContext, report: Report) -> None:
    """What other coding agents read from this repository, and ignore without a word.

    AGENTS.md variants Claude Code never reads (54), Cursor rules (55) and Copilot
    instruction files (56): each tool, like Claude Code, skips a misplaced or
    misnamed file silently. Doctrine and sources: references/agents-md-anatomy.md,
    cursor-anatomy.md, copilot-anatomy.md (verified 2026-09-28). Gemini CLI is
    doctrine only in this release.
    """
    root = ctx.root
    all_files = repo_files(root)
    files = [f for f in all_files if not is_specimen_path(f)]
    ignored = git_ignored(root)
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if name in ("AGENTS.override.md", "AGENTS.local.md") and not ignored(rel):
            report.add("54-agents-md-variant", "NOTICE",
                       f"'{rel}' is read by Codex, never by Claude Code: \"Not read: "
                       "AGENTS.local.md, AGENTS.override.md\" (memory). Whatever it overrides "
                       "applies to one agent and not the other.", str(root / rel))
    # Cursor applies CLAUDE.md to every conversation "regardless of any alwaysApply" (Cursor
    # rules help), and Copilot's agent, CLI and code review read it too (Copilot custom
    # instructions): what CLAUDE.md tells Claude Code alone, they read as theirs. Only
    # mechanisms no other agent has are counted - .claude/skills/ is not, Cursor loads it.
    claude_md = claude_md_path(root)
    if claude_md.is_file():
        text = strip_code_fences(injected_memory(claude_md.read_text(encoding="utf-8", errors="replace")))
        only_claude = [m.group(0).strip("` ") for m in CLAUDE_ONLY_RE.finditer(text)
                       if not HTTP_ROUTE_BEFORE_RE.search(text[max(0, m.start() - 16):m.start()])]
        readers = []
        if (root / ".cursor").is_dir() or (root / ".cursorrules").is_file():
            readers.append(("55-cursor-reads-claude-md", "Cursor applies it to every conversation "
                            "(Cursor rules help)"))
        if (root / ".github/copilot-instructions.md").is_file() or (root / ".github/instructions").is_dir():
            readers.append(("56-copilot-reads-claude-md", "Copilot's agent, CLI and code review read "
                            "it (Copilot custom instructions)"))
        if only_claude:
            shown = ", ".join(repr(x) for x in list(dict.fromkeys(only_claude))[:3])
            for check, how in readers:
                report.add(check, "NOTICE",
                           f"CLAUDE.md names {len(only_claude)} Claude Code-only mechanism(s) "
                           f"({shown}), and {how}: that agent reads them as instructions it cannot "
                           "follow. Say in CLAUDE.md which lines are for Claude Code - Cursor also loads "
                           ".claude/skills/, so moving them to a skill does not hide them.", str(claude_md))
    if (root / ".cursorrules").is_file():
        report.add("55-cursorrules-legacy", "NOTICE",
                   "'.cursorrules' is Cursor's legacy format - \"legacy and will be deprecated\" "
                   "(Cursor rules help): move it to .cursor/rules/*.mdc.", str(root / ".cursorrules"))
    for rel in files:
        if "/.cursor/rules/" not in "/" + rel:
            continue
        path = root / rel
        base_name = rel.rsplit("/", 1)[-1]
        rules_at = rel.index(".cursor/rules/") + len(".cursor/rules/")
        below = rel[rules_at:].split("/")
        # A skill folder kept in .cursor/rules/: one finding for the folder, not one per file -
        # 80 findings for one misplaced skill in a fresh sample (2026-09-29). At any depth:
        # `.cursor/rules/skills/<name>/` read as plain .md files gave 35 findings for 23
        # skills in one repository, their references/ each reported as a rule (2026-09-29).
        skill_dir = next((rel[:rules_at] + "/".join(below[:i]) for i in range(1, len(below))
                          if (root / rel[:rules_at] / "/".join(below[:i]) / "SKILL.md").is_file()), None)
        if skill_dir:
            if rel == f"{skill_dir}/SKILL.md":
                report.add("55-cursor-rule-ignored", "WARN",
                           f"'{skill_dir}/' is a skill kept in .cursor/rules/: the "
                           "rules system reads only .mdc there. Cursor loads skills from "
                           ".cursor/skills/ (or .claude/skills/).", str(path))
            continue
        # A folder rule written RULE.md: a format Cursor documented at one point; its current
        # rules page requires .mdc and names no other. Whether it loads depends on the Cursor
        # version, so it is not reported as ignored - 215 findings in 8 of 601 fresh
        # repositories (2026-09-29).
        if base_name == "RULE.md" and len(below) > 1:
            report.add("55-cursor-rule-ignored", "NOTICE",
                       f"'{rel}' uses the folder format (<name>/RULE.md): Cursor's current rules page "
                       "says \"Project rules must use the .mdc extension\". Whether this one loads "
                       "depends on your Cursor version - check it appears in Cursor's rule settings.",
                       str(path))
            continue
        # README, AGENTS.md and CLAUDE.md in that folder are not rule attempts: each has its
        # own reading rule, or none (palier 4 measure, 2026-09-28).
        if rel.endswith(".md") and not base_name.lower().startswith("readme") \
                and base_name not in ("AGENTS.md", "CLAUDE.md"):
            report.add("55-cursor-rule-ignored", "WARN",
                       f"'{rel}' is a plain .md in .cursor/rules/: \"ignored by the rules system "
                       "because it has no frontmatter\" (Cursor rules). Rename it .mdc with a "
                       "frontmatter, or move it to AGENTS.md.", str(path))
            continue
        if not rel.endswith(".mdc"):
            continue
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        fm = fm or {}
        always = str(fm.get("alwaysApply", "")).strip().lower() == "true"
        globs = _tool_patterns(fm.get("globs", ""))
        desc = str(fm.get("description", "") or "").strip().strip("'\"")
        if not always and not globs and not desc:
            report.add("55-cursor-rule-manual", "NOTICE",
                       f"'{rel}' has no alwaysApply, no globs and no description: Cursor applies "
                       "it only when someone @-mentions it (Manual). If it should apply on its "
                       "own, give it one of the three (Cursor rules).", str(path))
        base = rel.split(".cursor/rules/")[0]
        scoped = [f[len(base):] for f in all_files if f.startswith(base)] if base else all_files
        # A NOTICE, not a WARN: measured on 98 public repositories carrying Cursor or Copilot
        # files, 79 % of unmatched globs were real - under the 90 % bar - and the rest sat in
        # repositories that distribute rules for other projects to copy, where the glob aims
        # at the user's tree, not this one (2026-09-28).
        if globs and not always and not _tool_glob_matches(globs, scoped):
            report.add("55-cursor-rule-glob", "NOTICE",
                       f"'{rel}' globs {', '.join(repr(g) for g in globs)} match no file: the "
                       "rule never attaches here (Cursor rules: \"ensure the file pattern matches "
                       "referenced files\"). Expected if this repository distributes rules for "
                       "others.", str(path))
    for rel in files:
        if rel.startswith(".github/chatmodes/") and rel.endswith(".chatmode.md"):
            report.add("56-copilot-chatmode", "WARN",
                       f"'{rel}' is a chat mode in its old location: Copilot now reads custom "
                       "agents as .github/agents/*.agent.md - \"rename them to .agent.md\" "
                       "(VS Code custom agents).", str(root / rel))
        if not rel.startswith(".github/instructions/") or not rel.endswith(".md"):
            continue
        name = rel.rsplit("/", 1)[-1]
        if not name.endswith(".instructions.md"):
            if not name.lower().startswith("readme"):
                report.add("56-copilot-instructions-name", "WARN",
                           f"'{rel}' is not named *.instructions.md: Copilot reads only that "
                           "suffix in .github/instructions/, and skips this file without a "
                           "word (Copilot custom instructions).", str(root / rel))
            continue
        try:
            fm, _ = parse_frontmatter((root / rel).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        fm = fm or {}
        apply_to = _tool_patterns(fm.get("applyTo", ""))
        if not apply_to and not str(fm.get("description", "") or "").strip():
            report.add("56-copilot-apply-to", "NOTICE",
                       f"'{rel}' has neither applyTo nor description: Copilot never attaches it "
                       "on its own - \"attach the file manually when you want to use it\" "
                       "(VS Code custom instructions).", str(root / rel))
        elif apply_to and not _tool_glob_matches(apply_to, all_files):
            # NOTICE, same reason as 55-cursor-rule-glob: 4 of 18 real on 98 public
            # repositories - most sat in toolkits that distribute instruction files.
            report.add("56-copilot-apply-to", "NOTICE",
                       f"'{rel}' applyTo {', '.join(repr(p) for p in apply_to)} matches no file: "
                       "the instructions never attach here. Expected if this repository distributes "
                       "instruction files for others.", str(root / rel))
