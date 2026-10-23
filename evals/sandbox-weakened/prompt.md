---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Why does this make our sandbox weaker? We put it in the shared `.claude/settings.json` of the shop repository because the sandbox would not start in the unprivileged Docker container our CI runs in.

```json
{ "sandbox": { "enabled": true, "enableWeakerNestedSandbox": true, "network": { "allowLocalBinding": true } } }
```
