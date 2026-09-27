---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

We moved our skills to `.agents/skills/` so our other coding agent and Claude Code share one copy. Since then Claude never uses any of them - `/shop-release` isn't even offered. Nothing errors. Layout:

```
.agents/skills/shop-release/SKILL.md
.agents/skills/shop-refunds/SKILL.md
CLAUDE.md
```
