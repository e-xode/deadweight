---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our skill `.claude/skills/ship/SKILL.md` never fires and `/skills` lists it with no description. Its frontmatter is:

```
---
name: ship
description: Use when releasing --- run after the tests pass, never before.
allowed-tools: Bash(git *)
---
```

The YAML looks valid to us. What is wrong, and how do we fix it?
