---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our reviewer subagent is supposed to run a guard before every shell command, but the guard never runs. `scripts/guard.sh` exists and is executable. The agent file:

```markdown
---
name: shop-reviewer
description: Review shop changes before merge. Do not use for writing code.
hooks:
  PreToolUse:
    - matcher: "bash"
      hooks:
        - type: command
          command: "./scripts/guard.sh"
---
Review the diff.
```
