"""Frontmatter keys the harness reads, for skills and agents."""
from __future__ import annotations



# Source: code.claude.com/docs/en/sub-agents, supported frontmatter fields (18).
AGENT_KNOWN_KEYS = {
    "name", "description", "tools", "disallowedTools", "model", "permissionMode",
    "maxTurns", "skills", "mcpServers", "hooks", "memory", "background", "omitClaudeMd",
    "effort", "isolation", "color", "initialPrompt", "experimental",
}


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
