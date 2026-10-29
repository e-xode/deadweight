---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our shop repo has a `PreToolUse` hook on `Bash` in `.claude/settings.json`:
`{ "type": "command", "command": "./scripts/guard.sh" }`. The script exits 1 when it dislikes a
command. On Linux the command still runs, which is what we saw. A teammate on Windows says the same
command gets blocked. Why does the platform change the outcome?
