#!/usr/bin/env python3
"""Status line launcher, written by `deadweight --setup-statusline`. Carries no display logic.

It runs the status line template of the deadweight plugin INSTALLED for this project.
Until 0.13.1 the setup copied the template itself into the project, and a copy stays at
the version it was taken from: 0.13.0 added notices to the line, and every copy made
before it went on without them until the setup was run again. This file only finds the
template, so a plugin update reaches the line at the next session.

Prints nothing where the plugin is not installed. The lookup reads
`installed_plugins.json`, Claude Code's own bookkeeping and not a documented interface:
a format change shows nothing rather than something false.

To add the audit to a status line of your own instead, load the same template and call
its `segment(project_dir)`, which returns the segment as a string.
"""
import json
import os
import runpy

PLUGIN = "deadweight"


def template():
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        with open(os.path.join(home, "plugins", "installed_plugins.json"), encoding="utf-8") as fh:
            installed = json.load(fh)
    except Exception:
        return None
    pick = None
    for key, entries in (installed.get("plugins") or {}).items():
        if key.split("@")[0] != PLUGIN or not isinstance(entries, list):
            continue
        for e in entries:
            if e.get("projectPath") == root or (pick is None and e.get("scope") == "user"):
                pick = e
    if not pick or not pick.get("installPath"):
        return None
    path = os.path.join(pick["installPath"], "skills", "config-auditor", "templates", "statusline.py")
    return path if os.path.isfile(path) else None


found = template()
if found:
    runpy.run_path(found, run_name="__main__")
