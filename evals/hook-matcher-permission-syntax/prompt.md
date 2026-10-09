---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

The first of these two hooks in our shop repo never runs, not even once, while the second one does. The script works when we run it by hand. What's wrong?

```json
{ "hooks": { "PreToolUse": [
    { "matcher": "Bash(git commit*)",
      "hooks": [{ "type": "command", "command": "node tools/shop-guard/pre-commit-audit.js", "timeout": 30 }] },
    { "matcher": "Bash",
      "hooks": [{ "type": "command", "command": "node tools/shop-guard/bash-guard.js", "timeout": 30 }] } ] } }
```
