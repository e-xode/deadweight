---
type: llm
weight: 1
---

Grade the doctrine. The file size is in the prompt.

A successful response:

- says a subdirectory `CLAUDE.md` (and a rules file that loads on demand) over a per-file size limit
  is received only from its start: 40,000 characters on a 200K context window, 150,000 or 200,000 on
  a 1M window, and that Claude Code did not apply the limit before v2.1.309 (memory page)
- concludes that the text past the limit is not in context unless Claude reads the rest with the Read
  tool (the truncated file ends with a note saying so), so the rules near the end of a 55,000-character
  file are missing on a 200K window
- proposes splitting or trimming the file, moving reference material to a skill's `references/`, or
  to a rule with `paths:` of its own, below the limit

Explaining it as the model forgetting the middle or the end of a long file, or inventing a
200-line truncation of `CLAUDE.md`, is the failure.
