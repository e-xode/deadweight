---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Two of our skills keep firing on each other's requests. Nothing looks wrong in either file. Their
frontmatter:

```yaml
# .claude/skills/shop-refunds/SKILL.md
name: shop-refunds
description: Handle refund requests in the shop checkout - partial refunds, chargebacks, refund windows and receipts for customers.

# .claude/skills/shop-payouts/SKILL.md
name: shop-payouts
description: Handle refund requests in the shop checkout - partial refunds, chargebacks, refund windows and receipts for merchants.
```
