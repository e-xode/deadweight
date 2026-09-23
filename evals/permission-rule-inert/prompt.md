---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Claude keeps asking permission to list directories and to clean the build folder in our shop repo, even though our `.claude/settings.json` allows both. Why?

```json
{ "permissions": {
    "allow": ["LS", "Bash(rm -rf dist)"],
    "deny":  ["Bash(rm -rf dist)"] } }
```
