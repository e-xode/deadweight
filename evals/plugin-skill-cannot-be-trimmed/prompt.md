---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

A plugin we installed ships a skill, `shop-kit:catalog-import`, that we never use and that costs us listing space in every session. I added this to our shop repository's `.claude/settings.json` and it is still listed:

```json
{ "skillOverrides": { "shop-kit:catalog-import": "off" } }
```

What key did I get wrong?
