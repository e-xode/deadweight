#!/usr/bin/env bash
# Two planted defects the harness ignores without a word; neither is named in the prompt.
set -e
git init -q .
mkdir -p .claude-plugin/skills/shop-refunds skills/shop-coupons agents
cat > .claude-plugin/plugin.json <<'J'
{ "name": "shop-kit", "version": "1.2.0", "description": "Refund and coupon helpers for the shop.", "agents": "agents/" }
J
printf -- '---\nname: shop-refunds\ndescription: Handle refund requests in the shop checkout. Do not use for invoicing.\n---\nRefunds.\n' > .claude-plugin/skills/shop-refunds/SKILL.md
printf -- '---\nname: shop-coupons\ndescription: Create and validate shop coupon codes. Do not use for refunds.\n---\nCoupons.\n' > skills/shop-coupons/SKILL.md
printf -- '---\nname: shop-checker\ndescription: Check a shop order for refund eligibility. Do not use for coupons.\n---\nCheck.\n' > agents/shop-checker.md
