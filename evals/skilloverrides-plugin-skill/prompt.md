---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

We want to hide the skill `lint` of the plugin `acme-tools` from the listing, so we wrote in `.claude/settings.json`: `{ "skillOverrides": { "acme-tools:lint": "off" } }`. It is still listed with its full description. Why?
