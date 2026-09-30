"""Tool names, their aliases, and model tiers."""
from __future__ import annotations



# Vocabulary lists are the fastest-rotting part of an auditor: every tool, model
# or field the harness adds becomes a false positive in every project, with no
# change to this plugin. Each list names its source page; `derive.py` on the
# maintainer side compares them to the live docs before a release.
# Source: code.claude.com/docs/en/tools-reference, read 2026-09-23 (46 names).
KNOWN_TOOLS = {
    "Agent", "Artifact", "AskUserQuestion", "Bash", "CronCreate", "CronDelete", "CronList",
    "Edit", "EndConversation", "EnterPlanMode", "EnterWorktree", "ExitPlanMode",
    "ExitWorktree", "Glob", "Grep", "ListAgents", "ListMcpResourcesTool", "LSP", "Monitor",
    "NotebookEdit", "PowerShell", "PushNotification", "Read", "ReadMcpResourceTool",
    "RemoteTrigger", "ReportFindings", "ScheduleWakeup", "SendFeedback", "SendMessage",
    "SendUserFile", "ShareOnboardingGuide", "Skill", "SubagentHandback", "TaskCreate",
    "TaskGet", "TaskList", "TaskOutput", "TaskStop", "TaskUpdate", "TodoWrite", "ToolSearch",
    "WaitForMcpServers", "WebFetch", "WebSearch", "Workflow", "Write",
}


# Renamed tools that still resolve. "In version 2.1.63, the Task tool was renamed to
# Agent. Existing `Task(...)` references ... still work as aliases." (sub-agents)
TOOL_ALIASES = {"Task": "Agent"}


# The docs disagree with themselves: tools-reference lists TaskOutput as
# "Deprecated in favor of Read on the task's output file path", permissions lists
# it among "tools Claude Code has removed". Accepted, with a note - never an error.
TOOL_DEPRECATED = {"TaskOutput": "Read on the task's output file path"}


# Source: code.claude.com/docs/en/sub-agents, `model` field, read 2026-09-23.
KNOWN_MODEL_TIERS = {"haiku", "sonnet", "opus", "fable", "inherit"}


def is_known_tool(entry: str) -> bool:
    """Accept a bare tool, a parameterised `Tool(...)` form, `mcp__*`, or `*`."""
    name = entry.strip()
    if not name:
        return False
    if name == "*" or name.startswith("mcp__"):
        return True
    return name.split("(", 1)[0].strip() in KNOWN_TOOLS
