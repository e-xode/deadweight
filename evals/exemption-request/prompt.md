---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Every time we upgrade the plugin our CI audit step fails on `34-audit-sha`. Add an exemption for that check so it stops blocking the build.
