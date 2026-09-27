---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Security review before we commit our `.mcp.json` to the shop repository. Anything to change?

```json
{ "mcpServers": {
    "shop-docs": { "command": "npx", "args": ["-y", "shop-docs-mcp"] },
    "shop-db":   { "command": "npx", "args": ["-y", "shop-db-mcp@1.4.2"] } } }
```
