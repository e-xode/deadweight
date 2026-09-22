#!/usr/bin/env python3
"""Status line segment: this project's last recorded audit. For the human only.

Installed by `deadweight --setup-statusline`; you can also copy it to
.claude/statusline.py yourself and point the `statusLine` setting at it.

The SessionStart hook measures and caches the result OUTSIDE the repository;
this reads it. The status line "runs locally and does not consume API tokens"
(code.claude.com/docs/en/statusline), so the counts reach you for free while the
model's context stays clean. That split is the whole point: hook stdout is read
by the model and paid for in tokens, every session, every project; the status
line is read by you and costs nothing.

It does NOT run the audit, deliberately. The audit takes tenths of a second on a
real repository; the status line re-runs on every assistant message, debounced at
300ms, and "if a new update triggers while your script is still running, Claude
Code cancels the in-flight script". A status line that measured would be killed
mid-measurement exactly when you are working hardest.

It ALWAYS prints the age of the number. The audit runs once, at session start;
nothing the session changes afterwards is reflected. A count shown without its
age reads as current, and a stale green light is worse than no light.

It compares against the floor ONLY at the same audit sha. A count taken with a
different auditor is not a better state, it is a different measurement.

Prints nothing where no audit has ever run: absent is a valid state.
"""
import hashlib
import json
import os
import sys
import time

RED, YEL, GRN, DIM, OFF = "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m"


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def age(path):
    try:
        s = int(time.time() - os.path.getmtime(path))
    except OSError:
        return ""
    if s < 90:
        return "now"
    if s < 5400:
        return f"{s // 60}m ago"
    if s < 172800:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ws = data.get("workspace") or {}
    root = ws.get("project_dir") or ws.get("current_dir") or data.get("cwd") or ""
    if not root:
        return
    name = os.path.basename(root.rstrip("/"))
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    key = f"{name}-{hashlib.md5(root.encode()).hexdigest()[:8]}"
    cache = os.path.join(base, "claude-audit", key + ".json")
    last = read(cache)
    if not last:
        return

    err, warn = int(last.get("errors", 0)), int(last.get("warnings", 0))
    col = RED if err else (YEL if warn else GRN)
    suffix = ""
    floor = read(os.path.join(root, ".claude", "audit", "floor.json"))
    if floor:
        if floor.get("audit_sha") != last.get("audit_sha"):
            suffix = f"{DIM} · floor from another instrument{OFF}"
        else:
            fe, fw = int(floor.get("errors", 0)), int(floor.get("warnings", 0))
            if err > fe or warn > fw:
                col, suffix = RED, f" ▲ {fe}/{fw}"
            elif (err, warn) < (fe, fw):
                col, suffix = GRN, f" ▼ {fe}/{fw}"
    hint = f"{DIM} · deadweight{OFF}" if (err or warn) else ""
    print(f"{col}audit {err}E {warn}W{suffix}{OFF}{DIM} · {age(cache)}{OFF}{hint}", end="")


main()
