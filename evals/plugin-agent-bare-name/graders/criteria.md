---
type: llm
weight: 1
---

Grade the doctrine. The command text is in the prompt.

A successful response:

- says a plugin agent is registered under a scoped name `shop-tools:security-auditor`, so the Agent tool called with the bare name fails with "Agent type 'security-auditor' not found"
- recommends writing the scoped name in the command
- does not claim the bare name always resolves; if it says the command is wrong, it either notes that in the runs measured the model usually used the scoped name anyway, or gives the scoped name as the fix

Saying the bare name works, or that the Agent tool accepts any agent file name, is the failure.
