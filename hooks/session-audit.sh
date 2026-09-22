#!/usr/bin/env bash
# SessionStart hook. Measures the consuming project and writes the result where a
# status line can read it - outside the repository. Prints nothing.
#
# WHY IT IS SILENT. A SessionStart hook's stdout enters the model's context -
# measured, not assumed: a probe plugin printing marker lines had them read back
# verbatim by a fresh session. `claude plugin details` reports a hook as
# "harness-only - no model context cost", which is true of the DECLARATION and
# false of the OUTPUT. Whatever this prints is paid for in every session of every
# project that installs the plugin. Numbers a human glances at travel through the
# status line, which "runs locally and does not consume API tokens". Print here
# only what the MODEL must act on.
#
# WHY THE CACHE LIVES OUTSIDE THE REPOSITORY. A hook that runs at every session
# start and writes inside the project leaves one more untracked file in every
# repository, forever. A measurement is not configuration. The series that IS
# worth keeping - `audit.py --record` appending to .claude/audit/history.jsonl -
# is therefore opt-in: it is written only where `.claude/audit/` already exists,
# which is how a project says it wants to keep the record and commit it.
#
# Matchers: `startup` and `resume` only. `clear` and `compact` reset the
# conversation, not the configuration on disk.
#
# Writes:   ${XDG_CACHE_HOME:-~/.cache}/claude-audit/<project>.json   (always)
#           ${CLAUDE_PROJECT_DIR}/.claude/audit/history.jsonl         (if opted in)
# Read by:  templates/statusline.sh
# Opt out:  `claude plugin disable <this plugin> --scope project` - the
#           granularity is the whole plugin, not this hook.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
AUDIT="${CLAUDE_PLUGIN_ROOT:-}/skills/config-auditor/scripts/audit.py"
[ -f "$AUDIT" ] || exit 0

# Opt-in series, inside the project, only where the directory already exists.
[ -d "$ROOT/.claude/audit" ] && timeout 25 python3 "$AUDIT" --root "$ROOT" --record >/dev/null 2>&1

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/claude-audit"
mkdir -p "$CACHE" 2>/dev/null || exit 0
# Basename plus a short digest of the full path: two checked-out copies of the
# same repository are two projects, and must not overwrite each other's line.
KEY="$(basename "$ROOT")-$(printf '%s' "$ROOT" | md5sum | cut -c1-8)"

TMP="$(mktemp)" || exit 0
trap 'rm -f "$TMP"' EXIT
# audit.py exits 1 as soon as it finds an ERROR while still writing valid JSON:
# its exit code says "this project has errors", not "the measurement failed".
# Trusting it would silence the hook in exactly the projects that have something
# to report. The only real failure is empty output, covered on the next line.
timeout 25 python3 "$AUDIT" --root "$ROOT" --json >"$TMP" 2>/dev/null
[ -s "$TMP" ] || exit 0

python3 - "$TMP" "$CACHE/$KEY.json" "$(basename "$ROOT")" <<'PY' 2>/dev/null
import datetime, json, sys
src, dst, name = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.load(open(src, encoding="utf-8"))
except Exception:
    sys.exit(0)
counts = data.get("counts") or {}
# The findings travel with the counts, deliberately. A status line that says
# "3 warnings" and gives no way to see which three is a number without a
# referent: it can only be believed or ignored. The audit has just run and the
# detail is already in hand - dropping it here would cost a second run later.
json.dump({"project": name,
           "errors": int(counts.get("ERROR", 0)),
           "warnings": int(counts.get("WARN", 0)),
           "audit_sha": data.get("audit_sha"),
           "layout": data.get("layout"),
           "measured_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "findings": [f for f in (data.get("findings") or [])
                        if f.get("severity") in ("ERROR", "WARN")]},
          open(dst, "w", encoding="utf-8"), indent=1)
PY
exit 0
