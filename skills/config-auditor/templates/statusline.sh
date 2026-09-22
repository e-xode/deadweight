#!/usr/bin/env bash
# Status line segment: this project's last recorded audit. For the human only.
#
# The SessionStart hook measures and writes the result to a cache outside the
# repository; this reads it. The status line "runs locally and does not consume
# API tokens" (code.claude.com/docs/en/statusline), so the counts reach you for
# free while the model's context stays clean. That split is the whole point:
# hook stdout is read by the model and paid for in tokens, every session, every
# project; the status line is read by you and costs nothing.
#
# It does NOT run the audit, deliberately. The audit takes tenths of a second on
# a real repository; the status line re-runs on every assistant message, debounced
# at 300ms, and "if a new update triggers while your script is still running,
# Claude Code cancels the in-flight script". A status line that measured would be
# killed mid-measurement exactly when you are working hardest. It reads a file
# written elsewhere - a few milliseconds, never cancelled.
#
# It ALWAYS prints the age. The audit runs once, at session start; nothing the
# session changes afterwards is reflected. A count shown without its age reads as
# current, and a stale green light is worse than no light. Making staleness
# visible is cheaper than trying to abolish it.
#
# Install, in the consuming project:
#   cp "<plugin root>/skills/config-auditor/templates/statusline.sh" .claude/statusline.sh
#   chmod +x .claude/statusline.sh
#   .claude/settings.json:
#     { "statusLine": { "type": "command",
#                       "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/statusline.sh" } }
#
# Prints nothing where no audit has ever run. Absent is a valid state - a project
# that has not installed the plugin should not be nagged by a blank segment.
set -u

IN=$(cat)
DIR=$(printf '%s' "$IN" | jq -r '.workspace.project_dir // .cwd // empty' 2>/dev/null)
[ -n "$DIR" ] || exit 0

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/claude-audit"
KEY="$(basename "$DIR")-$(printf '%s' "$DIR" | cksum | cut -d' ' -f1)"
SRC="$CACHE/$KEY.json"
# The cache is the live value. The in-repository series is the fallback, for a
# project that keeps the record but whose cache has been cleared.
[ -s "$SRC" ] || SRC="$DIR/.claude/audit/history.jsonl"
[ -s "$SRC" ] || exit 0

# `jq -s .[-1]` reads both shapes without branching: the cache is one indented
# JSON object, the history is one compact object per line. `tail -n 1` worked on
# the second and returned "}" on the first.
read -r ERR WARN SHA <<<"$(jq -rs '.[-1] | [.errors, .warnings, .audit_sha] | @tsv' <"$SRC" 2>/dev/null)"
[ -n "${SHA:-}" ] && [ "$SHA" != "null" ] || exit 0

# Age from the file's own mtime: no schema change needed, and mtime answers
# exactly the question asked - when was this written, not what date did the
# writer believe it was.
MTIME=$(stat -c %Y "$SRC" 2>/dev/null || stat -f %m "$SRC" 2>/dev/null || echo 0)
AGE=$(( $(date +%s) - MTIME ))
if   [ "$AGE" -lt 90 ];     then WHEN="now"
elif [ "$AGE" -lt 5400 ];   then WHEN="$((AGE / 60))m ago"
elif [ "$AGE" -lt 172800 ]; then WHEN="$((AGE / 3600))h ago"
else                             WHEN="$((AGE / 86400))d ago"
fi

RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
if   [ "${ERR:-0}"  -gt 0 ]; then COL="$RED"
elif [ "${WARN:-0}" -gt 0 ]; then COL="$YEL"
else                              COL="$GRN"
fi
# Older than a day means the hook did not run this session: the plugin is
# disabled here, or the session was resumed without it. Say so rather than
# showing a number that looks live.
[ "$AGE" -ge 86400 ] && COL="$DIM"

# When there is something to see, name the command that shows it. A count with
# no way to reach its detail can only be believed or ignored, and the moment the
# question arises is the moment the answer has to be within reach.
HINT=""
[ "${ERR:-0}" -gt 0 ] || [ "${WARN:-0}" -gt 0 ] && HINT=" · deadweight"
printf '%saudit %sE %sW%s %s· %s · %s%s%s\n' \
       "$COL" "${ERR:-?}" "${WARN:-?}" "$OFF" "$DIM" "$SHA" "$WHEN" "$HINT" "$OFF"
