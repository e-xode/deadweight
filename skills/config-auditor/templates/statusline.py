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

   Two glyphs, one meaning each:

       ↻        this number is not comparable: the configuration changed since it
                was measured, or the floor was set by another auditor
       ↑0.9.0   a newer release is known locally: `claude plugin update`

   `↻` carries no remedy, deliberately. An earlier version printed one - "reopen
   the session" - and it was wrong in one case of two: when the FLOOR is the older
   side, reopening measures again with the same auditor and the mismatch stays
   forever. This line compares two shas and cannot tell which is newer; the
   `deadweight` command can, and says which remedy applies.

3. A NUMBER IS SHOWN ONLY WHEN IT CHANGES WHAT YOU DO. Zero counts are dropped
   (`19W`, not `0E 19W`; `✓` when both are zero). The version is shown only as a
   DIFFERENCE - installed against available - because a version on its own names
   the state, and a difference names an action. Both are read from files Claude
   Code keeps on disk: no network, no subprocess, and nothing shown when the local
   catalogue was never refreshed.

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


PLUGIN = "deadweight"


def claude_home():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def version_key(v):
    try:
        return tuple(int(x) for x in str(v).split("-")[0].split("."))
    except ValueError:
        return ()


def versions(root):
    """(installed for this project, newest the local catalogue knows), or Nones.

    `installed_plugins.json` and `known_marketplaces.json` are Claude Code's own
    bookkeeping, not a documented interface: every read is guarded, and a format
    change shows nothing rather than something false.
    """
    plugins = os.path.join(claude_home(), "plugins")
    installed = read(os.path.join(plugins, "installed_plugins.json")) or {}
    pick, market = None, None
    for key, entries in (installed.get("plugins") or {}).items():
        if key.split("@")[0] != PLUGIN or not isinstance(entries, list):
            continue
        for e in entries:
            if e.get("projectPath") == root or (pick is None and e.get("scope") == "user"):
                pick, market = e, key.split("@", 1)[-1]
    if not pick:
        return None, None
    known = (read(os.path.join(plugins, "known_marketplaces.json")) or {}).get(market) or {}
    where = known.get("installLocation") or os.path.join(plugins, "marketplaces", market)
    catalogue = read(os.path.join(where, ".claude-plugin", "marketplace.json")) or {}
    available = next((p.get("version") for p in catalogue.get("plugins") or []
                      if p.get("name") == PLUGIN), None)
    return pick.get("version"), available


def update_available(root):
    installed, available = versions(root)
    if installed and available and version_key(available) > version_key(installed):
        return available
    return None


def cache_file(root):
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    key = f"{os.path.basename(root.rstrip('/'))}-{hashlib.md5(root.encode()).hexdigest()[:8]}"
    return os.path.join(base, "claude-audit", key + ".json")


def counts(err, warn, notice=0):
    # `n` is lower-case on purpose: a notice names a file, it does not move the floor.
    return " ".join(x for x in (f"{err}E" if err else "", f"{warn}W" if warn else "",
                                f"{notice}n" if notice else "") if x) or "✓"


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


def segment(root):
    """The audit segment for one project, or "" where no audit has run.

    Separate from main() so a status line of your own can import this file from the
    installed plugin and call it, instead of carrying a copy: a copy stays at the
    version it was taken from, and the plugin's next change never reaches it.
    """
    cache = cache_file(root)
    last = read(cache)
    if not last:
        return ""

    err, warn = int(last.get("errors", 0)), int(last.get("warnings", 0))
    floor = read(os.path.join(root, ".claude", "audit", "floor.json"))
    same_instrument = bool(floor) and floor.get("audit_sha") == last.get("audit_sha")
    suffix = ""

    if floor and not same_instrument:
        col = DIM
        suffix = " ↻"
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
        suffix = " ↻"

    # The age only shows when it adds something: dating a measurement already
    # declared stale is a second signal for one fact, and two signals for one fact
    # teach the reader to read neither.
    when = "" if (stale or (floor and not same_instrument)) else age(cache)
    tail = f"{DIM} · {when}{OFF}" if when else ""

    newer = update_available(root)
    up = f" {YEL}↑{newer}{OFF}" if newer else ""

    # The plugin's name leads: next to `ctx 42%` a bare `19W` does not say what it
    # counts, and the name doubles as the command that shows the detail.
    notice = int(last.get("notices", 0))
    return f"{col}{PLUGIN} {counts(err, warn, notice)}{suffix}{OFF}{up}{tail}"




def project_of(path):
    """The nearest folder holding .git or .claude/, or `path` itself.

    The cache is keyed by the project root the hook was given. A host that only
    says where it runs - Copilot CLI starts the command in its working directory -
    may be in a subfolder, and a subfolder's key finds nothing.

    The home folder is never a project: its .claude/ is the user's configuration,
    and without this stop every folder outside a project would resolve to it.
    """
    here = os.path.abspath(path)
    home = os.path.abspath(os.path.expanduser("~"))
    while here != home:
        if os.path.exists(os.path.join(here, ".git")) or os.path.isdir(os.path.join(here, ".claude")):
            return here
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    return os.path.abspath(path)


def main():
    # Windows writes a piped stdout in the ANSI code page (cp1252), which has no
    # `✓`, `↻` or `▲`: the first one raised UnicodeEncodeError and the line showed nothing. Measured on a
    # Windows runner, 2026-09-24. Every reader of this output - the host, an agent's
    # shell tool, a modern terminal - decodes UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    ws = data.get("workspace") or {}
    root = (ws.get("project_dir") or ws.get("current_dir") or data.get("cwd")
            or os.environ.get("CLAUDE_PROJECT_DIR") or project_of(os.getcwd()))
    print(segment(root), end="")


if __name__ == "__main__":
    main()
