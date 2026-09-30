"""What loaded at runtime, from an `InstructionsLoaded` log, against what the files declare.

Everything else in this auditor reads files. A rule whose `paths:` match nothing anyone
opens, a nested CLAUDE.md in a folder nobody works in, a `paths:` the harness did not
honour: the files say nothing about these, the sessions do. `audit.py --runtime <log>`
reads a log written by an `InstructionsLoaded` hook that the maintainer places
(references/runtime-data.md) - this auditor never places one.

What a log can and cannot say, measured on 2.1.284 (2026-09-29): a file that loads leaves
one line per load; a file that never loads leaves NOTHING. "Never loaded" is read from
absence, so it is only said over enough sessions, with their count and dates. Every
finding is a NOTICE until its precision is measured on real logs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..context import AuditContext
from ..limits import RUNTIME_MIN_SESSIONS
from ..parsing.frontmatter import parse_frontmatter
from ..repo import readable_files, tracked_paths
from ..report import Report

PRUNED = ("node_modules/", "vendor/", ".git/")


def read_log(path: Path, root: Path) -> tuple[list[dict], int, list[str]]:
    """The log's events about files of this repository, the count of unreadable lines, the sessions."""
    real_root = os.path.realpath(root)
    events, bad, sessions = [], 0, []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if not isinstance(d, dict) or d.get("hook_event_name") != "InstructionsLoaded":
            bad += 1
            continue
        if d.get("session_id") and d["session_id"] not in sessions:
            sessions.append(d["session_id"])
        real = os.path.realpath(str(d.get("file_path", "")))
        # The user's own ~/.claude/CLAUDE.md is in every log; it is not this repository's.
        if real == real_root or not real.startswith(real_root + os.sep):
            continue
        d["_rel"] = Path(os.path.relpath(real, real_root)).as_posix()
        events.append(d)
    return events, bad, sessions


def check_runtime_loads(ctx: AuditContext, report: Report) -> None:
    if ctx.runtime is None:
        return
    root = ctx.root
    try:
        events, bad, sessions = read_log(ctx.runtime, root)
    except OSError as exc:
        report.add("57-runtime-log", "NOTICE",
                   f"--runtime {ctx.runtime}: cannot read it ({exc.strerror}). Nothing about "
                   "runtime loads is reported.", str(ctx.runtime))
        return
    dates = sorted(str(e.get("ts", ""))[:10] for e in events if e.get("ts"))
    span = f", {dates[0]} to {dates[-1]}" if dates else ""
    loaded: dict[str, set[str]] = {}
    for e in events:
        loaded.setdefault(e["_rel"], set()).add(str(e.get("load_reason", "")))
    report.add("57-runtime-log", "INFO",
               f"Runtime log: {len(sessions)} session(s){span}, {len(loaded)} file(s) of this "
               f"repository loaded" + (f", {bad} unreadable line(s) skipped" if bad else "") + ".",
               str(ctx.runtime))

    rules_dir = root / ctx.claude_dir / "rules"
    scoped = []
    for rule in readable_files(rules_dir.rglob("*.md")) if rules_dir.is_dir() else []:
        fm, _ = parse_frontmatter(rule.read_text(encoding="utf-8", errors="replace"))
        if fm and str(fm.get("paths", "")).strip():
            scoped.append(rule.relative_to(root).as_posix())
    # A rule the audit reads as path-scoped that the harness loaded at session start: its
    # `paths:` was not honoured, so it costs every session what CLAUDE.md costs.
    for rel in scoped:
        if "session_start" in loaded.get(rel, set()):
            report.add("57-runtime-rule-unscoped", "NOTICE",
                       f"'{rel}' declares `paths:`, yet the log shows it loaded at session start: the "
                       "harness did not read it as path-scoped, and it is paid in every session. "
                       "Check its frontmatter parses (a quoted list, `paths:` spelled so).",
                       str(root / rel))
    nested = [t for t in tracked_paths(root)
              if t.endswith("/CLAUDE.md") and not t.startswith(".claude/")
              and not any(p in t for p in PRUNED)]
    if len(sessions) < RUNTIME_MIN_SESSIONS:
        if scoped or nested:
            report.add("57-runtime-log", "INFO",
                       f"{len(sessions)} session(s) recorded: fewer than {RUNTIME_MIN_SESSIONS}, so "
                       "nothing is called never loaded - a file that does not load leaves no line, "
                       "and a few sessions prove nothing by absence.", str(ctx.runtime))
        return
    for rel, what in [(r, "rule") for r in scoped] + [(n, "nested CLAUDE.md") for n in nested]:
        if rel not in loaded:
            report.add("57-runtime-never-loaded", "NOTICE",
                       f"'{rel}' ({what}) loaded in none of the {len(sessions)} recorded session(s)"
                       f"{span}. It guards nothing anyone touched in that time: check that its "
                       "paths match the files you work on, or retire it.", str(root / rel))
