---
type: llm
weight: 1
---

Grade the doctrine, not a measurement. The eval sandbox masks the workspace's `.claude/`
files, so `33-description-overlap` reports `0 listed description(s)` here and there are no
pairs to read — a rubric that demands the finding fails for a reason unrelated to the skill.

A successful response:

- locates the defect **in the set, not in either file**: each description can be faultless on
  its own and still collide with its neighbour, which is why "nothing looks wrong in either
  file" is the expected symptom rather than a contradiction
- names `33-description-overlap` as the mechanical instrument and says what it compares —
  listed descriptions against each other, not against the request
- says plainly that a static overlap check tells you which descriptions *look* confusable and
  never which one actually wins; only runtime invocation counts (`/skill-doctor`, `/usage`)
  settle that
- offers the two real fixes: crossed anti-triggers naming each other, or a merge when the
  two subjects turn out to be one
- states it could not read this workspace, rather than inventing a pair

Inventing a colliding pair for skills it could not open is the failure that matters most here.
