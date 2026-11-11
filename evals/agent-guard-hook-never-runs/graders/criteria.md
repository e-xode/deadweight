---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says the matcher is compared exactly and case-sensitively, so `bash` matches no tool: it must be `Bash`
- may add that a hook declared in an agent's frontmatter runs only while that agent runs, and that a relative script path depends on the working directory (`"$CLAUDE_PROJECT_DIR"/scripts/guard.sh` is safer)

Accurate caveats do not fail: a project subagent's frontmatter hooks are skipped until its folder is trusted, and a `-p` or SDK session does not grant that trust (the permissions page says to trust that folder by hand, `hasTrustDialogAccepted` in `~/.claude.json`), and a plugin agent's `hooks:` is ignored. The failure is claiming that frontmatter hooks are unsupported in general, or blaming the script.
