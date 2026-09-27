---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says the matcher is compared exactly and case-sensitively, so `bash` matches no tool: it must be `Bash`
- may add that a hook declared in an agent's frontmatter runs only while that agent runs, and that a relative script path depends on the working directory (`"$CLAUDE_PROJECT_DIR"/scripts/guard.sh` is safer)

Saying frontmatter hooks are not supported, or blaming the script, is the failure.
