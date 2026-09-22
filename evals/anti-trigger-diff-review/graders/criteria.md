---
type: llm
weight: 1
---

The run must NOT load the `config-auditor` skill. This is the whole point of the case: a description that fires here is over-triggering, and the failure is invisible from the skill's own file.

A successful response:

- does not trigger: reviewing a diff is a code-review task, not a configuration audit
- should not load config-auditor unless the diff changes CLAUDE.md, skills, agents, rules or settings
