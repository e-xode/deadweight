#!/usr/bin/env python3
"""Status line segment: what the audit last found here. For the human only.

Installed by `deadweight --setup-statusline`, which also wires the setting. You can
copy it to .claude/statusline.py yourself and point `statusLine` at it.

The SessionStart hook measures and caches the result OUTSIDE the repository; this
reads it and never measures. The status line "runs locally and does not consume API
tokens", so the counts reach you for free while the model's context stays clean.

TWO DESIGN RULES, both learned the hard way.

1. COLOUR ENCODES WHAT NEEDS AN ACTION, NOT THE COUNT. An earlier version went
   yellow whenever a warning existed, so a repository sitting exactly at its floor
   showed yellow every single day - for the state where there is nothing to do. A
   signal that is always on teaches the eye to skip it, and the day it matters it is
   no longer seen.

       dim     at the floor: the accepted state
       green   below the floor: the ratchet earned its keep
       yellow  errors, even under the floor: an error is always worth seeing
       red     above the floor: a regression, the only urgent case
       dim     measured by a superseded auditor, or by a stale measurement

2. FRESHNESS IS MEASURED, NOT GUESSED FROM AGE. The audit runs once, at session
   start; this reads a frozen number that looks live. Fix five warnings and it still
   shows the old count; add a broken rule and it still shows zero errors. An earlier
   version flagged AGE past a threshold, but age is a proxy: a three-day-old
   measurement in a repository nobody touched is still true, and a two-minute-old one
   in a repository you just edited is already false. The direct signal is the newest
   mtime of the configuration itself - about 6 ms over 500 files, against a 300 ms
   debounce.

Prints nothing where no audit has ever run: absent is a valid state.
"""
import hashlib
import json
import os
import sys
import time

RED, YEL, GRN, DIM, OFF = "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m"
# The audit's own bookkeeping lives under .claude/ but is not the audited
# configuration. Without this exclusion, setting a floor invalidates the very
# measurement that produced it.
SKIP_DIRS = {".git", "node_modules", "__pycache__", "audit"}


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def config_touched_since(root, when):
    newest = 0.0
    for base in (os.path.join(root, ".claude"), os.path.join(root, "CLAUDE.md")):
        if os.path.isfile(base):
            try:
                newest = max(newest, os.path.getmtime(base))
            except OSError:
                pass
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(dirpath, name)))
                except OSError:
                    pass
    return newest > when + 1          # a second of slack: the hook writes as it reads


def age(path):
    try:
        s = int(time.time() - os.path.getmtime(path))
    except OSError:
        return ""
    if s < 5400:
        return ""                     # minutes add nothing
    if s < 172800:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


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
    floor = read(os.path.join(root, ".claude", "audit", "floor.json"))
    same_instrument = bool(floor) and floor.get("audit_sha") == last.get("audit_sha")
    suffix = ""

    if floor and not same_instrument:
        col = DIM
        suffix = " (superseded auditor, reopen the session)"
    elif not floor:
        col = YEL if err else DIM
        suffix = " (no floor set)"
    else:
        fe, fw = int(floor.get("errors", 0)), int(floor.get("warnings", 0))
        if err > fe or warn > fw:
            col, suffix = RED, f" ▲ floor {fe}/{fw}"
        elif (err, warn) < (fe, fw):
            col, suffix = GRN, f" ▼ floor {fe}/{fw}"
        else:
            col = YEL if err else DIM

    stale = config_touched_since(root, os.path.getmtime(cache))
    if stale:
        col = DIM
        suffix = " (config changed since, run deadweight --fresh)"

    # The age only shows when it adds something: dating a measurement already
    # declared stale is a second signal for one fact, and two signals for one fact
    # teach the reader to read neither.
    when = "" if (stale or (floor and not same_instrument)) else age(cache)
    tail = f"{DIM} · {when}{OFF}" if when else ""

    # The plugin's name leads, and doubles as the command that shows the detail.
    print(f"{col}deadweight {err}E {warn}W{suffix}{OFF}{tail}", end="")


main()
