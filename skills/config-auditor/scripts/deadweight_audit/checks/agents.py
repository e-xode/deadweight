"""Sub-agents: frontmatter, tools, preloaded skills."""
from __future__ import annotations

import re

from ..context import AuditContext
from ..parsing.frontmatter import YAML_TRUE, frontmatter_keys, frontmatter_list, parse_frontmatter
from ..repo import readable_files
from ..report import Report
from ..vocabulary.frontmatter import (
    AGENT_PERMISSION_MODES,
    AGENT_VALIDATED_KEYS,
    PLUGIN_AGENT_IGNORED_KEYS,
)
from ..vocabulary.tools import KNOWN_MODEL_TIERS, TOOL_ALIASES, TOOL_DEPRECATED, is_known_tool


def check_agents(ctx: AuditContext, report: Report) -> dict[str, dict]:
    root = ctx.root
    agents_dir = root / ctx.agents_dir
    if not agents_dir.is_dir():
        # A project without agents/ has lost a container it is expected to have.
        # A plugin without agents/ is simply a plugin that ships only skills -
        # the directory is optional in the manifest, so its absence is not news.
        if ctx.layout == "project":
            report.add("08-agents-dir", "INFO",
                       f"{ctx.agents_dir}/ not found - a project without agents lacks nothing.",
                       str(agents_dir))
        return {}
    agents: dict[str, dict] = {}
    # Subdirectories are scanned recursively, and the identity is `name`, not the
    # filename: "The filename doesn't have to match" (sub-agents, 2026-09-23).
    seen_names: dict[str, str] = {}
    for entry in readable_files(agents_dir.rglob("*.md")):
        if not entry.is_file():
            continue
        text = entry.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if not fm:
            # No frontmatter at all is a document someone keeps in agents/ (a routing
            # guide, a reference) - not loaded as an agent. A frontmatter that does not
            # parse is an agent that silently fails to load.
            broken = text.lstrip().startswith("---")
            report.add(
                "08-agent-frontmatter",
                "ERROR" if broken else "WARN",
                f"'{entry.relative_to(agents_dir)}' " + (
                    "has a frontmatter that does not parse: this agent does not load."
                    if broken else
                    "has no frontmatter: it is not loaded as an agent. Documentation kept in "
                    "agents/ is scanned there; move it out if it is not an agent."),
                str(entry),
            )
            continue
        # `tools` and `model` are OPTIONAL. Verified 2026-09-22 against
        # code.claude.com/docs/en/sub-agents: "tools | Required: No - Inherits every
        # tool available to subagents if omitted." Requiring it was house doctrine
        # emitted as an ERROR, and measured on 15 public plugins it produced a false
        # error on somebody else's repository while contradicting the official docs.
        # An audit that is wrong is a nuisance; an audit that is wrong while citing a
        # spec teaches a false rule, with the authority of an error.
        missing = [k for k in ("name", "description") if not fm.get(k)]
        if missing and ctx.layout == "plugin":
            # "A plugin subagent whose frontmatter has no name or doesn't parse still loads,
            # under its filename" (sub-agents): an ERROR "does not load" was false there.
            if "description" in missing:
                report.add("08-agent-frontmatter", "WARN",
                           f"Plugin agent '{entry.stem}' has no description: it loads under its "
                           "filename, with nothing for Claude to decide when to delegate to it "
                           "(sub-agents).", str(entry))
        elif missing:
            report.add(
                "08-agent-frontmatter",
                "ERROR",
                f"Agent '{entry.stem}' missing required keys: {', '.join(missing)}",
                str(entry),
            )
        desc = fm.get("description", "").strip()
        if desc and desc[0] in (">", "|"):
            report.add(
                "02-frontmatter-block-scalar",
                "ERROR",
                f"Agent '{entry.stem}' description parsed as a raw block-scalar indicator — frontmatter parser failed.",
                str(entry),
            )
        ident = (fm.get("name") or entry.stem).strip()
        if ident in seen_names:
            report.add("08-agent-frontmatter", "WARN",
                       f"Two agents are named '{ident}' ({seen_names[ident]} and {entry.name}): the "
                       "harness keeps one by filesystem read order.", str(entry))
        seen_names[ident] = entry.name
        agents[ident] = {"name": fm.get("name", ""), "description": desc, "path": str(entry)}
    return agents


