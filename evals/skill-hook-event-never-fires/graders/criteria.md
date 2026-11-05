---
type: llm
weight: 1
---

Grade the doctrine. The frontmatter is in the prompt.

A successful response:

- says hooks declared in a skill's frontmatter for `SessionEnd` and `PreCompact` are accepted without error but do not fire, while the same events declared in settings.json do fire
- says this was observed (measured) on Claude Code and is not stated in the documentation
- recommends moving those hooks to `settings.json` (or the plugin's hooks file)

Blaming the script path or its permissions without evidence, or presenting the list of events as documented by Anthropic, is the failure.
