"""Hook events, types, fields and timeouts."""
from __future__ import annotations



# Hook vocabulary. Source: code.claude.com/docs/en/hooks, read 2026-09-22.
# An event name that is not in this set never fires and never complains: the
# harness has nothing to match it against, so a typo is silent forever. That is
# the whole reason this is a hard-coded list and not a shape check.
KNOWN_HOOK_EVENTS = frozenset({
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PermissionDenied", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "Notification", "MessageDisplay",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted",
    "Stop", "StopFailure", "TeammateIdle", "InstructionsLoaded",
    "ConfigChange", "CwdChanged", "DirectoryAdded", "FileChanged",
    "WorktreeCreate", "WorktreeRemove", "PreCompact", "PostCompact",
    "PreModelSwitch", "PostModelSwitch", "Elicitation", "ElicitationResult",
    "SessionEnd",
})


# "For most events, Claude Code writes stdout to the debug log and doesn't show
# it in the transcript. The exceptions are UserPromptSubmit, UserPromptExpansion,
# SessionStart, and PostModelSwitch, where Claude Code adds plain-text stdout as
# context that Claude can see and act on." Everything a hook on one of these four
# prints is paid for in tokens, in every session, in every project that has it -
# while `claude plugin details` reports a hook as "harness-only, no model context
# cost", which is true of the declaration and false of the output.
CONTEXT_INJECTING_HOOK_EVENTS = frozenset({
    "UserPromptSubmit", "UserPromptExpansion", "SessionStart", "PostModelSwitch",
})


# These events always fire. A `matcher` on them reads as a filter to every human
# who opens the file, and is not one.
MATCHERLESS_HOOK_EVENTS = frozenset({
    "CwdChanged", "UserPromptSubmit", "PostToolBatch", "Stop", "TeammateIdle",
    "TaskCreated", "TaskCompleted", "WorktreeCreate", "WorktreeRemove",
    "MessageDisplay",
})


HOOK_DEFAULT_TIMEOUT = 600          # seconds, for `command`, `http` and `mcp_tool`


# "Claude Code lowers the command, http, and mcp_tool default to 30 on
# UserPromptSubmit, PreModelSwitch, and PostModelSwitch, and to 10 on
# MessageDisplay. SessionEnd hooks share a 1.5-second budget" (hooks, 2026-09-23).
HOOK_EVENT_TIMEOUT = {"UserPromptSubmit": 30, "PreModelSwitch": 30, "PostModelSwitch": 30,
                      "MessageDisplay": 10, "SessionEnd": 1.5}


HOOK_TYPE_FIELDS = {"command": ("command",), "http": ("url",), "mcp_tool": ("server", "tool"),
                    "prompt": ("prompt",), "agent": ("prompt",)}


# "Only evaluated on tool events ... On other events, a hook with `if` set never runs."
HOOK_TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest",
                    "PermissionDenied"}


# Handler types each event runs; an unsupported one "Claude Code skips" (hooks, § prompt-
# based hooks, read 2026-09-27). Events not listed here take all five types.
_CMD_HTTP_MCP = frozenset({"command", "http", "mcp_tool"})


HOOK_EVENT_TYPES = {
    "PermissionRequest": frozenset({"command", "http", "mcp_tool", "prompt"}),
    "SessionStart": frozenset({"command", "mcp_tool"}), "Setup": frozenset({"command", "mcp_tool"}),
    **{e: _CMD_HTTP_MCP for e in (
        "ConfigChange", "CwdChanged", "DirectoryAdded", "Elicitation", "ElicitationResult",
        "FileChanged", "InstructionsLoaded", "MessageDisplay", "Notification", "PostCompact",
        "PostModelSwitch", "PreCompact", "PreModelSwitch", "SessionEnd", "StopFailure",
        "SubagentStart", "WorktreeCreate", "WorktreeRemove")},
}


HOOK_PLUGIN_ROOT_VARS = ("${CLAUDE_PLUGIN_ROOT}", "$CLAUDE_PLUGIN_ROOT")


HOOK_PROJECT_DIR_VARS = ("${CLAUDE_PROJECT_DIR}", "$CLAUDE_PROJECT_DIR")
