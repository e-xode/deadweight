---
type: llm
weight: 1
---

The run must load the `config-auditor` skill.

A successful response:

- loads config-auditor and runs scripts/audit.py rather than reading CLAUDE.md by hand
- reports the always-loaded budget as CLAUDE.md bytes plus skill and agent descriptions, not CLAUDE.md alone
