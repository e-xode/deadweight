---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our `.claude/settings.local.json` in the shop-api repo is supposed to keep Claude out of a sibling repository, and yesterday it edited a file in `/home/dev/shop-legacy` anyway. Why didn't these rules stop it?

```json
{ "permissions": { "deny": [
    "Edit(/home/dev/shop-legacy/**)",
    "Write(/home/dev/shop-legacy/**)",
    "NotebookEdit(/home/dev/shop-legacy/**)" ] } }
```