def check_agent_frontmatter_validity(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """Agent frontmatter names things that exist: tools, preloadable skills, a model tier."""
    root = ctx.root
    agents_dir = root / ctx.agents_dir
    if not agents_dir.is_dir():
        return
    inventory: dict[str, int] = {}
    unvalidated: dict[str, int] = {}
    for entry in readable_files(agents_dir.rglob("*.md")):
        try:
            text = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, _ = parse_frontmatter(text)
        if not fm:
            continue

        declared_tools = frontmatter_list(fm.get("tools", ""))
        unknown = []
        for tool in declared_tools:
            base = tool.split("(", 1)[0].strip()
            if base in TOOL_DEPRECATED:
                report.add("23-agent-tools", "NOTICE",
                           f"Agent '{entry.stem}' grants '{base}', deprecated in favor of "
                           f"{TOOL_DEPRECATED[base]} (tools-reference).", str(entry))
                continue
            if base in TOOL_ALIASES:
                report.add("23-agent-tools", "NOTICE",
                           f"Agent '{entry.stem}' grants '{base}', the former name of "
                           f"'{TOOL_ALIASES[base]}' - still accepted as an alias.", str(entry))
                continue
            if is_known_tool(tool):
                continue
            unknown.append(tool)
        # The harness drops an entry it cannot resolve and launches with the rest; only
        # an agent left with NO tool "fails to launch". Severity follows that.
        for tool in unknown:
            report.add(
                "23-agent-tools",
                "ERROR" if len(unknown) == len(declared_tools) else "WARN",
                f"Agent '{entry.stem}' grants unknown tool '{tool}'. Unresolvable entries are "
                "dropped; parameterised forms like 'Bash(git diff *)' and 'mcp__*' names are "
                "accepted (tools-reference).",
                str(entry),
            )

        for preload in frontmatter_list(fm.get("skills", "")):
            if not (root / ctx.skills_dir / preload / "SKILL.md").is_file():
                # `plugin:skill` and user skills preload legitimately and live outside
                # this repository - unverifiable here, not missing.
                report.add(
                    "23-agent-skills-preload",
                    "INFO" if ":" in preload else "WARN",
                    f"Agent '{entry.stem}' preloads skill '{preload}', which is not under "
                    f"{ctx.skills_dir}/ - fine if it is a user or plugin skill, dead otherwise.",
                    str(entry),
                )
                continue
            flag = str(skills.get(preload, {}).get("disable-model-invocation", "")).strip().lower()
            if flag in YAML_TRUE:
                report.add(
                    "23-agent-skills-preload",
                    "WARN",
                    f"Agent '{entry.stem}' preloads '{preload}', which carries "
                    "'disable-model-invocation: true' and cannot be preloaded. Read it by path instead: "
                    f".claude/skills/{preload}/SKILL.md.",
                    str(entry),
                )

        model = fm.get("model", "").strip()
        if model and model not in KNOWN_MODEL_TIERS and not model.startswith("claude-"):
            report.add(
                "23-agent-model",
                "WARN",
                f"Agent '{entry.stem}' declares model '{model}'. Expected one of "
                f"{', '.join(sorted(KNOWN_MODEL_TIERS))} or a 'claude-*' model id.",
                str(entry),
            )

        mode = fm.get("permissionMode", "").strip()
        # A plugin agent's permissionMode is ignored whatever its value, and
        # 23-agent-frontmatter-keys says so: judging the value too reported one
        # line twice (10 + 10 on a public sample, 2026-09-27).
        if ctx.layout == "plugin" and "permissionMode" in PLUGIN_AGENT_IGNORED_KEYS:
            mode = ""
        if mode and mode not in AGENT_PERMISSION_MODES:
            report.add("23-agent-permission-mode", "WARN",
                       f"Agent '{entry.stem}' declares permissionMode '{mode}', which is not a "
                       f"mode ({', '.join(sorted(AGENT_PERMISSION_MODES))}).", str(entry))
        elif mode == "bypassPermissions":
            report.add("23-agent-permission-mode", "WARN",
                       f"Agent '{entry.stem}' declares bypassPermissions: since 2.1.267 a subagent "
                       "that declares it keeps the main conversation's mode instead (sub-agents).",
                       str(entry))
        if re.search(r"\bAgent\([^)]*\)", fm.get("tools", "")):
            report.add("23-agent-tools", "WARN",
                       f"Agent '{entry.stem}' restricts spawnable types with 'Agent(...)': that list "
                       "applies only to an agent run as the main thread with `claude --agent`; in "
                       "a subagent definition it is ignored (sub-agents).", str(entry))
        if ":" in fm.get("name", ""):
            report.add("08-agent-frontmatter", "ERROR",
                       f"Agent '{entry.stem}' has a ':' in its name: the file is not loaded "
                       "(sub-agents, 2.1.218).", str(entry))
        if ctx.layout == "plugin":
            for key in sorted(PLUGIN_AGENT_IGNORED_KEYS & set(frontmatter_keys(text))):
                report.add("23-agent-frontmatter-keys", "WARN",
                           f"Agent '{entry.stem}' sets '{key}', which Claude Code ignores on an "
                           "agent shipped by a plugin (plugins-reference).", str(entry))

        for key in frontmatter_keys(text):
            inventory[key] = inventory.get(key, 0) + 1
            if key not in AGENT_VALIDATED_KEYS:
                unvalidated[key] = unvalidated.get(key, 0) + 1
                report.add("23-agent-frontmatter-keys", "WARN",
                           f"Agent '{entry.stem}' sets '{key}', which is not a subagent field: "
                           "it is ignored without a word (sub-agents lists 18).", str(entry))

    if inventory:
        seen = ", ".join(f"{k} ({v})" for k, v in sorted(inventory.items()))
        drift = ", ".join(f"{k} ({v})" for k, v in sorted(unvalidated.items())) or "none"
        report.add(
            "23-agent-frontmatter-keys",
            "INFO",
            f"Agent frontmatter keys in use: {seen}. Keys this script does not validate: {drift}.",
            str(agents_dir),
        )


def check_agents_dir_skills(ctx: AuditContext, report: Report) -> None:
    """Skills kept in `.agents/skills/` that Claude Code never loads.

    The docs list where skills live - managed, `~/.claude/skills/`, `.claude/skills/`,
    nested `.claude/skills/`, `--add-dir`, a plugin's `skills/` (skills, § where skills
    live) - and `.agents/` is none of them. A repository shared with other agents keeps
    its skills there and Claude sees none of them unless each is linked into
    `.claude/skills/`: 28 of 600 public repositories, often every skill they have.
    """
    root = ctx.root
    found = readable_files((root / ".agents" / "skills").glob("*/SKILL.md"))
    if not found:
        return
    visible = {p.name for p in (root / ctx.skills_dir).iterdir()} if (root / ctx.skills_dir).is_dir() else set()
    missing_skills = sorted(p.parent.name for p in found if p.parent.name not in visible)
    if not missing_skills:
        return
    shown = ", ".join(missing_skills[:6]) + (f" (+{len(missing_skills) - 6})" if len(missing_skills) > 6 else "")
    report.add("48-agents-dir-skills", "WARN",
               f"{len(missing_skills)} of {len(found)} skill(s) in .agents/skills/ have no "
               f"counterpart in {ctx.skills_dir}/: Claude Code does not load skills from .agents/, "
               f"so it never sees them ({shown}). Link each one into {ctx.skills_dir}/ to share it "
               "between tools (skills, where skills live).", str(root / ".agents" / "skills"))
