"""Tool names, their aliases, and model tiers."""
from __future__ import annotations

import re


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


# Renamed tools that still resolve. The sub-agents page said: "In version 2.1.63, the Task tool
# was renamed to Agent. Existing `Task(...)` references ... still work as aliases." The sentence
# is gone from the documentation (read 2026-10-08); the alias still works - tested on 2.1.293:
# a `deny: ["Task"]` rule removes the Agent tool, as `deny: ["Agent"]` does, and no rule leaves it.
TOOL_ALIASES = {"Task": "Agent"}


# The docs disagree with themselves: tools-reference lists TaskOutput as
# "Deprecated in favor of Read on the task's output file path", permissions lists
# it among "tools Claude Code has removed". Accepted, with a note - never an error.
TOOL_DEPRECATED = {"TaskOutput": "Read on the task's output file path"}


# Source: code.claude.com/docs/en/sub-agents, `model` field, read 2026-09-23.
KNOWN_MODEL_TIERS = {"haiku", "sonnet", "opus", "fable", "inherit"}

# The same field "Accepts the same values as the `--model` flag" (sub-agents), and
# model-config lists more aliases than the five above: `best`, `opusplan`, and the
# `[1m]` forms (read 2026-10-08). `default` is left out: model-config calls it "Not
# itself a model alias". Provider names are open-ended - a Bedrock inference profile
# ARN, a Foundry deployment name, a Vertex version name - so a value outside this
# vocabulary is not proven wrong.
KNOWN_MODEL_ALIASES = KNOWN_MODEL_TIERS | {"best", "opusplan"}


def is_documented_model(value: str) -> bool:
    """An alias (with an optional `[1m]`), an Anthropic model id, or a Bedrock ARN.

    `[1m]` goes "with model aliases or full model names" (model-config); `inherit` is
    neither, it names the main conversation's model (sub-agents). `claude-` counts as the
    start of an id or of a provider segment (`us.anthropic.claude-...`, `.../claude-...`),
    not anywhere: `my-claude-x` matched before (audit 3, g3-02). In any casing: model-config
    reads the `claude-` prefix "in any casing" (external audit 4, te-00).
    """
    v = value.strip()
    one_m = v.lower().endswith("[1m]")
    base = v[:-4] if one_m else v
    if base in KNOWN_MODEL_ALIASES:
        return not (one_m and base == "inherit")
    return bool(re.search(r"(^|[./:])claude-", v, re.IGNORECASE)) or v.startswith("arn:aws:bedrock:")


# Removed from every subagent "even when listed in the `tools` field" (sub-agents,
# read 2026-10-08). ExitPlanMode stays when the subagent's permissionMode is `plan`;
# Agent is removed only at the depth limit, so it is not listed here.
SUBAGENT_REMOVED_TOOLS = {"AskUserQuestion", "EndConversation", "EnterPlanMode", "ExitPlanMode",
                          "ScheduleWakeup", "WaitForMcpServers", "Workflow"}


def is_known_tool(entry: str) -> bool:
    """Accept a bare tool, a parameterised `Tool(...)` form, `mcp__*`, or `*`."""
    name = entry.strip()
    if not name:
        return False
    if name == "*" or name.startswith("mcp__"):
        return True
    return name.split("(", 1)[0].strip() in KNOWN_TOOLS
