---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

We're about to commit these two files in our shop repository so the whole team gets the MCP server. Anything wrong with them?

`.mcp.json`:
```json
{ "mcpServers": { "shop-api": { "type": "http", "url": "https://mcp.shop.example/api",
  "headers": { "Authorization": "Bearer 9f8e7d6c5b4a39281706f5e4d3c2b1a0" } } } }
```

`.claude/settings.json`:
```json
{ "enableAllProjectMcpServers": true }
```
