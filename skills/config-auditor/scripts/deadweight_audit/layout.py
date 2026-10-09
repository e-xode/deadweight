"""Which container is audited - project, plugin, marketplace, library, none - and where it keeps things."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .context import AuditContext


# Two containers hold skills, and they are not the same object.
#
#   project : CLAUDE.md + settings + agents + rules + skills at .claude/skills/
#   plugin  : a manifest + skills at skills/ (and optionally agents/)
#
# The SKILL-level checks - description length, compaction slice, reference TOCs,
# orphan references, anti-triggers, evals, broken links - apply to any SKILL.md
# wherever it lives. The PROJECT-level checks do not apply to a plugin at all.
# Splitting them is what lets this script audit a plugin, including its own.

LIBRARY_MIN_SKILLS = 3   # 1 or 2 root skills beside a CLAUDE.md were strays on two samples; 30 and 72 were libraries


def _memory_file_in_other_case(root: Path) -> bool:
    """A `claude.md` alone is a project whose instructions Linux never loads, not `none`.

    exists() is case-sensitive on Linux: before this, such a repository was reported as
    having nothing to audit and nothing missing (2026-10-06).
    """
    try:
        # claude.local.md too: a public repository holding only claude.local.md was reported as
        # `none` and never audited (sample of 44, 2026-10-08).
        return any(n.lower() in ("claude.md", "claude.local.md") for n in os.listdir(root))
    except OSError:
        return False


def claude_signs(root: Path) -> list[str]:
    """What in this repository says it is meant for Claude Code."""
    return [n for n in ("CLAUDE.md", ".claude", ".claude-plugin") if (root / n).exists()]


def root_level_skills(root: Path) -> list[Path]:
    """Directories at the root that hold a SKILL.md directly.

    Claude Code finds skills by LOCATION, never by content: `~/.claude/skills/`,
    `.claude/skills/`, and `skills/` at a plugin root. Measured 2026-09-23 from the
    session's `init` event: a `<name>/SKILL.md` at the repository root is loaded
    neither when the repository is opened as a project nor when it is passed as
    `--plugin-dir`, where `skills/<name>/SKILL.md` beside it is.
    """
    skip = {".claude", ".claude-plugin", ".git", "skills"}
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name not in skip and (d / "SKILL.md").is_file())


def detect_layout(root: Path) -> str:
    """Which container this is: `marketplace`, `plugin`, `project`, `library` or `none`.

    A repository whose root carries a marketplace manifest and whose plugins live in
    subdirectories is NEITHER a project NOR a plugin. Measured 2026-09-22 on 15
    public plugins from the community catalogue: auditing one as a project produced
    two confident errors - "CLAUDE.md not found" and ".claude/skills/ not found" -
    about files a marketplace has no reason to carry. An auditor that does not know
    a shape reports its own ignorance as the subject's defect.
    """
    if (root / ".claude-plugin" / "plugin.json").is_file():
        return "plugin"
    if (root / ".claude-plugin" / "marketplace.json").is_file():
        return "marketplace"
    # Everything below was measured on 15 public repositories created after
    # 2026-09-22: 6 of the 7 errors reported there were this auditor mistaking a
    # shape it did not know for a project missing its CLAUDE.md.
    if (root / "CLAUDE.md").exists() or (root / ".claude").is_dir() or (root / "AGENTS.md").exists() \
            or _memory_file_in_other_case(root):
        return "project"
    # The manifest is optional: `skills/<name>/SKILL.md` at the root loads under
    # `--plugin-dir`, named after the folder, and `claude plugin validate` passes.
    if (root / "skills").is_dir() and any((root / "skills").glob("*/SKILL.md")):
        return "plugin"
    # Skills kept at the root load nowhere as they stand. Their content is still
    # worth auditing - they are meant to be copied somewhere that does load them.
    if root_level_skills(root):
        return "library"
    # A project that shares only MCP servers: "Check `.mcp.json` into version control so
    # everyone on your team gets the same MCP tools" (mcp). After the plugin tests - a
    # plugin may ship a root .mcp.json too. Classed `none`, it was never audited.
    if (root / ".mcp.json").is_file():
        return "project"
    # A SKILL.md under `.devin/` or `tests/fixtures/` is not a Claude configuration,
    # and "CLAUDE.md not found" there is the auditor's ignorance, not a defect.
    return "none"


def has_project_config(root: Path) -> bool:
    """A project configuration beside a manifest - not an `.claude/audit/` floor alone."""
    claude = root / ".claude"
    return ((root / "CLAUDE.md").is_file() or (claude / "CLAUDE.md").is_file()
            or any((claude / d).exists() for d in ("skills", "agents", "commands", "rules",
                                                    "hooks", "settings.json",
                                                    "settings.local.json")))


def apply_layout(ctx: AuditContext, layout: str) -> None:
    """Point the context at the configuration of one container."""
    ctx.layout = layout
    if layout == "plugin":
        ctx.claude_dir, ctx.skills_dir, ctx.agents_dir = ".", "skills", "agents"
        manifest = ctx.root / ".claude-plugin" / "plugin.json"
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8-sig")).get("skills")
            if isinstance(declared, list) and declared and isinstance(declared[0], str):
                declared = declared[0]          # "string|array": the first path is the home
            if isinstance(declared, str):
                # A PREFIX, not a set of characters: `strip("./")` turned
                # `./.claude/skills` into `claude/skills`.
                d = declared[2:] if declared.startswith("./") else declared
                ctx.skills_dir = d.rstrip("/") or "skills"
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    elif layout == "marketplace":
        # A marketplace carries a catalogue, not a configuration. It has no CLAUDE.md,
        # no settings and no skills of its own - the plugins it lists have those.
        # Pointing the project paths at it would report every absence as a defect.
        ctx.claude_dir, ctx.skills_dir, ctx.agents_dir = ".", "skills", "agents"
    elif layout in ("library", "none"):
        ctx.claude_dir, ctx.skills_dir, ctx.agents_dir = ".", ".", "agents"
    else:
        ctx.claude_dir, ctx.skills_dir, ctx.agents_dir = ".claude", ".claude/skills", ".claude/agents"
