---
type: llm
weight: 1
---

Grade the doctrine. The two lines are in the prompt.

A successful response:

- says neither line imports its file: an `@path` followed by punctuation (`.`, `:`, `,`, `;`, `!`,
  `?`, `)`, `"`) does not load
- labels that as a measured observation of one release (one probe, Claude Code 2.1.302; naming the
  plugin's probe is not required), not as a rule Anthropic documents, or says the documentation does
  not state it
- fixes it by ending the path with a space or a line end (the import alone on its line, or
  followed by a space), and suggests checking with `/memory` or an `InstructionsLoaded` hook

Saying the lines work and the model ignored them, or presenting the punctuation rule as official
documentation, is the failure.
