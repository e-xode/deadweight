---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- reads `Task(...)` as the old name of the `Agent` tool
- says a list of spawnable agent types in `tools` applies only to an agent run as the main thread
  (`claude --agent`); in a subagent definition it does not restrict what the subagent can call
- gives a working alternative: run `shop-lead` as the main agent, or restrict delegation another way

Saying the list is applied in a subagent, or that `Task` is an unknown tool, is the failure.
