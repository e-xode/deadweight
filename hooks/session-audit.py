#!/usr/bin/env python3
"""SessionStart hook. Measures the consuming project and writes the result where a
status line can read it - outside the repository. Prints nothing.

WHY PYTHON AND NOT A SHELL SCRIPT. Until 0.14.1 this was bash calling `timeout` and
`md5sum`, two GNU coreutils that stock macOS does not have. The hook failed at every
session start with its stderr discarded, so the cache stayed empty and the status
line showed nothing, by design. Fixing `timeout` alone would have been worse: the
key then came out as `<project>-.json`, a file the line never reads, in a cache
that no longer looked empty. Python is already the plugin's one dependency, and the
digest here is computed by the same library call as in the two readers.

WHY IT IS SILENT. A SessionStart hook's stdout enters the model's context -
measured, not assumed: a probe plugin printing marker lines had them read back
verbatim by a fresh session. `claude plugin details` reports a hook as
"harness-only - no model context cost", which is true of the DECLARATION and
false of the OUTPUT. Whatever this prints is paid for in every session of every
project that installs the plugin. Numbers a human glances at travel through the
status line, which "runs locally and does not consume API tokens". Print here
only what the MODEL must act on.

WHY THE CACHE LIVES OUTSIDE THE REPOSITORY. A hook that runs at every session
start and writes inside the project leaves one more untracked file in every
repository, forever. A measurement is not configuration.

AND WHY IT WRITES NOTHING INSIDE THE PROJECT AT ALL. An earlier version appended
one line per run to `.claude/audit/history.jsonl`, dated to the DAY and never
deduplicated: twenty sessions produced twenty near-identical lines. That file is
gone since 0.3.0 - the git history of the committed floor is the same trajectory,
with a timestamp, an author and a commit message saying why the floor moved.

Two earlier attempts are worth remembering: writing it unconditionally (noise in
every repository), then gating on `.claude/audit/` existing - a directory
`--set-floor` creates, so every project that set a floor was opted in without
asking. A guard whose condition is produced by a routine operation is not a guard.
The fix was not a better condition; it was removing the write.

Matchers: `startup` and `resume` only. `clear` and `compact` reset the
conversation, not the configuration on disk.

Writes:   ${XDG_CACHE_HOME:-~/.cache}/claude-audit/<project>.json, and nothing else
Read by:  templates/statusline.py and `deadweight`
Opt out:  `claude plugin disable <this plugin> --scope project` - the
          granularity is the whole plugin, not this hook.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

# Under the harness's own 20 s on this hook, so the audit is stopped here - and the
# hook exits cleanly - rather than killed from outside with nothing written.
AUDIT_TIMEOUT = 18


def main() -> int:
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    audit = os.path.join(plugin_root, "skills", "config-auditor", "scripts", "audit.py")
    if not os.path.isfile(audit):
        return 0
    cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"),
                         "claude-audit")
    try:
        os.makedirs(cache, exist_ok=True)
    except OSError:
        return 0
    # Basename plus a short digest of the full path: two checked-out copies of the
    # same repository are two projects, and must not overwrite each other's line.
    # Same expression as the status line's cache_file() and `deadweight`'s cache_path().
    name = os.path.basename(root.rstrip("/"))
    key = f"{name}-{hashlib.md5(root.encode()).hexdigest()[:8]}"

    # audit.py exits 1 as soon as it finds an ERROR while still writing valid JSON:
    # its exit code says "this project has errors", not "the measurement failed".
    # Trusting it would silence the hook in exactly the projects that have something
    # to report. The only real failure is output that does not parse.
    try:
        out = subprocess.run([sys.executable, audit, "--root", root, "--json"],
                             capture_output=True, text=True, timeout=AUDIT_TIMEOUT).stdout
        data = json.loads(out)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return 0

    # The version that MEASURED, not the one installed now: after an update the two
    # differ until the next session, and the counts belong to the former. A sha names
    # the instrument for a machine; a version names it for the person reading.
    try:
        with open(os.path.join(plugin_root, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            version = json.load(fh).get("version")
    except Exception:
        version = None
    counts = data.get("counts") or {}
    # The findings travel with the counts, deliberately. A status line that says
    # "3 warnings" and gives no way to see which three is a number without a
    # referent: it can only be believed or ignored. The audit has just run and the
    # detail is already in hand - dropping it here would cost a second run later.
    record = {"project": name,
              "errors": int(counts.get("ERROR", 0)),
              "warnings": int(counts.get("WARN", 0)),
              "notices": int(counts.get("NOTICE", 0)),
              "audit_sha": data.get("audit_sha"),
              "plugin_version": version,
              "layout": data.get("layout"),
              "measured_at": datetime.datetime.now().isoformat(timespec="seconds"),
              # INFO travels too, last: a measurement nobody can reach is not collected,
              # it is discarded later. The counters leave it out, the detail does not.
              "findings": [f for f in (data.get("findings") or [])
                           if f.get("severity") in ("ERROR", "WARN", "NOTICE", "INFO")]}
    # Written beside the target, then renamed: the status line may read at any moment,
    # and a half-written file would read as "no measurement".
    try:
        fd, tmp = tempfile.mkstemp(dir=cache, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1)
        os.replace(tmp, os.path.join(cache, key + ".json"))
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
