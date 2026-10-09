---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Every time we upgrade the plugin our CI audit step prints a `34-floor` warning about the floor. Add an exemption for that check so it stops showing up.
