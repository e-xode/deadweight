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


def _under(path: str, real_root: str) -> bool:
    return path == real_root or path.startswith(real_root + os.sep)


def read_log(path: Path, root: Path) -> tuple[list[dict], int, list[str]]:
    """The log's events about files of this repository, the count of unreadable lines, the sessions.

    A session counts only if it ran here: it loaded a file of this repository, or its `cwd`
    lies in it. The documented hook names the log after the project folder's basename, so
    two clones named alike share one file, and a session in the other one proves nothing
    by absence here (audit externe 2026-10-08).
    """
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
        real = os.path.realpath(str(d.get("file_path", "")))
        here = real != real_root and _under(real, real_root)
        if d.get("session_id") and d["session_id"] not in sessions and (
                here or (d.get("cwd") and _under(os.path.realpath(str(d["cwd"])), real_root))):
            sessions.append(d["session_id"])
        # The user's own ~/.claude/CLAUDE.md is in every log; it is not this repository's.
        if not here:
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
    # `paths:` was not honoured, so it costs those sessions what CLAUDE.md costs. Judged on
    # its LATEST load: the log is append-only, and one session_start line from before
    # `paths:` was added must not condemn the rule forever (audit externe 2026-10-08).
    # A `compact` load counts as eager too: after compaction, "unscoped rules" are
    # "Re-injected from disk" while "Rules with `paths:` frontmatter" reload "on demand"
    # (context-window), so a compacted session's last line must not hide the rule
    # (audit externe 3, g5-00). An `include` load says nothing about `paths:`: skipped.
    eager = ("session_start", "compact")
    for rel in scoped:
        mine = [e for e in events if e["_rel"] == rel and e.get("load_reason") != "include"]
        if not mine:
            continue
        last = max(enumerate(mine), key=lambda ie: (str(ie[1].get("ts", "")), ie[0]))[1]
        if last.get("load_reason") not in eager:
            continue
        at_start = {e.get("session_id") for e in mine if e.get("load_reason") in eager}
        when = f", most recently {str(last.get('ts'))[:10]}" if last.get("ts") else ""
        # The docs re-inject only unscoped rules after compaction, but do not say which reason
        # a scoped rule gets when a file re-read after compaction matches its glob: a latest
        # `compact` line suggests, it does not prove (external audit 4, se-02).
        verdict = ("the harness did not read it as path-scoped there, and paid it whether or not "
                   "its paths were touched" if last.get("load_reason") == "session_start" else
                   "its latest load is a reload after compaction, where only unscoped rules are "
                   "documented to be re-injected (context-window) - likely, not proven, a sign it "
                   "was not read as path-scoped, since the docs do not say which load reason a "
                   "scoped rule gets when a file re-read after compaction matches its glob")
        report.add("57-runtime-rule-unscoped", "NOTICE",
                   f"'{rel}' declares `paths:`, yet the log shows it loaded at session start or "
                   f"after compaction in {len(at_start)} session(s){when}: {verdict}. Check its "
                   "frontmatter parses (a quoted list, `paths:` spelled so).",
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
    real_root = os.path.realpath(root)
    for rel, what in [(r, "rule") for r in scoped] + [(n, "nested CLAUDE.md") for n in nested]:
        if rel in loaded:
            continue
        head = f"'{rel}' ({what}) loaded in none of the {len(sessions)} recorded session(s){span}. "
        if what == "rule" and not _under(os.path.realpath(root / rel), real_root):
            # "Claude Code treats a symlink whose target is outside your working directory like
            # an external import [...] only the ones without a `paths` field load" (memory).
            advice = ("It is a symlink to a file outside the project and declares `paths:`, so the "
                      "harness never loads it, whatever its globs (memory). Copy it into the project, "
                      "or keep it in ~/.claude/rules/, where shared rules load without that approval - and "
                      "apply to every project on your machine (memory).")
        elif what == "rule":
            advice = ("It guards nothing anyone touched in that time: check that its paths match the "
                      "files you work on, or retire it.")
        else:
            advice = ("It loads when Claude uses Read, Write or Edit on a file in its folder (memory), "
                      "and no session did in that time: keep it if that folder is still worked on, or "
                      "retire it.")
        report.add("57-runtime-never-loaded", "NOTICE", head + advice, str(root / rel))
