---
type: llm
weight: 1
---

Grade the doctrine. The settings are in the prompt.

A successful response:

- says `LS` is not a current Claude Code tool, so the allow rule approves nothing - and that a
  mistyped allow rule raises no warning, unlike a deny or ask rule
- says rules are evaluated deny, then ask, then allow: the same `Bash(rm -rf dist)` in both
  lists means the allow entry never applies
- proposes a working fix (a real tool such as `Bash(ls *)` or `Glob`; removing the deny, or
  deciding the deny was the intent)

Blaming a caching or restart issue, or inventing a setting, is the failure.
