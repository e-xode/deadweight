---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

In `.claude/skills/notes/SKILL.md` we put hooks in the frontmatter so that notes are saved when the session ends and before compaction:

```
hooks:
  SessionEnd:
    - hooks: [{ type: command, command: ./scripts/save-notes.sh }]
  PreCompact:
    - hooks: [{ type: command, command: ./scripts/save-notes.sh }]
```

Claude Code reports no error, but the script never runs. Why, and what should we do?
