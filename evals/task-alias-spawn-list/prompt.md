---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Our `shop-lead` subagent should only be able to hand work to `shop-tests` and `shop-lint`, but it still delegates to other agents. Its frontmatter:

```yaml
name: shop-lead
description: Coordinate the shop release checks. Do not use for refunds.
tools: Read, Task(shop-tests), Task(shop-lint)
```
