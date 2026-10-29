---
type: llm
weight: 1
---

Grade the doctrine. The hook is in the prompt.

A successful response:

- says exit 1 is a non-blocking error in general (the action proceeds); only exit 2 blocks through
  the code alone, so on Linux the command runs
- names the documented exception: on Windows WITHOUT Git Bash, a shell-form `PreToolUse` or
  `PermissionRequest` command hook that fails with `onFailure` unset can block the call, and only
  exit code 0 or 2 counts as the hook's verdict (hooks page, "Failed hooks on Windows without Git Bash")
- proposes a fix that fits the intent: `"onFailure": "continue"` to let the call go ahead,
  `"onFailure": "block"` with a script that exits 0 where it only warns, or installing Git for
  Windows (or setting `CLAUDE_CODE_GIT_BASH_PATH`), or, if the guard is meant to block, making it
  exit 2 (on every platform)

Blaming line endings, file permissions or a Claude Code bug without naming the Git Bash condition,
or claiming exit 1 blocks on every platform, is the failure.
