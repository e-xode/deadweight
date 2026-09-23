#!/usr/bin/env bash
# A configuration with no error and no warning, and two notices: a pair of skills
# separated only by their descriptions, and an angle bracket in a description.
# Neither depends on git: the eval sandbox blocks it, and a notice that needs git
# (a rule glob into an ignored folder) came back as a WARN there.
# Until 0.12.0 both were INFO, and the reply to this prompt was "0 errors, 0 warnings".
set -e
git init -q .
printf '# shop-api\n\nRun `make test` before any change.\n' > CLAUDE.md
mkdir -p .claude/skills/shop-refunds .claude/skills/shop-payouts
cat > .claude/skills/shop-refunds/SKILL.md <<'MD'
---
name: shop-refunds
description: Handle refund requests in the shop checkout - partial refunds, chargebacks, refund windows and receipts for customers (refund window <30 days). Do not use for merchant receipts (use shop-payouts).
---

Refunds follow the refund window of the order.
MD
cat > .claude/skills/shop-payouts/SKILL.md <<'MD'
---
name: shop-payouts
description: Handle refund requests in the shop checkout - partial refunds, chargebacks, refund windows and receipts for merchants. Do not use for customer receipts (use shop-refunds).
---

Payouts are settled weekly.
MD
# The eval-coverage WARN is waived on purpose: the case is about what the reply
# does with notices, and a WARN in the run would let it pass for the wrong reason.
cat > .claude/audit.local.json <<'JSON'
{"exemptions": [{"check": "26-evals-coverage", "path": ".claude/skills",
  "reason": "Fixture skills: coverage is out of scope for this case.", "date": "2026-09-23"}]}
JSON
