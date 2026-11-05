---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

A reviewer says our command `commands/deploy.md` is broken because its frontmatter has `argument-hint: [--dry-run] [path]` (unquoted) and that is not valid YAML. The command works for us in Claude Code. Who is right, and what should we do?
