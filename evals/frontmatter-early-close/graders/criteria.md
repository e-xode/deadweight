---
type: llm
weight: 1
---

Grade the doctrine. The frontmatter is in the prompt.

A successful response:

- says Claude Code closes the frontmatter at the FIRST `---` it meets, here inside the description value, so the description is cut (to `Use when releasing`) and the keys after it are not read
- says this is observed behaviour of Claude Code and not something the documentation states
- fixes it by removing `---` from the value

Saying the YAML is valid so the cause is elsewhere (trigger wording, budget), or presenting the closing rule as official documentation, is the failure.
