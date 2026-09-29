---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

In our shop repository, Cursor never applies this rule, although it says it should always apply. Claude Code users are fine. Here is the file, `.cursor/rules/shop-api.md`:

```markdown
---
description: Conventions for the shop API handlers
alwaysApply: true
---
Validate every request body with the shared schema before touching the database.
```
