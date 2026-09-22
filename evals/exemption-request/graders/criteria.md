---
type: llm
weight: 1
---

The run must load the `config-auditor` skill.

A successful response:

- directs the exemption to the consuming project's .claude/audit.local.json, not to the plugin
- requires a reason and a date on the exemption, and says why a bare path list rots
