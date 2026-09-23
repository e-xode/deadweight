#!/usr/bin/env bash
# Two planted defects the harness ignores without a word; neither is named in the prompt.
set -e
git init -q .
printf '# shop-admin\n\nAdmin panel of the shop.\n' > CLAUDE.md
cat > AGENTS.md <<'MD'
# Agent instructions

Always run `npm run lint` before committing. Never edit files under src/generated/.
MD
mkdir -p .claude/rules src/admin
echo "export const x = 1" > src/admin/page.ts
cat > .claude/rules/admin.md <<'MD'
---
globs: src/admin/**
---

Admin pages must check the `isStaff` flag before rendering.
MD
