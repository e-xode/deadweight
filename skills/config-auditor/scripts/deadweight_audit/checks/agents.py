"""Sub-agents: frontmatter, tools, preloaded skills."""
from __future__ import annotations

import json
import re

from ..context import AuditContext
from ..parsing.frontmatter import (
    YAML_TRUE,
    frontmatter_keys,
    frontmatter_list,
    frontmatter_raw_value,
    frontmatter_yaml_error,
    parse_frontmatter,
)
from ..repo import readable_files
from ..report import Report
from ..vocabulary.frontmatter import (
    AGENT_PERMISSION_MODES,
    AGENT_VALIDATED_KEYS,
    PLUGIN_AGENT_IGNORED_KEYS,
)
from ..vocabulary.tools import (
    KNOWN_MODEL_ALIASES,
    SUBAGENT_REMOVED_TOOLS,
    TOOL_ALIASES,
    TOOL_DEPRECATED,
    is_documented_model,
    is_known_tool,
)


def _main_thread_agents(ctx: AuditContext) -> set[str]:
    """Agents named by the `agent` setting: they run as the main thread, not as subagents.

    "To make it the default for every session in a project, set `agent` in
    `.claude/settings.json`" (sub-agents, on running an agent as the main thread).
    """
    names = set()
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((ctx.root / ctx.claude_dir / name).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("agent"), str):
            names.add(data["agent"].strip())
    return names


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
        rel = entry.relative_to(agents_dir)
        if not text.startswith("---") and text.lstrip().startswith("---"):
            # A separate cause in the docs, and a different fix: the YAML may be fine.
            report.add("08-agent-frontmatter", "ERROR",
                       f"'{rel}' opens its frontmatter after line 1: Claude Code reads a file whose "
                       "opening --- is not the first line as having no frontmatter and treats it "
                       "as documentation, so this agent does not load (sub-agents). Make --- the "
                       "first line.", str(entry))
            continue
        # parse_frontmatter is tolerant and reads fields out of a frontmatter Claude Code
        # rejects whole: "YAML that doesn't parse: Claude Code reads no fields from the
        # file, skips it" (sub-agents). Without this, such agents were counted as live.
        yaml_error = frontmatter_yaml_error(text) if fm else None
        if ctx.layout == "plugin" and (yaml_error or fm == {}):
            # "A plugin subagent whose frontmatter has no `name` or doesn't parse still
            # loads, under its filename" (sub-agents): no ERROR "does not load" here.
            why = f"does not parse ({yaml_error})" if yaml_error else "is empty"
            report.add("08-agent-frontmatter", "WARN",
                       f"Plugin agent '{entry.stem}' has a frontmatter that {why}: it loads under "
                       "its filename with no field read, so Claude has no description to decide "
                       "when to delegate to it (sub-agents).", str(entry))
            agents[entry.stem] = {"name": "", "description": "", "path": str(entry)}
            continue
        if yaml_error:
            report.add("08-agent-frontmatter", "ERROR",
                       f"'{rel}' has a frontmatter that does not parse as YAML ({yaml_error}): "
                       "Claude Code reads no fields from it and skips this agent (sub-agents; "
                       "shape rejected by `claude plugin validate` 2.1.294).", str(entry))
            continue
        if not fm:
            # No frontmatter at all is a document someone keeps in agents/ (a routing
            # guide, a reference) - not loaded as an agent. A frontmatter that does not
            # parse is an agent that silently fails to load.
            broken = text.lstrip().startswith("---")
            report.add(
                "08-agent-frontmatter",
                "ERROR" if broken else "WARN",
                f"'{rel}' " + (
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
        raw_desc = frontmatter_raw_value(text, "description") or ""
        if desc and desc[0] in (">", "|") and raw_desc[:1] in (">", "|"):
            # A quoted "> ..." is a description that starts with '>', and `>2`/`|2-` are
            # block headers the parser now reads: neither reaches here. What is left is a
            # header followed by text on the same line - not standard YAML, yet accepted
            # by `claude plugin validate` 2.1.294. The parser's reading, not the file's fault.
            report.add(
                "02-frontmatter-block-scalar",
                "INFO",
                f"Agent '{entry.stem}' description opens with '{raw_desc[0]}' followed by text on "
                "the same line: this auditor's parser reads it as text starting with "
                f"'{raw_desc[0]}', which strict YAML parsers reject. Quote the value to be read "
                "the same everywhere.",
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
    main_thread = _main_thread_agents(ctx)
    for entry in readable_files(agents_dir.rglob("*.md")):
        try:
            text = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, _ = parse_frontmatter(text)
        # A frontmatter Claude Code cannot parse has no field it reads: judging the
        # fields this tolerant parser still extracts gave "unknown tool 'model: sonnet'".
        if not fm or frontmatter_yaml_error(text):
            continue
        ident = (fm.get("name") or entry.stem).strip()
        as_main = ident in main_thread

        declared_tools = frontmatter_list(fm.get("tools", ""))
        unknown = []
        removed = []
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
                if (base in SUBAGENT_REMOVED_TOOLS and not as_main
                        and not (base == "ExitPlanMode" and fm.get("permissionMode", "").strip() == "plan")):
                    removed.append(base)
                continue
            unknown.append(tool)
        # The harness drops an entry it cannot resolve and launches with the rest; only
        # an agent left with NO tool "fails to launch". Severity follows that. A tool
        # removed from every subagent resolves to nothing there either: "names a tool
        # that isn't available to subagents" is one of the docs' two examples.
        none_left = bool(declared_tools) and len(unknown) + len(removed) == len(declared_tools)
        for tool in unknown:
            report.add(
                "23-agent-tools",
                "ERROR" if none_left else "WARN",
                f"Agent '{entry.stem}' grants unknown tool '{tool}'. Unresolvable entries are "
                "dropped; parameterised forms like 'Bash(git diff *)' and 'mcp__*' names are "
                "accepted (tools-reference).",
                str(entry),
            )
        for tool in removed:
            report.add(
                "23-agent-tools",
                "ERROR" if none_left else "WARN",
                f"Agent '{entry.stem}' grants '{tool}', which Claude Code removes from every "
                "subagent even when listed (sub-agents)" + (
                    ": no entry is left, and Claude Code usually refuses to launch a subagent "
                    "with nothing resolvable." if none_left else
                    ": as a subagent it runs without it."),
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
                    # The flag marks workflows Claude must not start on its own, and Claude
                    # Code tells Claude "not to reproduce the deploy steps another way"
                    # (skills): advising to read the file by path got around it.
                    f"Agent '{entry.stem}' preloads '{preload}', which carries "
                    "'disable-model-invocation: true': the preload is skipped (sub-agents). "
                    "Remove the entry, or drop the flag if Claude may invoke that skill on its "
                    "own (skills).",
                    str(entry),
                )

        model = fm.get("model", "").strip()
        if model and not is_documented_model(model):
            # NOTICE, not WARN: the field takes "the same values as the `--model` flag"
            # (sub-agents), which include a Foundry deployment name or a Vertex version
            # name - free-form strings no vocabulary can rule out.
            report.add(
                "23-agent-model",
                "NOTICE",
                f"Agent '{entry.stem}' declares model '{model}', which is not a documented alias "
                f"({', '.join(sorted(KNOWN_MODEL_ALIASES))}; [1m] goes on an alias other than inherit) nor a "
                "'claude-*' model id or Bedrock ARN"
                + (": model-config calls 'default' \"Not itself a model alias\"."
                   if model == "default" else
                   ". Fine if it is a provider deployment or version name, a typo otherwise "
                   "(model-config)."),
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
        # `Task(...)` too: the old name of the tool still resolves to Agent (tested 2026-10-08,
        # 2.1.293: a `deny: ["Task"]` rule removes the Agent tool), and anthropics/claude-code
        # #28277 restricts a subagent with `Task(a), Task(b)`.
        spawn = re.search(r"\b(Agent|Task)\([^)]*\)", fm.get("tools", ""))
        if spawn and not as_main:
            report.add("23-agent-tools", "WARN",
                       f"Agent '{entry.stem}' restricts spawnable types with '{spawn.group(1)}(...)': that list "
                       "applies only to an agent run as the main thread with `claude --agent`; in "
                       "a subagent definition it is ignored (sub-agents).", str(entry))
        if ":" in fm.get("name", ""):
            report.add("08-agent-frontmatter", "ERROR",
                       f"Agent '{entry.stem}' has a ':' in its name: the file is not loaded "
                       "(sub-agents, 2.1.218).", str(entry))
        # The two other name rules of the same docs list, for the directories it covers
        # ("a project, user, or managed `agents` directory").
        name = fm.get("name", "")
        if ctx.layout != "plugin" and name.startswith("-"):
            report.add("08-agent-frontmatter", "ERROR",
                       f"Agent '{entry.stem}' has a name starting with '-': Claude Code skips "
                       "the file (sub-agents).", str(entry))
        if ctx.layout != "plugin" and len(name) > 256:
            report.add("08-agent-frontmatter", "ERROR",
                       f"Agent '{entry.stem}' has a name of {len(name)} characters (> 256): "
                       "Claude Code skips the file (sub-agents).", str(entry))
        if ctx.layout == "plugin":
            for key in sorted(PLUGIN_AGENT_IGNORED_KEYS & set(frontmatter_keys(text))):
                report.add("23-agent-frontmatter-keys", "WARN",
                           f"Agent '{entry.stem}' sets '{key}', which Claude Code ignores on an "
                           "agent shipped by a plugin (plugins-reference).", str(entry))

        for key in frontmatter_keys(text):
            inventory[key] = inventory.get(key, 0) + 1
            if key not in AGENT_VALIDATED_KEYS:
                unvalidated[key] = unvalidated.get(key, 0) + 1
                report.add("23-agent-frontmatter-keys", "WARN", _unknown_agent_key(entry.stem, key, ctx.layout),
                           str(entry))

    if inventory:
        seen = ", ".join(f"{k} ({v})" for k, v in sorted(inventory.items()))
        drift = ", ".join(f"{k} ({v})" for k, v in sorted(unvalidated.items())) or "none"
        report.add(
            "23-agent-frontmatter-keys",
            "INFO",
            f"Agent frontmatter keys in use: {seen}. Keys this script does not validate: {drift}.",
            str(agents_dir),
        )


# What a misspelt field was meant to do, and does not: the field is ignored, so its effect is absent.
_LOST_EFFECT = {
    "tools": "the agent is not limited to the tools it lists",
    "disallowedTools": "the tools it lists stay available",
    "maxTurns": "no turn limit is set by it",
    "permissionMode": "the mode it names is not applied",
}


def _unknown_agent_key(agent: str, key: str, layout: str = "project") -> str:
    """The 23 message for a key outside the documented subagent fields.

    The sub-agents page: field names "must match the table exactly: Claude Code ignores a
    field it doesn't recognize without reporting an error". A misspelt field
    (`disallowed-tools`, `maxturns`) is the case that costs, because the restriction it
    carries is silently off: that message quotes the page and names the field. Any other
    undocumented key keeps the 0.23.0 hedge - the CLI schema has accepted undocumented keys
    (`observer`, anthropics/claude-code#93109), so "ignored" would be more than is known.
    In a plugin, renaming a field the plugin loader ignores whatever its spelling
    (`permissionMode`, `mcpServers`, `initialPrompt`, `hooks`) applies nothing.
    """
    norm = lambda k: re.sub(r"[-_\s]", "", k).lower()  # noqa: E731
    meant = next((k for k in sorted(AGENT_VALIDATED_KEYS) if norm(k) == norm(key)), None)
    doc = ("\"Claude Code ignores a field it doesn't recognize without reporting an error\" "
           "(sub-agents)")
    if meant and layout == "plugin" and meant in PLUGIN_AGENT_IGNORED_KEYS:
        return (f"Agent '{agent}' sets '{key}', a misspelling of the documented field '{meant}', "
                "which Claude Code ignores on an agent shipped by a plugin whatever its spelling "
                "(plugins-reference): renaming it would not apply it. To use it, the agent must "
                "be a project or user agent (.claude/agents/).")
    if meant:
        lost = _LOST_EFFECT.get(meant, "its value is not applied")
        return (f"Agent '{agent}' sets '{key}', a misspelling of the documented field '{meant}': "
                f"{doc}, so {lost}. Rename it '{meant}'.")
    return (f"Agent '{agent}' sets '{key}', which is not a documented subagent field "
            f"(sub-agents lists {len(AGENT_VALIDATED_KEYS)}): nothing guarantees it is read, "
            "now or after an update.")


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
