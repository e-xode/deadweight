"""Other agents reading the same repository: AGENTS.md, Cursor, Copilot."""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_list, parse_frontmatter
from ..parsing.globs import glob_match_count
from ..parsing.markdown import injected_memory, memory_imports, strip_code_fences
from ..repo import git_ignored, is_specimen_path, repo_files
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
CLAUDE_SLASH = ("compact", "clear", "memory", "agents", "hooks", "init", "permissions", "context",
                "mcp", "doctor", "resume", "skills", "plugin", "config", "model", "rewind")
# What each reader has under the same name, so it is not counted for that reader (audit
# externe 2026-10-08). Cursor CLI's slash-command reference lists /model, /clear, /resume,
# /rewind, /mcp, /plugin, /config; Cursor loads .claude/agents/ ("Claude compatibility",
# Cursor subagents) and runs the hooks of .claude/settings(.local).json, on by default
# (Cursor third-party hooks) - the scripts those hooks call sit in .claude/hooks/.
# Copilot CLI's command reference lists /clear, /compact, /init, /model, /mcp, /resume, /plugin,
# /permissions, /config, /rewind, /context, /agents, /skills; VS Code reads .claude/agents
# ("Workspace (Claude format)", VS Code custom agents). .claude/settings.json is read by VS Code
# only with chat.useClaudeHooks, "off by default" (VS Code hooks): with it, .claude/settings.json
# and the .claude/hooks/ scripts it calls are shared - see _copilot_reads_claude_hooks.
SHARED_WITH = {
    "cursor": {"slash": {"model", "clear", "resume", "rewind", "mcp", "plugin", "config"},
               "dot": {"agents", "hooks", "settings"}},
    "copilot": {"slash": {"clear", "compact", "init", "model", "mcp", "resume", "plugin", "permissions",
                          "config", "rewind", "context", "agents", "skills"},
                "dot": {"agents"}},
}


def claude_only_re(reader: str | None = None, shared_dot: set[str] | None = None) -> re.Pattern:
    """The Claude Code-only mechanisms as one pattern, less what `reader` has too."""
    slash = [c for c in CLAUDE_SLASH if not reader or c not in SHARED_WITH[reader]["slash"]]
    dot_shared = set(shared_dot if shared_dot is not None else
                     (SHARED_WITH[reader]["dot"] if reader else ()))
    dot = [pat for d, pat in (("agents", "agents"), ("hooks", "hooks"), ("commands", "commands"),
                              ("settings", r"settings(?:\.local)?\.json")) if d not in dot_shared]
    parts = []
    if slash:
        parts.append(r"(?<![\w/.-])/(?:" + "|".join(slash) + r")\b(?![/?])")
    parts += [r"`(?:Task|TodoWrite|Skill|NotebookEdit|WebFetch|WebSearch)(?:\([^`]*\))?`",
              r"\b(?:Task|TodoWrite|Skill|WebFetch|NotebookEdit) tool\b"]
    if dot:
        parts.append(r"\.claude/(?:" + "|".join(dot) + r")\b")
    return re.compile("|".join(parts), re.IGNORECASE)


# Every mechanism, for whoever reads it with no reader in mind.
CLAUDE_ONLY_RE = claude_only_re()
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


