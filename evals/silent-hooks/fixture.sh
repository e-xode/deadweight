#!/usr/bin/env bash
# A shop repository with two planted defects the harness ignores without a word.
# Neither is named in the prompt: the only way to find them is to read the files.
set -e
git init -q .
cat > CLAUDE.md <<'MD'
# shop-api

Run `make test` before any change.
MD
mkdir -p .claude/agents
cat > .claude/settings.json <<'J'
{ "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "echo shop-banner", "if": "Bash(git *)", "timeout": 5 }] }],
    "PreToolUse":   [{ "matcher": "mcp__shop-api", "hooks": [{ "type": "command", "command": "echo shop-mcp", "timeout": 5 }] }] } }
J
