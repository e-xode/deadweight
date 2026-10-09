---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

My personal agent lives in `~/.claude/agents/shop-terse.md`, not in a project. Is its frontmatter right, and can I audit my `~/.claude` setup the way I audit a project?

```yaml
---
name: shop-terse
description: Answer tersely about the shop catalogue. Do not use for refunds.
observer: true
---
```