def _imported_by_memory(root, files: list[str]) -> set[str]:
    """Real paths of the files a CLAUDE.md or CLAUDE.local.md of the tree imports with `@`.

    "Imported files are expanded and loaded into context at launch [...] Imported files can
    recursively import other files, with a maximum depth of four hops" (memory). Imports
    outside the repository are not followed: they wait on an approval dialog.
    """
    real_root = os.path.realpath(root)
    todo = [(root / f, 0) for f in files if f.rsplit("/", 1)[-1] in ("CLAUDE.md", "CLAUDE.local.md")]
    seen: set[str] = set()
    while todo:
        path, depth = todo.pop()
        try:
            refs = memory_imports(injected_memory(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
        for ref in refs:
            if ref.startswith(("~/", "/")):
                continue
            real = os.path.realpath(path.parent / ref)
            if real in seen or not real.startswith(real_root + os.sep) or not os.path.isfile(real):
                continue
            seen.add(real)
            if depth < 4:
                todo.append((Path(real), depth + 1))
    return seen


def _copilot_reads_claude_hooks(root) -> bool:
    """Whether the workspace turns on chat.useClaudeHooks, the one way VS Code reads
    .claude/settings.json - "off by default" (VS Code hooks). A user-level setting is not
    visible from the repository: then the file is counted as Claude Code-only."""
    try:
        text = (root / ".vscode" / "settings.json").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # settings.json is "JSON with Comments" (VS Code JSON): a commented-out line is off
    # (audit externe 3, g5-01). Strings are kept whole, so a "//" inside one is not a comment.
    text = JSONC_TOKEN_RE.sub(lambda m: m.group(0) if m.group(0).startswith('"') else " ", text)
    return re.search(r'"chat\.useClaudeHooks"\s*:\s*true\b', text) is not None


JSONC_TOKEN_RE = re.compile(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', re.DOTALL)


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
    imported = None
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if name in ("AGENTS.override.md", "AGENTS.local.md") and not ignored(rel):
            # Claude Code never finds these on its own, but loads one a CLAUDE.md imports
            # (memory): then both agents read it, and nothing diverges (audit externe 2026-10-08).
            if imported is None:
                imported = _imported_by_memory(root, all_files)
            if os.path.realpath(root / rel) in imported:
                # Unless the AGENTS.md beside it is imported too: Claude Code loads both, while
                # "Codex includes at most one file per directory" and skips that AGENTS.md
                # because an override exists (Codex AGENTS.md guide; audit externe 3, g5-02).
                sibling = rel[:-len(name)] + "AGENTS.md"
                if name == "AGENTS.override.md" and os.path.realpath(root / sibling) in imported:
                    report.add("54-agents-md-variant", "NOTICE",
                               f"'{rel}' and '{sibling}' are both imported by a CLAUDE.md, so Claude "
                               f"Code reads both; Codex \"includes at most one file per directory\" "
                               f"and reads only the override (Codex AGENTS.md guide). Whatever "
                               f"'{sibling}' says applies to Claude Code and not to Codex.",
                               str(root / rel))
                continue
            # Codex documents AGENTS.override.md; no reader of AGENTS.local.md is documented -
            # Claude Code's memory page only lists it as not read.
            reader = ("is read by Codex, never by Claude Code" if name == "AGENTS.override.md"
                      else "is not read by Claude Code, and no agent documents reading it")
            report.add("54-agents-md-variant", "NOTICE",
                       f"'{rel}' {reader}: \"Not read: AGENTS.local.md, AGENTS.override.md\" "
                       "(memory)" + (". Whatever it overrides applies to one agent and not the other."
                                     if name == "AGENTS.override.md" else
                                     ". Import it from CLAUDE.md with `@` if Claude Code should read it."),
                       str(root / rel))
    # Cursor applies CLAUDE.md to every conversation "regardless of any alwaysApply" (Cursor
    # rules help), and Copilot's agent, CLI and code review read it too (Copilot custom
    # instructions): what CLAUDE.md tells Claude Code alone, they read as theirs. Only
    # mechanisms no other agent has are counted - .claude/skills/ is not, Cursor loads it.
    # Only ./CLAUDE.md: Cursor documents "a CLAUDE.md file in your project root" (Cursor rules
    # help), Copilot "a single CLAUDE.md [...] stored in the root of the repository" (Copilot
    # custom instructions); neither documents .claude/CLAUDE.md (audit externe 2026-10-08).
    claude_md = root / "CLAUDE.md"
    if claude_md.is_file():
        text = strip_code_fences(injected_memory(claude_md.read_text(encoding="utf-8", errors="replace")))
        readers = []
        if (root / ".cursor").is_dir() or (root / ".cursorrules").is_file():
            readers.append(("55-cursor-reads-claude-md", "Cursor applies it to every conversation "
                            "(Cursor rules help)", claude_only_re("cursor")))
        if (root / ".github/copilot-instructions.md").is_file() or (root / ".github/instructions").is_dir():
            dot = SHARED_WITH["copilot"]["dot"] | ({"settings", "hooks"} if _copilot_reads_claude_hooks(root) else set())
            readers.append(("56-copilot-reads-claude-md", "Copilot's agent, CLI and code review read "
                            "it (Copilot custom instructions)", claude_only_re("copilot", dot)))
        for check, how, pattern in readers:
            only_claude = [m.group(0).strip("` ") for m in pattern.finditer(text)
                           if not HTTP_ROUTE_BEFORE_RE.search(text[max(0, m.start() - 16):m.start()])]
            if not only_claude:
                continue
            shown = ", ".join(repr(x) for x in list(dict.fromkeys(only_claude))[:3])
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
            # NOTICE: VS Code still loads it - "they continue to work and are automatically
            # treated as custom agents" (VS Code 1.106 release notes); the location is deprecated,
            # not dead (audit externe 2026-10-08).
            report.add("56-copilot-chatmode", "NOTICE",
                       f"'{rel}' is a chat mode in its deprecated location: VS Code still loads it as a "
                       "custom agent (VS Code 1.106 release notes), but custom agents now live in "
                       ".github/agents/*.agent.md - \"rename them to .agent.md\" (VS Code custom "
                       "agents).", str(root / rel))
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
