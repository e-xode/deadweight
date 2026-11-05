---
type: llm
weight: 1
---

Grade the doctrine. The setup is in the prompt.

A successful response:

- says Claude Code expands an `@path` import in a memory file such as AGENTS.md (documented, memory page), and that Codex is understood not to: from a reading of its source (agents_md.rs) the line is passed to the model as text; it labels this a source reading, not a run and not Codex documentation
- concludes that Codex users do not get the content of `docs/commands.md` through the import
- recommends inlining what Codex must see in the file (or accepting the gap), and does not claim certainty about Codex beyond the source reading

Stating as a fact that Codex has no import support without saying where that comes from, or blaming Claude Code, is the failure.
