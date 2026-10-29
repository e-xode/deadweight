---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

`src/billing/CLAUDE.md` in our shop repo is about 55,000 characters long. Claude follows the rules
at the top of it but seems to know nothing about the ones near the end. The file loads (Claude quotes
the rules at its top). What is happening, and what should we do about it?
