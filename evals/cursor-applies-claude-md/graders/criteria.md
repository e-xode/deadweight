---
type: llm
weight: 1
---

Grade the substance. The configuration is in the prompt; the sandbox holds no such files. A hedged answer passes when its reasoning is right.

A successful response:

- says yes: Cursor reads `CLAUDE.md` and applies it to every conversation, whatever the rule settings - so an instruction written for Claude Code reaches every Cursor chat
- proposes a fix that keeps Claude Code working: move the release instruction where only Claude Code reads it (the `shop-release` skill itself, a path-scoped rule, or a `.claude/rules/` file), or scope Cursor's behaviour with its own `.cursor/rules/*.mdc`

Saying Cursor ignores `CLAUDE.md`, or blaming the Cursor users' own rules without mentioning `CLAUDE.md`, is the failure.
