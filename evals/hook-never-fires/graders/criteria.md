---
type: llm
weight: 1
---

Grade the doctrine. The hooks are in the prompt.

A successful response:

- says `mcp__shop-api` is compared as an exact string and matches no tool; every tool of the
  server needs `mcp__shop-api__.*`
- says `if` is evaluated on tool events only (PreToolUse, PostToolUse, PostToolUseFailure,
  PermissionRequest, PermissionDenied); on SessionStart a hook with `if` never runs - drop the
  `if` or move the hook
- does not claim the scripts are missing or non-executable without evidence

Suggesting a restart, or only one of the two causes, is the failure.
