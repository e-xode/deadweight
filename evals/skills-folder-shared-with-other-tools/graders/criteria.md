---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says Claude Code finds skills by location, and `.agents/skills/` is not one of them (project skills live in `.claude/skills/<name>/SKILL.md`)
- keeps the single shared copy: link each skill folder into `.claude/skills/` (a symlink per skill), or move them and point the other tool there
- does not blame the descriptions or the frontmatter, which are not the cause here

Rewriting the skills' descriptions, or saying Claude Code reads `.agents/`, is the failure.
