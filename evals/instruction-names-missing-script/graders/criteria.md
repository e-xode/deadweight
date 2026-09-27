---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says `npm run test:e2e` is not defined in `package.json`, so the instruction sends Claude to a command that fails
- proposes fixing the instruction (name the command that exists, `npm test`) or adding the missing script - and treating CLAUDE.md as code that is pruned when the repository changes

Blaming the test framework or the model's behaviour, without noticing the missing script, is the failure.
