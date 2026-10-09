---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says a hook whose script does not exist cannot start and lands in the non-blocking bucket: the
  tool call proceeds, with at most a `hook error` notice in the transcript - the guard fails open
- says only exit code 2 (or a valid JSON decision) blocks, so a missing or crashing guard never blocks
- proposes a way to catch it before it matters: keep the script in the repository and call it through
  `"$CLAUDE_PROJECT_DIR"/...`, and check that every hook command points to an existing file (an audit
  that resolves `~/`, `$HOME/`, absolute and relative paths does this)

Saying the hook was blocked by a permission, or that a missing script raises a blocking error, is the failure.
