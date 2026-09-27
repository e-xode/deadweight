---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

We added this to `.claude/settings.json` to keep Claude out of `secrets/`, and yesterday it edited `secrets/stripe.env` anyway. Why didn't the rule stop it?

```json
{ "permissions": { "deny": ["Write(secrets/**)"] } }
```
