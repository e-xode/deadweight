---
type: llm
weight: 1
---

Grade the doctrine. The line is in the prompt.

A successful response:

- says the line is not valid strict YAML (an unquoted `[--dry-run]` opens and closes a flow sequence, and the text that follows it, ` [path]`, is then rejected by a strict parser) AND that Claude Code reads it tolerantly: measured, the command is listed and runs (2.1.317), so the reviewer is right about YAML and the command is not broken in Claude Code
- says the risk is another reader of the file (a strict YAML parser) and cites a public report where one dropped the whole command
- recommends quoting the value, and says what the unquoted hint does to the argument hint shown in the interactive menu was not measured

Saying Claude Code refuses to load the command, or that nothing needs doing because Claude Code accepts it with no mention of other readers, is the failure.
