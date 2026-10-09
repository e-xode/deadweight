---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says a hook `matcher` is compared with the tool name only: `Bash(git commit*)` holds parentheses,
  so it is read as a regular expression and matches no tool name - the group never fires
- moves the argument filter to the handler's `if` field: `"matcher": "Bash"` and
  `"if": "Bash(git commit*)"`

Blaming workspace trust, the operating system or the script is the failure.
