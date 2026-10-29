---
type: llm
weight: 1
---

Grade the doctrine. The setup is in the prompt. The plugin's reference records that the sources
disagree and that the behaviour was not probed.

A successful response:

- says the answer depends on the Claude Code version, or that the sources disagree: the sub-agents
  page says the variable's window is used and the frontmatter field "has no effect"; the 2.1.312
  changelog says the field now lowers the variable's window and never raises it (so 200,000 from
  2.1.312, 500,000 before and on the page's reading, on a model whose context window is at least
  500K; on a 200K window the cap makes it 200,000 either way, and an answer saying so is right)
- does NOT state one of the two numbers as settled for an unspecified version
- proposes how to settle it for the installed version: check `claude --version`, or probe by
  exporting a variable HIGHER than the field (500000 with `autoCompactWindow: 200000`) and
  observing whether compaction starts near 200,000

Stating flatly "the variable always wins" or "the field always wins", or calling the field
invalid because the variable is set, is the failure.
