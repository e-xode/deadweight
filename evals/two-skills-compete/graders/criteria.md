---
type: llm
weight: 1
---

Grade the doctrine. The two descriptions are in the prompt; the sandbox holds no such files
(it masks the workspace's `.claude/`), so the answer reads the pair from the prompt.

A successful response:

- locates the defect **in the set, not in either file**: each description can be faultless on
  its own and still collide with its neighbour, which is why "nothing looks wrong in either
  file" is the expected symptom rather than a contradiction
- says plainly that a static overlap check tells you which descriptions *look* confusable and
  never which one actually wins; only runtime invocation counts (`/skill-doctor`, `/usage`)
  settle that
- offers crossed anti-triggers naming each other as the fix (a merge is an option only if the
  two subjects turn out to be one)
- reads the pair it was given: the two descriptions differ only by their last word
  (customers / merchants) and carry no anti-trigger naming each other

Blaming one file alone, or calling the pair fine, is the failure that matters most here.
