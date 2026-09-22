---
type: llm
weight: 1
---

The run must NOT load the `config-auditor` skill. This is the whole point of the case: a description that fires here is over-triggering, and the failure is invisible from the skill's own file.

A successful response:

- does not trigger: this is application code, outside .claude/ and the plugin manifest
- should not load config-auditor for a code change that touches no configuration
