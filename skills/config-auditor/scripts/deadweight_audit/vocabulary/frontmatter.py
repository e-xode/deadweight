"""Frontmatter keys the harness reads, for skills and agents."""
from __future__ import annotations



# Source: code.claude.com/docs/en/sub-agents, supported frontmatter fields (18; 19 on
# 2026-10-17 with `autoCompactWindow`, "Requires Claude Code v2.1.296 or later").
AGENT_KNOWN_KEYS = {
    "name", "description", "tools", "disallowedTools", "model", "permissionMode",
    "maxTurns", "autoCompactWindow", "skills", "mcpServers", "hooks", "memory", "background", "omitClaudeMd",
    "effort", "isolation", "color", "initialPrompt", "experimental",
}


# sub-agents and settings-reference, read 2026-10-17: "a token count from `100000` to `1000000`".
AUTO_COMPACT_WINDOW_MIN, AUTO_COMPACT_WINDOW_MAX = 100_000, 1_000_000


AGENT_PERMISSION_MODES = {"default", "manual", "acceptEdits", "auto", "dontAsk",
                          "bypassPermissions", "plan"}


# Fields Claude Code ignores on an agent shipped BY A PLUGIN (plugins-reference).
PLUGIN_AGENT_IGNORED_KEYS = {"hooks", "mcpServers", "permissionMode", "initialPrompt"}  # plugins/components, 2026-09-27


# Source: code.claude.com/docs/en/skills, frontmatter reference (20 fields).
SKILL_KNOWN_KEYS = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
    "metadata", "license", "compatibility",
}


AGENT_VALIDATED_KEYS = AGENT_KNOWN_KEYS
