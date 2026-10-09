---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

We have a guard hook in the shop repo that should stop force-pushes. It stopped working after a cleanup and Claude force-pushed. Nothing blocked. What happened, and how do we catch this next time?

```json
{ "hooks": { "PreToolUse": [
    { "matcher": "Bash",
      "hooks": [{ "type": "command", "command": "bash ~/.shop/guards/no-force-push.sh", "timeout": 10 }] } ] } }
```

`ls ~/.shop/guards/` now says: No such file or directory.
