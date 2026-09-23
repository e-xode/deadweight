---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Neither of these two hooks in our shop repo ever runs, and nothing reports an error. What's wrong?

```json
{ "hooks": {
    "PreToolUse":   [{ "matcher": "mcp__shop-api",
                       "hooks": [{ "type": "command", "command": "./scripts/log-mcp.sh", "timeout": 5 }] }],
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "./scripts/banner.sh",
                                   "if": "Bash(git *)", "timeout": 5 }] }] } }
```
