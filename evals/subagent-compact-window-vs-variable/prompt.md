---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our shop reviewer sub-agent sets `autoCompactWindow: 200000` in its frontmatter
(`.claude/agents/shop-review.md`). Our CI job also exports `CLAUDE_CODE_AUTO_COMPACT_WINDOW=500000`
before it starts Claude Code. At what size does that sub-agent compact: 200,000 or 500,000 tokens?
