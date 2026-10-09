---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says `observer` is not a documented subagent field: nothing guarantees it is read, now or after an
  update - without claiming it is certainly ignored
- says `~/.claude` holds user-scope configuration, whose rules differ from a project's, so a project
  audit does not apply to it as is (an audit run on the home directory says so instead of auditing it)

Stating as a fact that `observer` is ignored, or auditing `~/.claude` with project rules, is the failure.
