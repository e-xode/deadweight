#!/usr/bin/env python3
"""Render docs/statusline.svg from the REAL status line, run on a fictional project.

Why generated and not a screenshot: a screenshot of a real terminal carries real
project names, and a PNG is the one file an anonymity check that reads text cannot
open. Why SVG: it stays text, so the same check reads it, and it is regenerated on
each release instead of quietly showing a format that no longer exists.

    python3 docs/render_statusline.py        # rewrites docs/statusline.svg
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "skills" / "config-auditor" / "templates" / "statusline.py"
COLOURS = {"31": "#e5534b", "32": "#57ab5a", "33": "#c69026", "2": "#768390"}

# (label, errors, warnings, floor (errors, warnings) or None, stale, newer version)
STATES = [
    ("at the floor - nothing to do", 0, 19, (0, 19), False, None),
    ("below the floor - the ratchet earned its keep", 0, 15, (0, 19), False, None),
    ("errors - always worth seeing", 2, 19, (2, 19), False, None),
    ("above the floor - a regression", 2, 25, (0, 19), False, None),
    ("not comparable - run `deadweight` to see why", 0, 19, (0, 19), True, None),
    ("a newer release is known", 0, 19, (0, 19), False, "0.9.0"),
]


def line_for(tmp, errors, warnings, floor, stale, newer):
    root = Path(tmp) / "shop-api"
    (root / ".claude" / "audit").mkdir(parents=True, exist_ok=True)
    cache_home, claude_home = Path(tmp) / "cache", Path(tmp) / "claude"
    sys.path.insert(0, str(TEMPLATE.parent))
    import statusline as sl
    os.environ["XDG_CACHE_HOME"] = str(cache_home)       # the key the template itself derives
    cache = Path(sl.cache_file(str(root)))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"errors": errors, "warnings": warnings, "audit_sha": "a1b2c3d4"}))
    (root / ".claude" / "audit" / "floor.json").write_text(json.dumps(
        {"errors": floor[0], "warnings": floor[1],
         "audit_sha": "e5f6a7b8" if stale else "a1b2c3d4"}))
    os.utime(root / ".claude", (1, 1))                     # config older than the measurement
    plugins = claude_home / "plugins"
    (plugins / "marketplaces" / "deadweight" / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({"plugins": {"deadweight@deadweight": [
        {"scope": "project", "projectPath": str(root), "version": "0.8.0"}]}}))
    (plugins / "marketplaces" / "deadweight" / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "deadweight", "version": newer or "0.8.0"}]}))
    env = dict(os.environ, XDG_CACHE_HOME=str(cache_home), CLAUDE_CONFIG_DIR=str(claude_home))
    out = subprocess.run([sys.executable, str(TEMPLATE)], input=json.dumps(
        {"workspace": {"project_dir": str(root)}}), capture_output=True, text=True, env=env).stdout
    return out


def spans(ansi):
    parts, colour = [], None
    for chunk in re.split(r"(\x1b\[[0-9;]*m)", ansi):
        m = re.fullmatch(r"\x1b\[([0-9;]*)m", chunk)
        if m:
            colour = COLOURS.get(m.group(1))
        elif chunk:
            parts.append((chunk, colour or "#adbac7"))
    return parts


def main():
    rows = []
    for label, e, w, floor, stale, newer in STATES:
        with tempfile.TemporaryDirectory() as tmp:
            rows.append((label, line_for(tmp, e, w, floor, stale, newer)))
    h, width = 34, 760
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h * len(rows) + 24}" '
           f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="15">',
           f'<rect width="100%" height="100%" rx="8" fill="#22272e"/>']
    for i, (label, ansi) in enumerate(rows):
        y = 12 + h * i + 22
        tspans = "".join(f'<tspan fill="{c}">{escape(t)}</tspan>' for t, c in spans(ansi))
        out.append(f'<text x="18" y="{y}" xml:space="preserve">{tspans}</text>')
        out.append(f'<text x="330" y="{y}" fill="#636e7b" font-size="13">{escape(label)}</text>')
    out.append("</svg>")
    (HERE / "statusline.svg").write_text("\n".join(out) + "\n", encoding="utf-8")
    for label, ansi in rows:
        print(f"{re.sub(r'\x1b\[[0-9;]*m', '', ansi):30}  {label}")


if __name__ == "__main__":
    main()
