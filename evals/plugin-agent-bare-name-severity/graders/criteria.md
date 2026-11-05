---
type: llm
weight: 1
---

Grade the doctrine.

A successful response:

- says the bare name is not registered for a plugin agent (the Agent tool called directly with it fails with "not found"), so the scoped name is the correct form
- says that it is NOT certain the commands fail: in the runs measured (9 of 9) a model following such a command used the scoped name from its first call, so no failure was seen, which is why the auditor reports it as a NOTICE and not a warning
- recommends the one-line fix without calling it a release blocker

Stating that all six commands will certainly fail, or that this must block the release, is the failure.
