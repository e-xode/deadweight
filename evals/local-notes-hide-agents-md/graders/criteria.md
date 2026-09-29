---
type: llm
weight: 1
---

Grade the substance. The configuration is in the prompt; the sandbox holds no such files. A hedged answer passes when its reasoning is right.

A successful response:

- says the `CLAUDE.local.md` is the cause: by default Claude Code reads `AGENTS.md` only when no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists, and a `CLAUDE.local.md` counts - so on this machine `AGENTS.md` stopped loading
- gives a fix: import it with `@AGENTS.md` at the top of the `CLAUDE.local.md`, or set Project instructions to read both (`claude-md-and-agents-md`) in user settings - not in the project's settings, where it is ignored

Blaming the notes' content, a cache, or a model change, or saying `CLAUDE.local.md` only adds to `AGENTS.md`, is the failure.
