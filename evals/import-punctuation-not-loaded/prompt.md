---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our shop `CLAUDE.md` says: `Follow the naming rules in @docs/naming.md.` and
`See @docs/refunds.md: the refund rules.` The files exist. Claude behaves as if it had never read
them. Do those lines import the files, and how do we make them load?
