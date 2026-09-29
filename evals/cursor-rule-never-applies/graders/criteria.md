---
type: llm
weight: 1
---

Grade the substance. The configuration is in the prompt; the sandbox holds no such files. A hedged answer passes when its reasoning is right.

A successful response:

- says Cursor's project rules must be `.mdc` files: a plain `.md` in `.cursor/rules/` is ignored by the rules system, frontmatter or not
- tells them to rename it `shop-api.mdc` (or to put plain markdown in `AGENTS.md` instead)

Rewriting the frontmatter (quotes, `globs`, `alwaysApply`) as the fix while keeping the `.md` extension is the failure.
