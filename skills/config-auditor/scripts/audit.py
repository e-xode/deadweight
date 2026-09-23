#!/usr/bin/env python3
"""Audit the Claude configuration of a project or of a plugin.

SHIPPED AS PART OF A PLUGIN - DO NOT EDIT IN PLACE.
This file is installed, not copied: an edit made in one consuming project is lost
on the next plugin update, and until then makes that project silently diverge from
every other one. Fix it upstream in the plugin repository and release a version.

Anything genuinely local - exemptions, and the reason each one was granted - lives
in the CONSUMING PROJECT at `.claude/audit.local.json`, never beside this file:
installed as a plugin, this script sits in a version-stamped cache directory that
is replaced on every update, so anything written next to it is lost.

Two containers are audited, and they are not the same object:

    project : CLAUDE.md + settings + agents + rules + skills at .claude/skills/
    plugin  : a manifest + skills at skills/ (and optionally agents/)

The SKILL-level checks apply to any SKILL.md wherever it lives; the project-level
checks (listed in PROJECT_ONLY) are skipped when the container is a plugin, and
check 30 replaces the budget check with its inverse - what the plugin costs each
consuming project. The layout is detected from `.claude-plugin/plugin.json`, or
forced with --layout.

Runs the mechanical checks listed in CHECKS, reporting OK/INFO/WARN/ERROR. Most
checks emit a finding only on failure; a clean run prints the executed-count
summary so success stays legible. Exits 1 on any error.

Beyond file hygiene the script verifies the mechanisms behind the configuration:
that rule `paths:` globs expand to real files, that agent frontmatter names tools
and preloadable skills that exist, that no reference file is reachable only from a
sibling reference, that every eval suite matches the documented schema, that twin
skills carry both halves of their division-of-responsibilities table, and that the
project's own overlay carries a reason and a date for every exemption it grants.

Usage:
    python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py
    python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --json
    python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --root /path/to/repo

No external dependencies (Python stdlib only). No --fix flag: corrections are
always proposed to the user, never applied automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date as _date
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# THRESHOLDS - identical in every repository. Three tiers, and the tier decides
# whether a number is negotiable.
#
# 1. MECHANISM - imposed by the runtime. Not a choice; changing it only makes the
#    audit lie about what the model actually does.
# TWO caps, both mechanisms, from TWO different documents. Restored 2026-09-20 after being
# wrongly collapsed into one: this project's own
# references/skill-runtime-mechanisms.md had it right all along.
DESCRIPTION_MAX_CHARS = 1024          # Agent Skills SPEC cap on `description` ALONE.
                                      # "description: Must be non-empty / Maximum 1,024 characters"
                                      # platform.claude.com/docs/en/agents-and-tools/agent-skills/
                                      #   best-practices  (re-verified 2026-09-20)
DESCRIPTION_LISTING_MAX_CHARS = 1536  # LISTING cap on `description` + `when_to_use` COMBINED.
                                      # code.claude.com/docs/en/skills.md
                                      # Past it the tail is dropped without a warning.
SKILL_MD_COMPACTION_WARN_BYTES = 20000  # ~5,000 tokens: content past this point is
                                        # dropped when a skill is re-attached after
                                        # auto-compaction.
#
# 2. HOUSE DOCTRINE - deliberate discipline, uniform across the fleet because no
#    mechanism makes one repository deserve more room than another.
DESCRIPTION_MIN_CHARS = 80
AGENT_DESCRIPTION_MAX_CHARS = 900
CLAUDE_MD_MAX_BYTES = 12 * 1024
CLAUDE_MD_MAX_LINES = 200
SKILL_MD_ERROR_BYTES = 50 * 1024
REFERENCE_WARN_LINES = 300
REFERENCE_TOC_LINES = 100
REFERENCE_TOC_SCAN_LINES = 30
ALWAYS_LOADED_WARN_CHARS = 43000
ALWAYS_LOADED_ERROR_CHARS = 47000
SKILL_DESC_AGGREGATE_WARN_CHARS = 40000
# A plugin pays nothing itself: every consuming project pays its descriptions,
# once each. 2 000 chars is ~5 % of ALWAYS_LOADED_WARN_CHARS - the point past
# which installing the plugin is a budget decision, not a free addition.
PLUGIN_COST_WARN_CHARS = 2000
# Agent Skills spec: `name` is lowercase letters, digits and hyphens, 64 chars max,
# and must not contain "anthropic" or "claude". The last rule bites only when a
# skill is packaged or published - locally a non-conformant name keeps working,
# which is exactly why it survives unnoticed until the day it blocks distribution.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX_CHARS = 64
RESERVED_NAME_TOKENS = ("anthropic", "claude")
# Triggering is a COMPETITION between the descriptions listed on the same turn.
# Two close descriptions do not merely cost tokens, they steal each other's
# activations. 0.35 was calibrated on a 59-skill project: it flagged 13 pairs, of
# which 2 were real confusions - low enough to catch, high enough not to nag.
OVERLAP_THRESHOLD = 0.35
# A skill with no eval suite cannot be shown wrong; it can only rot quietly. The
# floor is a house figure, not a platform one.
EVALS_COVERAGE_WARN = 0.50
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# CHECK IDS ARE A PUBLIC API. A consuming project names them in its
# `.claude/audit.local.json`, so renaming one silently turns that project's
# exemption inert - and the audit then blames the project for an id this script
# changed. Ids are therefore never renamed: an id that must change is added here,
# old -> new, and keeps working. Never remove an entry.
CHECK_ID_ALIASES: dict[str, str] = {}
EVALS_MIN_COUNT = 3
#
# 3. DERIVED - computed from this repository's own settings, so the NUMBER differs
#    between repositories while the RULE stays the same. `skillListingBudgetFraction`
#    is a per-repository dial (measured 2026-09-20 across one fleet of 19: 0.025 in
#    eight repositories, 0.05 in one, 0.06 in another). Hard-coding one ceiling across
#    repositories that set different fractions would uniformise the wrong thing.
# --- Which thresholds a project may move, and which it may not -------------
# C57 names three families of threshold, and treating them alike would be the
# mistake. MECHANISM is imposed by the harness: a project that raises the 1,024
# spec cap has not adjusted a threshold, it has decided to ignore a limit its
# upload will hit anyway. DOCTRINE is uniform by choice, so a repository with a
# good reason may hold its own number - an ops repository whose CLAUDE.md is all
# hard rules is the case that forced this. DERIVED already comes from the
# project's own settings and needs no override.
#
# Refusing loudly is the point. A plugin that silently obeyed any override would
# turn its own doctrine into a suggestion, and the audit into a mirror.
OVERRIDABLE_THRESHOLDS = frozenset({
    "CLAUDE_MD_MAX_BYTES", "CLAUDE_MD_MAX_LINES", "SKILL_MD_ERROR_BYTES",
    "REFERENCE_WARN_LINES", "REFERENCE_TOC_LINES", "DESCRIPTION_MIN_CHARS",
    "AGENT_DESCRIPTION_MAX_CHARS", "ALWAYS_LOADED_WARN_CHARS",
    "ALWAYS_LOADED_ERROR_CHARS", "SKILL_DESC_AGGREGATE_WARN_CHARS",
    "PLUGIN_COST_WARN_CHARS", "OVERLAP_THRESHOLD", "EVALS_COVERAGE_WARN",
    "EVALS_MIN_COUNT",
})
MECHANISM_THRESHOLDS = {
    "DESCRIPTION_MAX_CHARS": "the Agent Skills spec cap on `description` alone; over it the upload fails",
    "DESCRIPTION_LISTING_MAX_CHARS": "where the harness truncates the listing; moving the number moves nothing",
    "SKILL_MD_COMPACTION_WARN_BYTES": "the slice re-attached after compaction; it is the harness's, not yours",
    "SKILL_NAME_MAX_CHARS": "a spec limit on the name field",
    "CONTEXT_WINDOW_TOKENS": "the window the model actually has",
    "CHARS_PER_TOKEN": "kept optimistic on purpose so every derived figure is a floor",
}

LISTING_FRACTION_DEFAULT = 0.01       # harness default: 1% of the context window
CONTEXT_WINDOW_TOKENS = 1_000_000     # the window this fleet actually runs on
# Measured 2026-09-22 with `claude plugin details`, the harness's own projection.
# Four throwaway plugins, one skill each, only the description length varying:
# tokens = 18.2 + chars / 3.38, r2 = 0.99992 - a slope AND a fixed cost of about 18
# tokens per listed skill. Then two controls at IDENTICAL length (627 chars): ordinary
# prose 174 tokens (4.02 chars/token), this plugin's own description 238 (2.85). A
# factor of 1.4 at the same length: the ratio is a property of the TEXT, not of the
# language - a description tokenises badly precisely because it is written tight.
#
# So 4 is not replaced by another number; there is no single right one. 4 is the most
# optimistic ratio observed, so any token count computed from it is a FLOOR, stated as
# "at least". Characters stay the measured quantity: the budget doctrine is written in
# characters, not in tokens.
CHARS_PER_TOKEN = 4                   # optimistic on purpose: token figures are floors
# ---------------------------------------------------------------------------

CHECKS = (
    "claude-md size + code-comments",
    "skill SKILL.md exists + frontmatter",
    "skill name matches folder",
    "skill description length + anti-trigger",
    "skill SKILL.md size",
    "skill duplicate name",
    "skill broken relative links",
    "agent frontmatter (name/description/tools)",
    "agent description budget + anti-trigger",
    "agent <-> CLAUDE.md cross-refs",
    "english-only heuristic (skills + src content)",
    "no code comments in SKILL.md",
    "no global scripts pool",
    "rules structure (size/paths/comments/english)",
    "skill-index <-> folder coherence",
    "reference file size + table of contents",
    "always-loaded context budget",
    "see-skill cross-reference targets",
    "frontmatter scalar quoting (strict-YAML safety)",
    "relative links resolve across the whole .claude tree",
    "SKILL.md compaction re-attach slice",
    "rule paths globs expand to real files",
    "agent frontmatter validity (tools / skills preload / model)",
    "settings.json scope semantics",
    "orphan references (unreachable from SKILL.md)",
    "evals schema + coverage",
    "twin-skill division-of-responsibilities tables (heading, twin row, shared row text)",
    "skill anchors resolve to real files (falsifiability)",
    "listing budget derived from skillListingBudgetFraction",
    "plugin cost imposed on each consuming project",
    "project overlay: exemptions and doctrine-threshold overrides, each with a reason and a date",
    "skill name shape + reserved words (spec)",
    "confusable descriptions (TF-IDF cosine between listed skills)",
    "ratchet: counts against the recorded floor, same instrument only",
    "hooks: known events, resolvable commands, timeouts, and what their stdout costs",
    "plugin routing to skills it does not ship",
    "flags the documentation shows must exist in the script",
    "38-unreadable",
    "39-eval-quality",
    "40-skill-not-loaded",
)
# i18n-data: start — French on purpose, this is the check's own dictionary
FRENCH_HEURISTIC_WORDS = {
    "avec", "pour", "dans", "cette", "celui", "celle", "ceux", "celles",
    "vous", "nous", "etre", "tres", "donc", "ainsi",
    "depuis", "toujours", "jamais", "ensuite", "alors", "parce", "lorsque",
    "fichier", "exemple", "doit", "peut", "faut", "selon",
}
# i18n-data: end
FRENCH_HEURISTIC_THRESHOLD = 3
ENGLISH_ONLY_EXEMPT: set[str] = set()   # filled from audit.local.json, see below
# A file that IS the French version of localised content is not drift: a
# multilingual project has to carry each language properly, French included, and a
# check that flags `pricing-fr.md` for being in French is wrong in a way that costs
# it its credibility. What matters is that the language is DECLARED in the name.
# Measured 2026-09-22 on one repository: 11 of 19 findings under src/ were
# locale-suffixed files, flagged only because the convention there is `-fr.md`
# while this exempted `.fr.md`.
ENGLISH_ONLY_SUFFIX_EXEMPT = ".fr.md"
LOCALE_MARKED_RE = re.compile(r"(?:[-_.](?:fr|de|es|it|pt|nl|ja|zh|ru|ar)\.[a-z]+$)"
                              r"|(?:/(?:fr|de|es|it|pt|nl|ja|zh|ru|ar)/)")

KNOWN_TOOLS = {
    "Read", "Edit", "Write", "Glob", "Grep", "Bash", "PowerShell", "Skill", "Agent",
    "WebFetch", "WebSearch", "NotebookEdit", "TodoWrite", "ToolSearch", "Monitor",
    "SendMessage", "TaskStop", "TaskOutput", "EnterWorktree", "ExitWorktree",
    "AskUserQuestion",
}
KNOWN_MODEL_TIERS = {"haiku", "sonnet", "opus", "inherit"}

# Hook vocabulary. Source: code.claude.com/docs/en/hooks, read 2026-09-22.
# An event name that is not in this set never fires and never complains: the
# harness has nothing to match it against, so a typo is silent forever. That is
# the whole reason this is a hard-coded list and not a shape check.
KNOWN_HOOK_EVENTS = frozenset({
    "SessionStart", "Setup", "UserPromptSubmit", "UserPromptExpansion",
    "PreToolUse", "PermissionRequest", "PermissionDenied", "PostToolUse",
    "PostToolUseFailure", "PostToolBatch", "Notification", "MessageDisplay",
    "SubagentStart", "SubagentStop", "TaskCreated", "TaskCompleted",
    "Stop", "StopFailure", "TeammateIdle", "InstructionsLoaded",
    "ConfigChange", "CwdChanged", "DirectoryAdded", "FileChanged",
    "WorktreeCreate", "WorktreeRemove", "PreCompact", "PostCompact",
    "PreModelSwitch", "PostModelSwitch", "Elicitation", "ElicitationResult",
    "SessionEnd",
})
# "For most events, Claude Code writes stdout to the debug log and doesn't show
# it in the transcript. The exceptions are UserPromptSubmit, UserPromptExpansion,
# SessionStart, and PostModelSwitch, where Claude Code adds plain-text stdout as
# context that Claude can see and act on." Everything a hook on one of these four
# prints is paid for in tokens, in every session, in every project that has it -
# while `claude plugin details` reports a hook as "harness-only, no model context
# cost", which is true of the declaration and false of the output.
CONTEXT_INJECTING_HOOK_EVENTS = frozenset({
    "UserPromptSubmit", "UserPromptExpansion", "SessionStart", "PostModelSwitch",
})
# These events always fire. A `matcher` on them reads as a filter to every human
# who opens the file, and is not one.
MATCHERLESS_HOOK_EVENTS = frozenset({
    "CwdChanged", "UserPromptSubmit", "PostToolBatch", "Stop", "TeammateIdle",
    "TaskCreated", "TaskCompleted", "WorktreeCreate", "WorktreeRemove",
    "MessageDisplay",
})
HOOK_DEFAULT_TIMEOUT = 600          # seconds, for `command` hooks
HOOK_PLUGIN_ROOT_VARS = ("${CLAUDE_PLUGIN_ROOT}", "$CLAUDE_PLUGIN_ROOT")
HOOK_PROJECT_DIR_VARS = ("${CLAUDE_PROJECT_DIR}", "$CLAUDE_PROJECT_DIR")
AGENT_VALIDATED_KEYS = {"name", "description", "tools", "model", "skills"}
PROJECT_SCOPE_IGNORED_MODES = {"bypassPermissions", "auto"}

WALK_PRUNE_DIRS = {
    ".git", "node_modules", "dist", "build", "coverage", ".venv", "venv",
    "__pycache__", ".cache", ".output", ".next", ".nuxt", "out",
}

EVALS_REQUIRED_KEYS = ("id", "prompt", "expected_output", "expectations")
EVALS_ANTI_NAME_TOKENS = ("anti-trigger", "not-trigger", "should-not", "defer", "negative", "near-miss")
EVALS_ANTI_EXPECTATION_TOKENS = ("defer", "does not trigger", "should not")

DIVISION_HEADING_RE = re.compile(r"^#{1,6}\s+.*division of responsibilities", re.IGNORECASE | re.MULTILINE)
POINTER_RE = re.compile(r"→\s*([a-z0-9][a-z0-9-]*)")

SEVERITY_ORDER = {"OK": 0, "INFO": 1, "WARN": 2, "ERROR": 3}


VALID_CHECK_IDS: set[str] = set()   # filled in main() from the findings vocabulary


def load_local_config(root: Path) -> dict:
    """The project's overlay. The ONLY thing that may differ between projects.

    `<root>/.claude/audit.local.json`. It lives in the PROJECT, never beside this
    script: shipped as a plugin, this file sits in a version-stamped cache directory
    that is replaced on every update, so anything written next to it is lost.

    Schema:

        {"exemptions": [
            {"check": "11-english-only",
             "path":  "translate/references/glossary.md",
             "reason": "FR/EN glossary, bilingual by nature",
             "date":  "2026-09-22"}]}

    `reason` and `date` are not decoration and not optional. A bare list of exempt
    paths is amnesia: six months on nobody knows why an entry is there, so nobody
    dares remove it, so the list only ever grows - a ratchet pointing the wrong way.
    Carrying the reason puts the decision at the exact place the model looks when
    the check fires, which is why this project needs no separate decision document
    for the ordinary case. Check 31 enforces the shape.

    Absent, unreadable or malformed: no exemption, and the audit says so.
    """
    path = root / STATE_DIR / "audit.local.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {"__error__": str(path)}


def apply_thresholds(local: dict, report: Report) -> None:
    """Let a project hold its own number for a DOCTRINE threshold, and say so.

    Schema, in `<project>/.claude/audit.local.json`:

        {"thresholds": {"CLAUDE_MD_MAX_BYTES":
            {"value": 13312, "reason": "ops repository, all hard rules", "date": "2026-09-22"}}}

    `reason` and `date` are required for exactly the same cause as on an
    exemption: a bare number is amnesia. Six months on nobody knows why the
    ceiling is 13 KB, so nobody dares lower it, and the dial only ever turns one
    way.

    Every applied override is reported as INFO on every run. An override nobody
    sees is a doctrine quietly rewritten; one that prints itself is a decision
    anyone can re-open.
    """
    # An unknown key was ignored in silence, so a project writing `thresholds`
    # against an older release got no signal and wondered why nothing moved. A
    # configuration file that accepts everything and applies part of it is worse
    # than one that refuses.
    connues = {"exemptions", "thresholds", "_comment"}
    for k in sorted(set(local) - connues):
        report.add("31-overlay-unknown", "WARN",
                   f"`{k}` is not a key this audit reads, so it does nothing. Known keys: "
                   f"{', '.join(sorted(connues - {'_comment'}))}.", "")
    over = local.get("thresholds")
    if not isinstance(over, dict):
        return
    for nom in sorted(over):
        spec = over[nom]
        if nom in MECHANISM_THRESHOLDS:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{nom}` cannot be overridden: {MECHANISM_THRESHOLDS[nom]}. "
                       "Moving this number changes what the audit says, not what the harness "
                       "does.", "")
            continue
        if nom not in OVERRIDABLE_THRESHOLDS:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{nom}` is not a threshold this audit recognises. Known overridable "
                       f"thresholds: {', '.join(sorted(OVERRIDABLE_THRESHOLDS))}.", "")
            continue
        if not isinstance(spec, dict) or "value" not in spec:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{nom}` must be an object with `value`, `reason` and `date`.", "")
            continue
        manque = [k for k in ("reason", "date") if not str(spec.get(k, "")).strip()]
        if manque:
            report.add("31-overlay-threshold", "ERROR",
                       f"`{nom}` overrides a doctrine threshold without {' and '.join(manque)}. "
                       "A number with no reason is a number nobody dares change back.", "")
            continue
        if not ISO_DATE_RE.match(str(spec["date"])):
            report.add("31-overlay-threshold", "ERROR",
                       f"`{nom}`: `date` must be YYYY-MM-DD.", "")
            continue
        ancien = globals().get(nom)
        try:
            valeur = type(ancien)(spec["value"])
        except (TypeError, ValueError):
            report.add("31-overlay-threshold", "ERROR",
                       f"`{nom}`: `value` is not a {type(ancien).__name__}.", "")
            continue
        globals()[nom] = valeur
        report.add("31-overlay-threshold", "INFO",
                   f"`{nom}` {ancien} -> {valeur}, on this project's authority "
                   f"({spec['date']}): {spec['reason']}", "")


def exemption_paths(local: dict, check: str) -> set[str]:
    """Paths exempt from one check, from the structured `exemptions` list."""
    out: set[str] = set()
    for e in local.get("exemptions") or ():
        chk = e.get("check") if isinstance(e, dict) else None
        chk = CHECK_ID_ALIASES.get(chk, chk)
        if isinstance(e, dict) and chk == check and isinstance(e.get("path"), str):
            out.add(e["path"])
    return out


ENGLISH_ONLY_EXEMPT: set[str] = set()   # filled from audit.local.json in main()


# An exemption may never silence the checks that audit the exemptions, nor the
# ratchet. A release valve able to disconnect its own pressure gauge is not a
# valve: it is a way of not knowing.
UNEXEMPTABLE = frozenset({
    "31-overlay", "31-overlay-parse", "31-overlay-schema", "31-overlay-stale",
    "31-overlay-alias", "31-overlay-unknown-check", "31-overlay-threshold",
    "34-audit-sha", "00-layout",
})
DOWNGRADE_TO = ("WARN", "INFO")


def apply_overlay(report: "Report", local: dict, root: Path) -> None:
    """Drop or downgrade findings the project has formally excused.

    Until 2026-09-22 the overlay reached exactly one check, `11-english-only`:
    an exemption written for any other id was schema-checked, counted in the
    summary, and applied to nothing. Nobody had been bitten because nobody had
    written one - the only exemption anyone wrote was the one that worked.

    `severity` is the addition that makes the file worth writing: without it an
    exemption erases the finding, and the project loses the count it excused.
    With it, the finding stays visible at a severity that does not fail CI, and
    `--check-floor` still watches it grow.
    """
    entries = [e for e in (local.get("exemptions") or ()) if isinstance(e, dict)]
    if not entries:
        return
    resolus: list[tuple[str, Path, str | None]] = []
    for e in entries:
        chk = CHECK_ID_ALIASES.get(e.get("check"), e.get("check"))
        pth = e.get("path")
        if not isinstance(chk, str) or not isinstance(pth, str) or not pth:
            continue
        if chk in UNEXEMPTABLE:
            continue
        sev = e.get("severity")
        sev = sev if isinstance(sev, str) and sev.upper() in DOWNGRADE_TO else None
        for base in (root / SKILLS_DIR / pth, root / pth):
            if base.exists():
                resolus.append((chk, base.resolve(), sev and sev.upper()))
                break
    if not resolus:
        return
    gardees: list[Finding] = []
    for f in report.findings:
        cible = None
        if f.location:
            try:
                cible = Path(f.location).resolve()
            except OSError:
                cible = None
        couvert = next(
            (sev for chk, base, sev in resolus
             if chk == f.check and cible is not None
             and (cible == base or base in cible.parents)),
            "__rien__")
        if couvert == "__rien__":
            gardees.append(f)
        elif couvert is not None:
            gardees.append(Finding(f.check, couvert, f.message + " [excused by overlay]",
                                   f.location))
    report.findings = gardees


# --- Layout -----------------------------------------------------------------
# Two containers hold skills, and they are not the same object.
#
#   project : CLAUDE.md + settings + agents + rules + skills at .claude/skills/
#   plugin  : a manifest + skills at skills/ (and optionally agents/)
#
# The SKILL-level checks - description length, compaction slice, reference TOCs,
# orphan references, anti-triggers, evals, broken links - apply to any SKILL.md
# wherever it lives. The PROJECT-level checks do not apply to a plugin at all.
# Splitting them is what lets this script audit a plugin, including its own.
CLAUDE_DIR = ".claude"
# Where the AUDITED configuration lives changes with the container (CLAUDE_DIR).
# Where the audit's OWN bookkeeping lives does not: the overlay, the floor and the
# run history are repository state, and `.claude/` is their home in a project and
# in a plugin repository alike. Conflating the two put `audit/floor.json` at the
# root of a plugin on 2026-09-22.
STATE_DIR = ".claude"
SKILLS_DIR = ".claude/skills"
AGENTS_DIR = ".claude/agents"
LAYOUT = "project"
# Checks whose subject exists only in a project. Named by function, because the
# dispatch in main() reads this tuple: a project-only check added later and not
# listed here runs against a plugin and reports a missing file that cannot exist.
PROJECT_ONLY = (
    "check_claude_md",
    "check_cross_refs",
    "check_no_global_scripts",
    "check_rules",
    "check_rule_globs",
    "check_skill_index",
    "check_settings_scope",
    "check_always_loaded_budget",
    "check_listing_budget_derived",
)
PLUGIN_ONLY = ("check_plugin_cost",)
# The only things worth saying about a marketplace repository: what it is, and
# whether its own catalogue is coherent. Everything else has no subject here.
MARKETPLACE_CHECKS = ("check_skills",)
# A library is skills and nothing else: judge their content, and say where they
# would load. A repository with no Claude configuration gets the second only.
LIBRARY_CHECKS = ("check_skills", "check_skill_names", "check_description_overlap",
                  "check_unloadable_skills")
NONE_CHECKS = ("check_unloadable_skills",)


def claude_signs(root: Path) -> list[str]:
    """What in this repository says it is meant for Claude Code."""
    return [n for n in ("CLAUDE.md", ".claude", ".claude-plugin") if (root / n).exists()]


def root_level_skills(root: Path) -> list[Path]:
    """Directories at the root that hold a SKILL.md directly.

    Claude Code finds skills by LOCATION, never by content: `~/.claude/skills/`,
    `.claude/skills/`, and `skills/` at a plugin root. Measured 2026-09-23 from the
    session's `init` event: a `<name>/SKILL.md` at the repository root is loaded
    neither when the repository is opened as a project nor when it is passed as
    `--plugin-dir`, where `skills/<name>/SKILL.md` beside it is.
    """
    skip = {".claude", ".claude-plugin", ".git", "skills"}
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name not in skip and (d / "SKILL.md").is_file())


def check_unloadable_skills(root: Path, report: Report) -> None:
    """A SKILL.md at the repository root is a file, not a skill.

    Severity follows intent, which the auditor can only read from the repository:
    beside a CLAUDE.md, a `.claude/` or a plugin manifest, the author meant these to
    load in Claude Code and they do not - ERROR. Without any such sign the repository
    may target another tool, or installation by copy - WARN, saying where they load.
    """
    found = root_level_skills(root)
    if not found:
        return
    signs = claude_signs(root)
    names = ", ".join(d.name for d in found[:5]) + (f" (+{len(found) - 5})" if len(found) > 5 else "")
    where = ("`skills/<name>/` (plugin)" if LAYOUT != "project"
             else "`.claude/skills/<name>/`")
    report.add(
        "40-skill-not-loaded",
        "ERROR" if signs else "WARN",
        f"{len(found)} skill(s) at the repository root load nowhere as they stand: {names}. "
        "Claude Code finds skills by location, not by content - a project loads "
        "`.claude/skills/`, a plugin loads `skills/`. "
        + (f"This repository carries {', '.join(signs)}, so they were meant to load: "
           f"move them under {where}." if signs else
           "Nothing here says the repository targets Claude Code; if it does, move them "
           "under `skills/` and it loads as a plugin, manifest or not."),
        str(root),
    )


def detect_layout(root: Path) -> str:
    """Which container this is: `marketplace`, `plugin`, `project`, `library` or `none`.

    A repository whose root carries a marketplace manifest and whose plugins live in
    subdirectories is NEITHER a project NOR a plugin. Measured 2026-09-22 on 15
    public plugins from the community catalogue: auditing one as a project produced
    two confident errors - "CLAUDE.md not found" and ".claude/skills/ not found" -
    about files a marketplace has no reason to carry. An auditor that does not know
    a shape reports its own ignorance as the subject's defect.
    """
    if (root / ".claude-plugin" / "plugin.json").is_file():
        return "plugin"
    if (root / ".claude-plugin" / "marketplace.json").is_file():
        return "marketplace"
    # Everything below was measured on 15 public repositories created after
    # 2026-09-22: 6 of the 7 errors reported there were this auditor mistaking a
    # shape it did not know for a project missing its CLAUDE.md.
    if (root / "CLAUDE.md").exists() or (root / ".claude").is_dir():
        return "project"
    # The manifest is optional: `skills/<name>/SKILL.md` at the root loads under
    # `--plugin-dir`, named after the folder, and `claude plugin validate` passes.
    if (root / "skills").is_dir() and any((root / "skills").glob("*/SKILL.md")):
        return "plugin"
    # Skills kept at the root load nowhere as they stand. Their content is still
    # worth auditing - they are meant to be copied somewhere that does load them.
    if root_level_skills(root):
        return "library"
    # A SKILL.md under `.devin/` or `tests/fixtures/` is not a Claude configuration,
    # and "CLAUDE.md not found" there is the auditor's ignorance, not a defect.
    return "none"


def apply_layout(root: Path, layout: str) -> None:
    global CLAUDE_DIR, SKILLS_DIR, AGENTS_DIR, LAYOUT
    LAYOUT = layout
    if layout == "plugin":
        CLAUDE_DIR, SKILLS_DIR, AGENTS_DIR = ".", "skills", "agents"
        manifest = root / ".claude-plugin" / "plugin.json"
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8")).get("skills")
            if isinstance(declared, str):
                SKILLS_DIR = declared.strip("./") or "skills"
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    elif layout == "marketplace":
        # A marketplace carries a catalogue, not a configuration. It has no CLAUDE.md,
        # no settings and no skills of its own - the plugins it lists have those.
        # Pointing the project paths at it would report every absence as a defect.
        CLAUDE_DIR, SKILLS_DIR, AGENTS_DIR = ".", "skills", "agents"
    elif layout in ("library", "none"):
        CLAUDE_DIR, SKILLS_DIR, AGENTS_DIR = ".", ".", "agents"
    else:
        CLAUDE_DIR, SKILLS_DIR, AGENTS_DIR = ".claude", ".claude/skills", ".claude/agents"


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    location: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, check: str, severity: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(check, severity, message, location))

    def has_errors(self) -> bool:
        return any(f.severity == "ERROR" for f in self.findings)

    def counts(self) -> dict[str, int]:
        c = {"OK": 0, "INFO": 0, "WARN": 0, "ERROR": 0}
        for f in self.findings:
            c[f.severity] = c.get(f.severity, 0) + 1
        return c


BLOCK_SCALAR_INDICATORS = {">", ">-", ">+", "|", "|-", "|+"}


def parse_frontmatter(text: str) -> tuple[dict[str, str] | None, int]:
    if not text.startswith("---"):
        return None, 0
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, 0
    data: dict[str, str] = {}
    current_key: str | None = None
    buf: list[str] = []
    block_style: str | None = None

    def flush() -> None:
        nonlocal buf, block_style
        if current_key is None:
            # Anything before the first key - a stray comment, a blank line - is
            # discarded rather than left in the buffer. Until 2026-09-22 this branch
            # returned without clearing `buf`, so a comment above `name:` was glued
            # onto the name, and every downstream check then judged a value the file
            # does not contain: 422 false errors on one sampled public repository.
            buf = []
            block_style = None
            return
        if block_style == ">":
            value = " ".join(part for part in (s.strip() for s in buf) if part)
        else:
            value = "\n".join(buf).strip()
        data[current_key] = value.strip().strip('"').strip("'").replace("''", "'")
        buf = []
        block_style = None

    for raw in lines[1:end]:
        # A YAML comment at column 0 is a comment. Indented, it may be content
        # inside a block scalar, so it is only dropped when no block is open.
        if raw.lstrip().startswith("#") and (block_style is None or not raw[:1].isspace()):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:", raw):
            flush()
            key, _, value = raw.partition(":")
            current_key = key.strip()
            scalar = value.strip()
            if scalar in BLOCK_SCALAR_INDICATORS:
                block_style = scalar[0]
            else:
                buf.append(scalar)
        else:
            buf.append(raw.strip())
    flush()
    return data, end + 1


def strip_code_fences(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    return text


def _fenced_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by fenced code blocks, opening fence included."""
    spans: list[tuple[int, int]] = []
    ouvert: int | None = None
    pos = 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            if ouvert is None:
                ouvert = pos
            else:
                spans.append((ouvert, pos + len(line)))
                ouvert = None
        pos += len(line)
    if ouvert is not None:
        spans.append((ouvert, len(text)))
    return spans


def iter_relative_links(text: str) -> Iterable[tuple[str, int]]:
    # A link inside a fenced block is a specimen, not a reference: the file that
    # shows a reader how to write a context map links to the `src/ordering/`
    # the reader will create, not to one that exists here. Verified 2026-09-22
    # on a sampled public repository, where 3 of 9 link errors were examples.
    spans = _fenced_spans(text)
    for m in re.finditer(r"\]\((\.[^)\s]+)", text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        link = m.group(1)
        link = link.split("#", 1)[0]
        if link:
            yield link, m.start()


def sort_du_depot(depuis: Path, link: str, root: Path) -> bool:
    """True when `link` climbs above the repository root.

    `../../../-/issues/174` is a GitLab issue reference that resolves on the
    forge, never on disk. Nothing outside the repository can be checked here,
    so claiming it is broken states an opinion the auditor cannot hold.
    """
    try:
        cible = (depuis / link).resolve()
        racine = root.resolve()
    except OSError:
        return True
    return racine != cible and racine not in cible.parents


def frontmatter_keys(text: str) -> list[str]:
    """Top-level frontmatter keys, in file order."""
    if not text.startswith("---"):
        return []
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return []
    keys: list[str] = []
    for raw in lines[1:end]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", raw)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def frontmatter_list(value: str) -> list[str]:
    """Split a frontmatter scalar into items, block-list or inline-list alike."""
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        raw_items = value[1:-1].split(",")
    elif "\n" in value or value.lstrip().startswith("- "):
        raw_items = value.splitlines()
    else:
        raw_items = value.split(",")
    items = []
    for raw in raw_items:
        item = raw.strip()
        if item.startswith("- "):
            item = item[2:]
        item = item.strip().strip("'").strip('"').strip()
        if item:
            items.append(item)
    return items


def repo_files(root: Path) -> list[str]:
    """Every repo-relative file path, minus build output and vendored trees.

    Dependency and build directories are pruned deliberately: a rule glob whose
    only matches live in `node_modules/` guards nothing the project writes, so
    counting those matches would hide exactly the inert globs check 22 exists
    to find.
    """
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in WALK_PRUNE_DIRS)
        rel = os.path.relpath(dirpath, root)
        prefix = "" if rel == "." else rel.replace(os.sep, "/") + "/"
        for name in sorted(filenames):
            files.append(prefix + name)
    return files


def expand_braces(pattern: str) -> list[str]:
    """Expand `{a,b}` alternatives into one pattern per branch."""
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    head, tail = pattern[: m.start()], pattern[m.end() :]
    expanded: list[str] = []
    for option in m.group(1).split(","):
        expanded.extend(expand_braces(head + option + tail))
    return expanded


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile one brace-free glob, with `**` spanning path segments."""
    segments = pattern.split("/")
    out: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            out.append(".*" if last else "(?:.*/)?")
            continue
        compiled = ""
        pos = 0
        while pos < len(segment):
            char = segment[pos]
            if char == "*":
                compiled += "[^/]*"
            elif char == "?":
                compiled += "[^/]"
            elif char == "[":
                close = segment.find("]", pos + 1)
                if close == -1:
                    compiled += re.escape(char)
                else:
                    body = segment[pos + 1 : close]
                    compiled += "[" + ("^" + body[1:] if body.startswith("!") else body) + "]"
                    pos = close
            else:
                compiled += re.escape(char)
            pos += 1
        out.append(compiled if last else compiled + "/")
    return re.compile("^" + "".join(out) + "$")


def glob_match_count(pattern: str, files: Iterable[str]) -> int:
    files = list(files)
    matched: set[str] = set()
    for branch in expand_braces(pattern):
        regex = glob_to_regex(branch)
        matched.update(path for path in files if regex.match(path))
    return len(matched)


def check_claude_md(root: Path, report: Report) -> None:
    path = root / "CLAUDE.md"
    if not path.exists():
        report.add("01-claude-md-exists", "ERROR", "CLAUDE.md not found", str(path))
        return
    size = path.stat().st_size
    if size > CLAUDE_MD_MAX_BYTES:
        report.add(
            "01-claude-md-size",
            "ERROR",
            f"CLAUDE.md is {size} bytes (max {CLAUDE_MD_MAX_BYTES}). Move knowledge to skills.",
            str(path),
        )
    else:
        report.add("01-claude-md-size", "OK", f"CLAUDE.md size {size} bytes <= {CLAUDE_MD_MAX_BYTES}.", str(path))

    text = path.read_text(encoding="utf-8")
    stripped = strip_code_fences(text)
    if re.search(r"^\s*//", stripped, re.MULTILINE) or re.search(r"/\*[^!]", stripped):
        report.add(
            "12-no-code-comments",
            "WARN",
            "CLAUDE.md contains // or /* */ outside fenced code blocks.",
            str(path),
        )


# Directories under `skills/` that are not skills. `_`-prefixed is the widespread
# convention for shared material; the rest are the names the Agent Skills spec
# itself uses for a skill's own subdirectories, which appear one level up in
# repositories that share them between skills.
SUPPORT_DIR_NAMES = {"assets", "templates", "scripts", "references", "shared", "common"}


def dossiers_de_skill(base: Path, report: Report) -> list[Path]:
    """Every directory that holds a SKILL.md, however the author nested them.

    A first version assumed exactly one level - `skills/<name>/SKILL.md` - and
    reported every other directory as a missing SKILL.md. Measured on 15 public
    plugins: 21 of 38 errors came from that assumption alone, against repositories
    that group skills by category (`skills/<category>/<skill>/SKILL.md`) or keep a
    `_shared/` directory beside them. Neither is a defect; both are organisation.

    A directory is reported only when it holds NEITHER a SKILL.md NOR any descendant
    that does - that is the case where something really is missing.
    """
    trouves: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "SKILL.md").is_file():
            trouves.append(entry)
            continue
        descendants = sorted(p.parent for p in entry.rglob("SKILL.md"))
        if descendants:
            trouves.extend(descendants)          # category, not a skill
            continue
        if entry.name.startswith("_") or entry.name.lower() in SUPPORT_DIR_NAMES:
            continue                             # support material, not a skill
        report.add("02-skill-md-exists", "ERROR",
                   f"Directory '{entry.name}' under the skills directory holds no SKILL.md "
                   "and no descendant that does. A skill needs one; a support directory "
                   "should be named with a leading underscore so it reads as one.",
                   str(entry))
    return trouves


def check_skills(root: Path, report: Report) -> dict[str, dict]:
    skills_dir = root / SKILLS_DIR
    if LAYOUT == "none":
        return {}
    if LAYOUT == "library":
        # Only the root folders that ARE skills: `src/` or `docs/` beside them are
        # not malformed skills, and the recursive walk would call them that.
        entries = root_level_skills(root)
    elif not skills_dir.is_dir():
        if LAYOUT == "marketplace":
            report.add("02-skills-dir", "INFO",
                       "A marketplace repository ships no skills of its own; the plugins it "
                       "lists carry them. Audit each plugin directory separately.",
                       str(root))
            return {}
        # A plugin may legitimately ship only commands, agents or hooks. Calling
        # that an error tells an author their working plugin is broken, which is
        # how an auditor gets uninstalled rather than heeded.
        autre = [d for d in ("commands", "agents", "hooks") if (root / d).exists()]
        if autre:
            report.add("02-skills-dir", "INFO",
                       f"No {SKILLS_DIR}/ — this one ships {', '.join(autre)} instead. "
                       "Skill checks have no subject here.", str(root))
        else:
            report.add("02-skills-dir", "WARN",
                       f"{SKILLS_DIR}/ not found, and no commands/, agents/ or hooks/ either "
                       "— nothing here declares anything.", str(skills_dir))
        return {}
    else:
        entries = dossiers_de_skill(skills_dir, report)
    skills: dict[str, dict] = {}
    seen_names: dict[str, str] = {}
    for entry in sorted(entries):
        skill_md = entry / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if not fm:
            report.add(
                "02-skill-frontmatter",
                "ERROR",
                f"SKILL.md in '{entry.name}' has no valid YAML frontmatter",
                str(skill_md),
            )
            continue
        name = fm.get("name", "").strip()
        desc = fm.get("description", "").strip()
        if not name:
            report.add("02-skill-frontmatter", "ERROR", "Missing 'name' in frontmatter", str(skill_md))
        if not desc:
            report.add("02-skill-frontmatter", "ERROR", "Missing 'description' in frontmatter", str(skill_md))

        if name and name != entry.name:
            report.add(
                "03-skill-name-matches-folder",
                "ERROR",
                f"Frontmatter name '{name}' does not match folder '{entry.name}'",
                str(skill_md),
            )

        if desc and desc[0] in (">", "|"):
            report.add(
                "02-frontmatter-block-scalar",
                "ERROR",
                f"Skill '{entry.name}' description parsed as a raw block-scalar indicator — frontmatter parser failed.",
                str(skill_md),
            )

        if desc:
            if len(desc) < DESCRIPTION_MIN_CHARS:
                report.add(
                    "04-skill-description-length",
                    "WARN",
                    f"Skill '{entry.name}' description is only {len(desc)} chars (min {DESCRIPTION_MIN_CHARS})",
                    str(skill_md),
                )
            if len(desc) > DESCRIPTION_MAX_CHARS:
                report.add(
                    "04-skill-description-length",
                    "WARN",
                    f"Skill '{entry.name}' description is {len(desc)} chars (> {DESCRIPTION_MAX_CHARS}). "
                    "The Agent Skills spec caps 'description' at 1,024 chars "
                    "(agentskills.io/specification); the 1,536 figure is a "
                    "different mechanism - the listing cutoff for 'description' + 'when_to_use' "
                    "combined, not a per-field limit.",
                    str(skill_md),
                )
            if not ANTI_TRIGGER_RE.search(desc):
                report.add(
                    "04-skill-description-antitrigger",
                    "WARN",
                    f"Skill '{entry.name}' description has no anti-trigger clause. MEASURED, "
                    "2026-09-22: on a near-miss case that names the objects this skill audits "
                    "but asks for them to be authored, the skill fired in 5 of 10 runs with the "
                    "clause removed and 0 of 10 with it present (Fisher exact, p=0.033). The "
                    "count is the Skill tool call itself, not a judge's opinion - with an LLM "
                    "grader the same twenty runs looked like noise, and an earlier reading at "
                    "3 runs per arm pointed the other way. One case moved, a second did not: "
                    "a clause earns its place against the near misses it is written for.",
                    str(skill_md),
                )

        size = skill_md.stat().st_size
        vendored = is_vendored_skill(entry)
        if size > SKILL_MD_ERROR_BYTES:
            report.add(
                "05-skill-md-size",
                "INFO" if vendored else "ERROR",
                f"SKILL.md in '{entry.name}' is {size} bytes (> {SKILL_MD_ERROR_BYTES}). Split it."
                + (" Vendored skill — reported for information only." if vendored else ""),
                str(skill_md),
            )
        elif size > SKILL_MD_COMPACTION_WARN_BYTES:
            report.add(
                "21-skill-md-compaction",
                "INFO" if vendored else "WARN",
                f"SKILL.md in '{entry.name}' is {size} bytes (> {SKILL_MD_COMPACTION_WARN_BYTES}, "
                "roughly 5,000 tokens): content past ~5,000 tokens is dropped after the first "
                "auto-compaction; move detail to references."
                + (" Vendored skill — reported for information only." if vendored else ""),
                str(skill_md),
            )

        if name and name in seen_names:
            report.add(
                "06-skill-duplicate-name",
                "ERROR",
                f"Duplicate skill name '{name}' (also in '{seen_names[name]}')",
                str(skill_md),
            )
        elif name:
            seen_names[name] = entry.name

        for link, _ in iter_relative_links(text):
            target = (skill_md.parent / link).resolve()
            try:
                target.relative_to(skill_md.parent.resolve())
            except ValueError:
                continue
            if not target.exists():
                report.add(
                    "07-skill-broken-link",
                    "ERROR",
                    f"SKILL.md in '{entry.name}' links to non-existent '{link}'",
                    str(skill_md),
                )

        skills[entry.name] = {
            "name": name,
            "description": desc,
            "path": str(skill_md),
            "disable-model-invocation": fm.get("disable-model-invocation", ""),
            "user-invocable": fm.get("user-invocable", ""),
            "paths": fm.get("paths", ""),
        }
    return skills


def check_agents(root: Path, report: Report) -> dict[str, dict]:
    agents_dir = root / AGENTS_DIR
    if not agents_dir.is_dir():
        # A project without agents/ has lost a container it is expected to have.
        # A plugin without agents/ is simply a plugin that ships only skills -
        # the directory is optional in the manifest, so its absence is not news.
        if LAYOUT == "project":
            report.add("08-agents-dir", "WARN", f"{AGENTS_DIR}/ not found", str(agents_dir))
        return {}
    agents: dict[str, dict] = {}
    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        text = entry.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if not fm:
            report.add(
                "08-agent-frontmatter",
                "ERROR",
                f"Agent '{entry.stem}' has no valid YAML frontmatter",
                str(entry),
            )
            continue
        # `tools` and `model` are OPTIONAL. Verified 2026-09-22 against
        # code.claude.com/docs/en/sub-agents: "tools | Required: No - Inherits every
        # tool available to subagents if omitted." Requiring it was house doctrine
        # emitted as an ERROR, and measured on 15 public plugins it produced a false
        # error on somebody else's repository while contradicting the official docs.
        # An audit that is wrong is a nuisance; an audit that is wrong while citing a
        # spec teaches a false rule, with the authority of an error.
        missing = [k for k in ("name", "description") if not fm.get(k)]
        if missing:
            report.add(
                "08-agent-frontmatter",
                "ERROR",
                f"Agent '{entry.stem}' missing required keys: {', '.join(missing)}",
                str(entry),
            )
        desc = fm.get("description", "").strip()
        if desc and desc[0] in (">", "|"):
            report.add(
                "02-frontmatter-block-scalar",
                "ERROR",
                f"Agent '{entry.stem}' description parsed as a raw block-scalar indicator — frontmatter parser failed.",
                str(entry),
            )
        agents[entry.stem] = {"name": fm.get("name", ""), "description": desc, "path": str(entry)}
    return agents


def check_agent_descriptions(report: Report, agents: dict[str, dict]) -> None:
    for name, meta in agents.items():
        desc = meta.get("description", "")
        if not desc:
            continue
        if len(desc) < DESCRIPTION_MIN_CHARS:
            report.add(
                "08b-agent-description",
                "WARN",
                f"Agent '{name}' description is only {len(desc)} chars (min {DESCRIPTION_MIN_CHARS})",
                meta["path"],
            )
        if len(desc) > AGENT_DESCRIPTION_MAX_CHARS:
            report.add(
                "08b-agent-description",
                "WARN",
                f"Agent '{name}' description is {len(desc)} chars (> {AGENT_DESCRIPTION_MAX_CHARS}). Description = trigger surface; move knowledge to the body.",
                meta["path"],
            )
        if not ANTI_TRIGGER_RE.search(desc):
            report.add(
                "08b-agent-description",
                "WARN",
                f"Agent '{name}' description has no anti-trigger clause",
                meta["path"],
            )


def listing_hidden_skills(root: Path, skills: dict[str, dict]) -> set[str]:
    """Skills whose description is NOT paid for in the per-turn skill listing.

    Three mechanisms withhold a description: `disable-model-invocation: true` in
    the skill's own frontmatter, a `skillOverrides` entry in
    `.claude/settings.json` set to anything other than "on", and a non-empty
    `paths:` frontmatter list. The last one is not documented as a withholding
    mechanism by Anthropic, but it was measured twice on this project — headless
    on 2026-09-03, interactive on 2026-09-09 — to remove the skill from the
    listing entirely (name and description) and to make it uninvocable by name,
    with no auto-load and no next-turn offer when a matching file is touched.
    The pilot was closed on 2026-09-09 and no skill carries `paths:` any more;
    this branch is kept as a regression guard, so that a re-added `paths:`
    surfaces as "withheld but not named in the Skills index" instead of a
    silently unreachable skill.
    See references/skill-runtime-mechanisms.md, section Path-scoped skills.

    All three are invisible to a naive character count, which is why the budget
    is reported twice.
    """
    hidden = {
        name
        for name, data in skills.items()
        if str(data.get("disable-model-invocation", "")).strip().lower() == "true"
        or frontmatter_list(data.get("paths", ""))
    }
    settings = root / CLAUDE_DIR / "settings.json"
    if settings.is_file():
        try:
            overrides = json.loads(settings.read_text(encoding="utf-8")).get("skillOverrides", {})
        except (json.JSONDecodeError, UnicodeDecodeError):
            overrides = {}
        for name, state in overrides.items():
            if name in skills and str(state).strip().lower() != "on":
                hidden.add(name)
    return hidden


def check_always_loaded_budget(
    root: Path, report: Report, skills: dict[str, dict], agents: dict[str, dict]
) -> None:
    claude_md = root / "CLAUDE.md"
    claude_md_bytes = claude_md.stat().st_size if claude_md.exists() else 0
    hidden = listing_hidden_skills(root, skills)
    raw_skill_chars = sum(len(s.get("description", "")) for s in skills.values())
    skill_chars = sum(
        len(s.get("description", "")) for name, s in skills.items() if name not in hidden
    )
    agent_chars = sum(len(a.get("description", "")) for a in agents.values())
    total = claude_md_bytes + skill_chars + agent_chars
    suppressed = raw_skill_chars - skill_chars
    detail = (
        f" [{len(hidden)} skill(s) withheld from the listing: {suppressed} chars not paid; "
        f"raw skill total {raw_skill_chars}]"
        if hidden
        else ""
    )
    message = (
        f"Always-loaded context: {total} chars "
        f"(CLAUDE.md {claude_md_bytes} B + skill descriptions {skill_chars} + agent descriptions {agent_chars})."
        f"{detail}"
    )
    if total > ALWAYS_LOADED_ERROR_CHARS:
        report.add(
            "17-always-loaded-budget",
            "ERROR",
            f"{message} Exceeds the hard budget ({ALWAYS_LOADED_ERROR_CHARS}). Trim descriptions or CLAUDE.md.",
            str(claude_md),
        )
    elif total > ALWAYS_LOADED_WARN_CHARS:
        report.add(
            "17-always-loaded-budget",
            "WARN",
            f"{message} Above the target budget ({ALWAYS_LOADED_WARN_CHARS}).",
            str(claude_md),
        )
    else:
        report.add("17-always-loaded-budget", "INFO", message, str(claude_md))
    if skill_chars > SKILL_DESC_AGGREGATE_WARN_CHARS:
        report.add(
            "17-always-loaded-budget",
            "WARN",
            f"Skill descriptions alone total {skill_chars} chars (> {SKILL_DESC_AGGREGATE_WARN_CHARS}): "
            "approaching the harness listing budget. `.claude/settings.json` sets "
            "`skillListingBudgetFraction: 0.025`, scaling the ~23.1k-23.5k cutoff observed on "
            "2026-07-19 at the 0.01 default to roughly 58k chars. Trim descriptions rather than "
            "raising this ratchet again; the next raise needs a fresh runtime measurement.",
            str(claude_md),
        )


def check_unreadable(root: Path, report: Report) -> None:
    """Files under .claude/ the auditor could not open.

    Until 2026-09-22 nine call sites caught only `UnicodeDecodeError`, so a file
    the process may not read raised `PermissionError` and took the whole audit
    down - found when an eval sandbox masked `.claude/loop.md` to mode 000 and
    the run reported "the audit script crashes". The catches now include OSError,
    which turns a crash into a skip; this check exists so the skip is not silent.
    An auditor that says nothing about what it could not read is claiming a
    coverage it does not have.
    """
    base = root / CLAUDE_DIR
    if not base.is_dir():
        return
    muets: list[str] = []
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        try:
            with f.open("rb"):
                pass
        except OSError:
            muets.append(str(f.relative_to(root)))
    if muets:
        report.add(
            "38-unreadable",
            "WARN",
            f"{len(muets)} file(s) under {CLAUDE_DIR}/ could not be opened and were not "
            f"audited: {', '.join(muets[:5])}"
            + (f" and {len(muets) - 5} more" if len(muets) > 5 else "")
            + ". Every check that would have read them reported nothing, which is not "
            "the same as reporting that they are sound.",
            str(base),
        )


def check_see_skill_targets(root: Path, report: Report, skills: dict[str, dict]) -> None:
    if not skills:
        return
    targets: list[Path] = []
    for sub in ("skills", "agents", "rules"):
        base = root / CLAUDE_DIR / sub
        if base.is_dir():
            targets.extend(sorted(base.rglob("*.md")))
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(
            r"➜\s*See skill:\s*([a-z0-9][a-z0-9-]*(?::[a-z0-9][a-z0-9-]*)?)", text
        ):
            name = m.group(1)
            # `plugin:skill` names a skill that lives outside this repository. Whether
            # it resolves depends on what the reader has installed, and nothing on disk
            # says. Until 2026-09-22 the pattern stopped at the `:`, captured the plugin
            # name alone, and reported it missing - so a project routing to this very
            # plugin (`➜ See skill: deadweight:config-auditor`, the convention this
            # plugin prescribes) earned an ERROR for following the doctrine it ships.
            # Skipping is the same call made for a link that climbs above the root:
            # claiming it is broken states an opinion the auditor cannot hold.
            if ":" in name:
                continue
            if name not in skills:
                report.add(
                    "18-see-skill-target",
                    "ERROR",
                    f"Cross-reference '➜ See skill: {name}' points to a non-existent skill.",
                    str(path),
                )


def check_documented_flags(root: Path, report: Report) -> None:
    """Every flag the documentation shows must exist in the script.

    Removing a feature and leaving its documentation is the same defect as renaming
    a skill and leaving its mentions: the code is right, the reader is wrong, and
    nothing fails. Measured on this plugin on 2026-09-22, after `--record` was
    removed one release earlier: SIX live references survived, including two inside
    COMMAND BLOCKS a reader would copy and run, and a README that contradicted
    itself - one section said the feature was removed while two others described it
    as present. Thirty-six checks saw none of it.

    Only flags on a line that invokes the audit script are read. A document
    legitimately shows `claude plugin eval --allow-tools` or `git log -p`, and a
    check that flagged those would be noise - and noise is how a check gets skipped.
    """
    script = root / SKILLS_DIR / "config-auditor" / "scripts" / "audit.py"
    if not script.is_file():
        script = Path(__file__)
    try:
        src = script.read_text(encoding="utf-8")
    except OSError:
        return
    reels = set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', src))
    if not reels:
        return
    base = root / SKILLS_DIR
    fichiers = sorted(base.rglob("*.md")) if base.is_dir() else []
    for extra in ("README.md", "CHANGELOG.md"):
        p = root / extra
        if p.is_file():
            fichiers.append(p)
    vus: dict[str, list[str]] = {}
    for f in fichiers:
        try:
            texte = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # FENCED CODE BLOCKS ONLY. A first version read any line containing
        # `audit.py` and returned five findings across the fleet, all five false:
        # « This is why `audit.py` has no `--fix` flag » - flagged for asserting
        # exactly what the check wants to be true - and two lines where prose put
        # two different commands side by side. The defect this check exists for is
        # a flag inside a block someone COPIES AND RUNS; prose that mentions a flag
        # is a lesser problem and not this one. A detector that is wrong five times
        # out of five is one nobody keeps.
        in_block = False
        for i, line in enumerate(texte.splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_block = not in_block
                continue
            if not in_block or "audit.py" not in line:
                continue
            for flag in re.findall(r"(?<![\w-])(--[a-z0-9-]+)", line):
                if flag not in reels:
                    vus.setdefault(flag, []).append(f"{f.relative_to(root)}:{i}")
    for flag, ou in sorted(vus.items()):
        # The CHANGELOG is exempt: naming what was removed is its job.
        vivants = [x for x in ou if not x.startswith("CHANGELOG.md")]
        if not vivants:
            continue
        report.add("37-documented-flag", "ERROR",
                   f"`{flag}` is shown with audit.py in {len(vivants)} place(s) "
                   f"({', '.join(vivants[:4])}) but the script does not accept it. A reader "
                   "copying that line gets an error, and nothing else fails.", str(root))


def check_foreign_skill_mentions(root: Path, report: Report, skills: dict[str, dict]) -> None:
    """A plugin must not route to skills it does not ship.

    A reference to a skill the reader does not have is a dangling reference, and a
    dangling reference costs a model more than a human: a human shrugs, a model goes
    looking - Glob, Grep, wrong files read. Bounded cost for one, unbounded for the
    other. In a PROJECT that risk is local and check 18 already covers the formal
    `➜ See skill:` form. In a PLUGIN the same sentence ships to every consumer, and
    in most of them the target does not exist.

    Two shapes are legitimate and are not flagged: the declared fictional example
    domain (a plugin's references need a worked example), and an angle-bracket
    placeholder. What is flagged is a bare backticked skill name that the plugin
    does not ship - it reads as a routing instruction and is not one.

    The fix is never to delete the sentence: it is to say that absent is a valid
    state, or to move the name into the example domain.
    """
    if LAYOUT != "plugin":
        return
    # ROUTING CONTEXTS ONLY. A first version matched any backticked kebab-case
    # token and returned 21 findings, of which some fifteen were frontmatter keys
    # (`disable-model-invocation`, `allowed-tools`), eval vocabulary
    # (`anti-trigger`, `near-miss`) and built-in commands. A detector that is
    # wrong seven times out of ten is one people learn to skip, which is worse
    # than not having it. What makes a name a routing instruction is the arrow in
    # front of it, not its shape.
    example_prefixes = ("shop-", "ui-", "api-", "data-")
    # A hyphen is not mandatory in a skill name: a first version required one and
    # missed `hooks`, `review`, `translate`, `release`. The arrow is what qualifies
    # the context; the shape of the name does not have to.
    #
    # A generic `→ `name`` was accepted here until 2026-09-22 and had to go. Measured
    # on 15 third-party public repositories it produced 140 findings of which some
    # 130 were false, because a bare arrow is how everyone writes a state table:
    # `running → `success``, `→ `not-started``, `→ `8867-4``. An arrow means
    # transition far more often than it means routing. `➜ See skill:` is a stated
    # convention and carries the intent; `→` carries none.
    routing = re.compile(
        r"➜\s*See skill:\s*([a-z0-9]+(?:-[a-z0-9]+)*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?)"
    )
    seen: dict[str, list[str]] = {}
    base = root / SKILLS_DIR
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in routing.finditer(text):
            name = m.group(1)
            # A `plugin:skill` reference already tells the reader the target is
            # external and where it comes from - which is the very remediation this
            # check asks for. It is the bare name, readable as local, that misleads.
            if ":" in name:
                continue
            if name in skills or name.startswith(example_prefixes):
                continue
            # An agent this plugin ships is a legitimate routing target, and half
            # the composite names the old regex caught were agents: `code-implementer`,
            # `test-writer`, `design-reviewer`, `session-reviewer`.
            if (root / "agents" / f"{name}.md").is_file():
                continue
            seen.setdefault(name, []).append(str(path.relative_to(root)))
    for name, where in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        report.add(
            "36-foreign-skill",
            "WARN",
            f"`{name}` reads as a skill name but this plugin does not ship it "
            f"({len(where)} mention(s), e.g. {where[0]}). In a consuming project it may "
            "not exist: say that absent is a valid state, or move it to the example domain.",
            str(root / SKILLS_DIR),
        )


def check_cross_refs(
    root: Path, report: Report, skills: dict[str, dict], agents: dict[str, dict]
) -> None:
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        return
    text = claude_md.read_text(encoding="utf-8")

    referenced_agents: set[str] = set()
    agents_table_match = re.search(
        r"##\s+Agents directory.*?(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE
    )
    if agents_table_match:
        block = agents_table_match.group(0)
        for m in re.finditer(r"\|\s*`([a-z0-9-]+)`\s*\|", block):
            referenced_agents.add(m.group(1))

    for agent_name in agents:
        if agent_name not in referenced_agents:
            report.add(
                "09-agent-in-claude-md",
                "ERROR",
                f"Agent '{agent_name}' exists in .claude/agents/ but is not listed in CLAUDE.md 'Agents directory'",
                str(claude_md),
            )
    for ref in referenced_agents:
        if ref not in agents:
            report.add(
                "09-claude-md-agent-missing",
                "ERROR",
                f"CLAUDE.md references agent '{ref}' but .claude/agents/{ref}.md does not exist",
                str(claude_md),
            )


def check_english_only(root: Path, report: Report) -> None:
    targets: list[Path] = []
    skills_dir = root / SKILLS_DIR
    if skills_dir.is_dir():
        for skill in skills_dir.iterdir():
            if not skill.is_dir():
                continue
            # Scripts count. The rule says English in every persisted artefact, and
            # a script is the most read file in a plugin after the README. Until
            # 2026-09-22 this check looked only at `*.md`, so the auditor's own
            # source drifted into another language - 95 French words, found by a
            # reader, not by the check that exists for exactly this.
            #
            # The heuristic word list is DATA for this check and is French on
            # purpose. It is fenced with `# i18n-data:` markers and skipped, rather
            # than exempting the whole file: exempting `audit.py` would have made
            # the one file where the drift happened the one file that cannot be
            # policed.
            for p in sorted(list(skill.rglob("*.md")) + list(skill.rglob("*.py"))
                            + list(skill.rglob("*.sh"))):
                if p.name.endswith(ENGLISH_ONLY_SUFFIX_EXEMPT):
                    continue
                if p.relative_to(skills_dir).as_posix() in ENGLISH_ONLY_EXEMPT:
                    continue
                targets.append(p)
    src_dir = root / "src"
    if src_dir.is_dir():
        translate_dir = src_dir / "translate"
        for pattern in ("*.md", "*.txt"):
            for p in src_dir.rglob(pattern):
                if p.name.endswith(ENGLISH_ONLY_SUFFIX_EXEMPT):
                    continue
                if LOCALE_MARKED_RE.search(p.as_posix()):
                    continue          # declared as a locale: French there is correct
                # An exemption must cover EVERY path the check reports. Until
                # 2026-09-22 this branch never consulted the overlay, so a project
                # could declare an exception on a file under src/ and keep being
                # reported for it - the mechanism meant to remove the noise produced
                # it instead. Paths here are relative to the project root, since
                # that is how a reader names a file under src/.
                if p.relative_to(root).as_posix() in ENGLISH_ONLY_EXEMPT:
                    continue
                if translate_dir not in p.parents:
                    targets.append(p)
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Drop any `# i18n-data:` fenced block. A check whose own dictionary trips
        # it would be unusable on the file that carries the dictionary - and
        # exempting that file instead would make the one place where the drift
        # happened the one place that cannot be policed.
        if "i18n-data: start" in text:
            kept, on = [], True
            for ln in text.splitlines():
                if "i18n-data: start" in ln:
                    on = False
                elif "i18n-data: end" in ln:
                    on = True
                elif on:
                    kept.append(ln)
            text = "\n".join(kept)
        stripped = strip_code_fences(text).lower()
        words = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ']+", stripped)
        hits = sum(1 for w in words if w in FRENCH_HEURISTIC_WORDS)
        if hits >= FRENCH_HEURISTIC_THRESHOLD:
            report.add(
                "11-english-only",
                "WARN",
                f"File appears to contain French content ({hits} heuristic hits).",
                str(path),
            )


def check_no_code_comments_in_skills(root: Path, report: Report) -> None:
    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    for skill_md in skills_dir.glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        stripped = strip_code_fences(text)
        if re.search(r"^\s*//", stripped, re.MULTILINE):
            report.add(
                "12-no-code-comments",
                "WARN",
                "SKILL.md contains // comment outside fenced code block",
                str(skill_md),
            )


def check_no_global_scripts(root: Path, report: Report) -> None:
    global_scripts = root / CLAUDE_DIR / "scripts"
    if not global_scripts.exists():
        return
    files = [p for p in global_scripts.rglob("*") if p.is_file()]
    if not files:
        return
    for path in files:
        report.add(
            "13-no-global-scripts",
            "ERROR",
            f"Script '{path.name}' lives in .claude/scripts/ (global pool). Move it to its owning skill: .claude/skills/<owner>/scripts/{path.name}.",
            str(path),
        )


RULE_MAX_BYTES = 2048


def check_rules(root: Path, report: Report) -> None:
    rules_dir = root / CLAUDE_DIR / "rules"
    if not rules_dir.is_dir():
        return
    for entry in sorted(rules_dir.iterdir()):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        text = entry.read_text(encoding="utf-8")
        size = entry.stat().st_size

        if size > RULE_MAX_BYTES:
            report.add(
                "14-rule-size",
                "WARN",
                f"Rule '{entry.name}' is {size} bytes (> {RULE_MAX_BYTES}). Consider converting to a skill.",
                str(entry),
            )

        fm, _ = parse_frontmatter(text)
        if fm is not None:
            paths_val = fm.get("paths", "").strip()
            if not paths_val:
                report.add(
                    "14-rule-no-paths",
                    "WARN",
                    f"Rule '{entry.name}' has frontmatter but no 'paths:' glob.",
                    str(entry),
                )

        stripped = strip_code_fences(text)
        if re.search(r"^\s*//", stripped, re.MULTILINE):
            report.add(
                "14-rule-code-comments",
                "WARN",
                f"Rule '{entry.name}' contains // comment outside fenced code block.",
                str(entry),
            )

        words = re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ']+", stripped.lower())
        hits = sum(1 for w in words if w in FRENCH_HEURISTIC_WORDS)
        if hits >= FRENCH_HEURISTIC_THRESHOLD:
            report.add(
                "14-rule-english-only",
                "WARN",
                f"Rule '{entry.name}' appears to contain French content ({hits} heuristic hits).",
                str(entry),
            )


def check_skill_index(root: Path, report: Report, skills: dict[str, dict]) -> None:
    """The CLAUDE.md index names only the skills the harness listing withholds.

    The per-turn listing already carries every visible skill's name and
    description, so re-listing all of them in CLAUDE.md pays twice. What the
    listing cannot convey is what it is hiding: a `disable-model-invocation`
    skill is absent entirely, and a `skillOverrides` entry may strip the
    description. Those are exactly the entries this section must carry, and
    exactly what this check reconciles.
    """
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists() or not skills:
        return
    text = claude_md.read_text(encoding="utf-8")
    section = re.search(r"##\s+Skills index.*?(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    hidden = listing_hidden_skills(root, skills)
    if not section:
        # The section exists to point at what the listing withholds. With nothing
        # withheld, its right content is empty, and demanding an empty heading was
        # an error on every project outside the fleet it was calibrated on: a
        # minimal clean project failed on first contact. The defect is not the
        # missing heading; it is a withheld skill that nothing points at.
        if not hidden:
            report.add(
                "15-skill-index",
                "INFO",
                "No 'Skills index' section, and no skill is withheld from the harness listing: "
                "nothing needs one.",
                str(claude_md),
            )
        for name in sorted(hidden):
            report.add(
                "15-skill-index",
                "ERROR",
                f"Skill '{name}' is withheld from the harness listing, and CLAUDE.md has no "
                "'Skills index' section to point at it. A withheld skill that nothing points at "
                "is unreachable.",
                str(claude_md),
            )
        return
    body = "\n".join(l for l in section.group(0).splitlines() if not l.lstrip().startswith("➜"))
    indexed = {m.group(1) for m in re.finditer(r"`([a-z0-9][a-z0-9-]+)`", body)}

    for name in sorted(hidden):
        if name not in indexed:
            report.add(
                "15-skill-index",
                "ERROR",
                f"Skill '{name}' is withheld from the harness listing but is not named in the CLAUDE.md 'Skills index'. "
                "A withheld skill that nothing points at is unreachable.",
                str(claude_md),
            )
    for ref in sorted(indexed):
        if ref in skills and ref not in hidden:
            report.add(
                "15-skill-index",
                "WARN",
                f"CLAUDE.md 'Skills index' names '{ref}', but that skill is fully listed by the harness. "
                "Drop the entry: the index carries withheld skills only.",
                str(claude_md),
            )


def is_vendored_skill(skill_dir: Path) -> bool:
    """A skill shipping its own LICENSE is upstream code vendored verbatim.

    Project size and split budgets do not apply to files we must be able to
    re-sync from upstream; a table of contents is still required so the file
    stays navigable.
    """
    return (skill_dir / "LICENSE.txt").is_file() or (skill_dir / "LICENSE").is_file()


def check_reference_sizes(root: Path, report: Report) -> None:
    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    for ref in skills_dir.glob("*/references/**/*.md"):
        skill_dir = skills_dir / ref.relative_to(skills_dir).parts[0]
        try:
            text = ref.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.count("\n") + 1
        if lines <= REFERENCE_TOC_LINES:
            continue
        head = "\n".join(text.splitlines()[:REFERENCE_TOC_SCAN_LINES]).lower()
        has_toc = "contents:" in head or "## contents" in head or "# contents" in head
        rel_name = ref.relative_to(skills_dir).as_posix()
        if not has_toc:
            report.add(
                "16-reference-size",
                "WARN",
                f"Reference '{rel_name}' is {lines} lines (> {REFERENCE_TOC_LINES}) with no table of contents. Add a 'Contents:' block near the top.",
                str(ref),
            )
        elif lines > REFERENCE_WARN_LINES and not is_vendored_skill(skill_dir):
            report.add(
                "16-reference-size",
                "WARN",
                f"Reference '{rel_name}' is {lines} lines (> {REFERENCE_WARN_LINES}) even with a table of contents. Split it.",
                str(ref),
            )


def check_frontmatter_quoting(root: Path, report: Report) -> None:
    """Flag plain (unquoted) frontmatter scalars containing ': '.

    Claude Code's frontmatter reader is tolerant, but a plain scalar holding
    a colon-space sequence — which every 'Don't use for: ...' anti-trigger
    produces — is invalid under strict YAML and is rejected by js-yaml and
    PyYAML. Quote the value so any downstream consumer can parse the file.
    """
    targets: list[Path] = []
    skills_dir = root / SKILLS_DIR
    agents_dir = root / AGENTS_DIR
    if skills_dir.is_dir():
        targets.extend(sorted(skills_dir.glob("*/SKILL.md")))
    if agents_dir.is_dir():
        targets.extend(sorted(agents_dir.glob("*.md")))

    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.startswith("---"):
            continue
        lines = text.splitlines()
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            continue
        for raw in lines[1:end]:
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(\S.*)$", raw)
            if not m:
                continue
            key, scalar = m.group(1), m.group(2).strip()
            if scalar[0] in "\"'>|[{":
                continue
            if ": " in scalar:
                report.add(
                    "19-frontmatter-quoting",
                    "WARN",
                    f"'{key}' in {path.parent.name if path.name == 'SKILL.md' else path.stem} is an unquoted scalar containing ': ' — invalid under strict YAML. Wrap the value in double quotes.",
                    str(path),
                )


def check_all_relative_links(root: Path, report: Report) -> None:
    """Every relative markdown link under .claude/ resolves to a real file.

    Check 07 only inspects SKILL.md and only follows links that stay inside the
    skill folder, so a reference linking to a sibling skill — or any link at
    all from a reference file — went unverified. Moving a section one directory
    deeper is exactly how those break, silently.
    """
    base = root / CLAUDE_DIR
    if not base.is_dir():
        return
    for md in sorted(base.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for link, _ in iter_relative_links(text):
            if sort_du_depot(md.parent, link, root):
                continue
            if not (md.parent / link).exists():
                report.add(
                    "20-relative-links",
                    "ERROR",
                    f"'{md.relative_to(base)}' links to non-existent '{link}'",
                    str(md),
                )


def check_rule_globs(root: Path, report: Report) -> None:
    """Every `paths:` glob in a rule expands to at least one real file.

    A glob that matches nothing never loads its rule: the guardrail is silently
    inert, and nothing about the file itself looks wrong. An unescaped `[` is
    the documented way to produce one by accident — it opens a character class
    instead of matching a literal bracket.
    """
    rules_dir = root / CLAUDE_DIR / "rules"
    if not rules_dir.is_dir():
        return
    files = repo_files(root)
    for entry in sorted(rules_dir.glob("*.md")):
        try:
            fm, _ = parse_frontmatter(entry.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if not fm:
            continue
        for pattern in frontmatter_list(fm.get("paths", "")):
            if glob_match_count(pattern, files):
                continue
            bracket = (
                " The unescaped '[' opens a character class — escape it if a literal bracket was meant."
                if "[" in pattern
                else ""
            )
            report.add(
                "22-rule-glob-match",
                "WARN",
                f"Rule '{entry.name}' glob '{pattern}' matches no file in the repository, "
                f"so the rule never loads for it.{bracket}",
                str(entry),
            )


def is_known_tool(entry: str) -> bool:
    """Accept a bare tool, a parameterised `Tool(...)` form, `mcp__*`, or `*`."""
    name = entry.strip()
    if not name:
        return False
    if name == "*" or name.startswith("mcp__"):
        return True
    return name.split("(", 1)[0].strip() in KNOWN_TOOLS


def check_agent_frontmatter_validity(root: Path, report: Report, skills: dict[str, dict]) -> None:
    """Agent frontmatter names things that exist: tools, preloadable skills, a model tier."""
    agents_dir = root / AGENTS_DIR
    if not agents_dir.is_dir():
        return
    inventory: dict[str, int] = {}
    unvalidated: dict[str, int] = {}
    for entry in sorted(agents_dir.glob("*.md")):
        try:
            text = entry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, _ = parse_frontmatter(text)
        if not fm:
            continue

        for tool in frontmatter_list(fm.get("tools", "")):
            if is_known_tool(tool):
                continue
            report.add(
                "23-agent-tools",
                "ERROR",
                f"Agent '{entry.stem}' grants unknown tool '{tool}'. The fan-out tool is 'Agent'; "
                "there is no 'Task'. Parameterised forms like 'Agent(review)' or 'Bash(git diff:*)' "
                "and 'mcp__*' names are accepted.",
                str(entry),
            )

        for preload in frontmatter_list(fm.get("skills", "")):
            if not (root / SKILLS_DIR / preload / "SKILL.md").is_file():
                report.add(
                    "23-agent-skills-preload",
                    "ERROR",
                    f"Agent '{entry.stem}' preloads skill '{preload}', but "
                    f".claude/skills/{preload}/SKILL.md does not exist.",
                    str(entry),
                )
                continue
            flag = str(skills.get(preload, {}).get("disable-model-invocation", "")).strip().lower()
            if flag == "true":
                report.add(
                    "23-agent-skills-preload",
                    "WARN",
                    f"Agent '{entry.stem}' preloads '{preload}', which carries "
                    "'disable-model-invocation: true' and cannot be preloaded. Read it by path instead: "
                    f".claude/skills/{preload}/SKILL.md.",
                    str(entry),
                )

        model = fm.get("model", "").strip()
        if model and model not in KNOWN_MODEL_TIERS and not model.startswith("claude-"):
            report.add(
                "23-agent-model",
                "WARN",
                f"Agent '{entry.stem}' declares model '{model}'. Expected one of "
                f"{', '.join(sorted(KNOWN_MODEL_TIERS))} or a 'claude-*' model id.",
                str(entry),
            )

        for key in frontmatter_keys(text):
            inventory[key] = inventory.get(key, 0) + 1
            if key not in AGENT_VALIDATED_KEYS:
                unvalidated[key] = unvalidated.get(key, 0) + 1

    if inventory:
        seen = ", ".join(f"{k} ({v})" for k, v in sorted(inventory.items()))
        drift = ", ".join(f"{k} ({v})" for k, v in sorted(unvalidated.items())) or "none"
        report.add(
            "23-agent-frontmatter-keys",
            "INFO",
            f"Agent frontmatter keys in use: {seen}. Keys this script does not validate: {drift}.",
            str(agents_dir),
        )


def check_settings_scope(root: Path, report: Report) -> None:
    """Settings keys that are silently ignored at project scope, and dangling overrides."""
    for name in ("settings.json", "settings.local.json"):
        path = root / CLAUDE_DIR / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.add("24-settings-parse", "ERROR", f"'{name}' is not valid JSON: {exc}", str(path))
            continue
        if not isinstance(data, dict):
            report.add("24-settings-parse", "ERROR", f"'{name}' does not hold a JSON object.", str(path))
            continue

        report.add(
            "24-settings-keys",
            "INFO",
            f"'{name}' top-level keys: {', '.join(sorted(data)) if data else '(none)'}.",
            str(path),
        )

        permissions = data.get("permissions")
        mode = str(permissions.get("defaultMode", "")).strip() if isinstance(permissions, dict) else ""
        if mode in PROJECT_SCOPE_IGNORED_MODES:
            report.add(
                "24-settings-default-mode",
                "WARN",
                f"'permissions.defaultMode: {mode}' in '{name}' is ignored at project scope since "
                "Claude Code 2.1.257 — set it in user or managed settings, or pass --permission-mode.",
                str(path),
            )

        overrides = data.get("skillOverrides")
        if isinstance(overrides, dict):
            for skill_name in sorted(overrides):
                if not (root / SKILLS_DIR / skill_name / "SKILL.md").is_file():
                    report.add(
                        "24-settings-skill-overrides",
                        "ERROR",
                        f"skillOverrides in '{name}' names '{skill_name}', which is not a skill folder "
                        "under .claude/skills/.",
                        str(path),
                    )


def _hook_declarations(root: Path) -> list[tuple[Path, object]]:
    """Where hooks are declared, which depends on the container.

    A project declares them among its settings; a plugin ships `hooks/hooks.json`
    at its root. Same schema, two homes - the same split as skills, and the same
    reason the layout has to be detected before anything is read.
    """
    rels = ([Path("hooks") / "hooks.json"] if LAYOUT == "plugin"
            else [Path(CLAUDE_DIR) / "settings.json",
                  Path(CLAUDE_DIR) / "settings.local.json"])
    return [(root / rel, rel) for rel in rels if (root / rel).is_file()]


def _hook_paths(command: str) -> list[str]:
    """Tokens of a hook command that name a file this script can resolve.

    Every token is examined, not just the first: `python3 "$X/audit.py" --root .`
    runs a script the first token does not name. Tokens that cannot be resolved
    WITHOUT GUESSING are returned to nobody - a bare binary on PATH, a flag, an
    inline jq filter. A check that guessed here would report `npm run lint` as a
    dead path, and a check that cries wolf is how people learn to skip the whole
    report.
    """
    out = []
    for tok in command.split():
        clean = tok.replace('"', "").replace("'", "")
        if "/" not in clean:
            continue
        if clean.startswith(HOOK_PLUGIN_ROOT_VARS + HOOK_PROJECT_DIR_VARS + ("./",)):
            out.append(clean)
    return out


def check_hooks(root: Path, report: Report) -> None:
    """Hooks: the only configuration that executes, and the last one audited.

    A hook is the highest-consequence object in a Claude Code configuration - it
    runs code on an event, before anyone reads anything - and it was the one
    component this auditor could not see at all until 2026-09-22. Every other
    check here asks whether some text will be read; this one asks whether some
    code will run, against what, and at what price.

    Four failures it catches, none of which announces itself at runtime:
      - an event name that does not exist: it never fires, and never complains;
      - a command whose script is not there: a dead anchor that executes;
      - `${CLAUDE_PLUGIN_ROOT}` in a PROJECT hook: unresolvable by construction,
        since one variable cannot designate one plugin among the N installed;
      - no explicit timeout: the default is ten minutes of a hung session.
    """
    for path, rel in _hook_declarations(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.add("35-hooks-parse", "ERROR", f"'{rel}' is not valid JSON: {exc}", str(path))
            continue
        hooks = data.get("hooks") if isinstance(data, dict) else None
        if hooks is None:
            continue
        if not isinstance(hooks, dict):
            report.add("35-hooks-shape", "ERROR",
                       f"'hooks' in '{rel}' is not an object of event -> entries.", str(path))
            continue

        injecting = []
        for event in sorted(hooks):
            if event not in KNOWN_HOOK_EVENTS:
                report.add("35-hooks-event", "ERROR",
                           f"'{event}' is not a hook event. It will never fire and will never "
                           f"report that it did not. Known events: {len(KNOWN_HOOK_EVENTS)}, "
                           "listed in KNOWN_HOOK_EVENTS.", str(path))
                continue
            entries = hooks[event]
            if not isinstance(entries, list):
                report.add("35-hooks-shape", "ERROR",
                           f"'{event}' in '{rel}' must hold a list of matcher groups.", str(path))
                continue
            for i, entry in enumerate(entries):
                where = f"{event}[{i}]"
                if not isinstance(entry, dict):
                    report.add("35-hooks-shape", "ERROR",
                               f"{where} in '{rel}' is not an object.", str(path))
                    continue
                if entry.get("matcher") and event in MATCHERLESS_HOOK_EVENTS:
                    report.add("35-hooks-matcher", "WARN",
                               f"{where} declares matcher '{entry['matcher']}' on '{event}', which "
                               "always fires. The matcher filters nothing and reads as if it did.",
                               str(path))
                inner = entry.get("hooks")
                if not isinstance(inner, list) or not inner:
                    report.add("35-hooks-shape", "ERROR",
                               f"{where} in '{rel}' has no 'hooks' list.", str(path))
                    continue
                for j, hook in enumerate(inner):
                    spot = f"{where}.hooks[{j}]"
                    if not isinstance(hook, dict):
                        report.add("35-hooks-shape", "ERROR",
                                   f"{spot} in '{rel}' is not an object.", str(path))
                        continue
                    kind = hook.get("type", "command")
                    if kind != "command":
                        continue
                    command = hook.get("command")
                    if not isinstance(command, str) or not command.strip():
                        report.add("35-hooks-shape", "ERROR",
                                   f"{spot} in '{rel}' is a command hook with no 'command'.",
                                   str(path))
                        continue
                    if "timeout" not in hook:
                        report.add("35-hooks-timeout", "WARN",
                                   f"{spot} in '{rel}' sets no 'timeout': the default is "
                                   f"{HOOK_DEFAULT_TIMEOUT}s. A hook that hangs holds the event it "
                                   "was meant to observe.", str(path))
                    for token in _hook_paths(command):
                        if token.startswith(HOOK_PLUGIN_ROOT_VARS) and LAYOUT != "plugin":
                            report.add("35-hooks-command", "ERROR",
                                       f"{spot} in '{rel}' uses CLAUDE_PLUGIN_ROOT, which a project "
                                       "hook cannot resolve: one variable cannot designate one "
                                       "plugin among those installed. A hook that needs a plugin's "
                                       "files has to be shipped BY that plugin.", str(path))
                            continue
                        resolved = token
                        for var in HOOK_PLUGIN_ROOT_VARS + HOOK_PROJECT_DIR_VARS:
                            resolved = resolved.replace(var, str(root))
                        # removeprefix, not lstrip: lstrip strips a SET of
                        # characters, so "./.claude/x" lost its dot-directory and
                        # a live script was reported dead. Caught by the negative
                        # control, never by reading the line.
                        rel_tok = resolved[2:] if resolved.startswith("./") else resolved
                        target = Path(rel_tok) if rel_tok.startswith("/") else root / rel_tok
                        if not target.exists():
                            report.add("35-hooks-command", "ERROR",
                                       f"{spot} in '{rel}' runs '{token}', which does not exist. A "
                                       "dead anchor that executes is worse than one that is read.",
                                       str(path))
                        elif target.is_file() and not os.access(target, os.X_OK) \
                                and not any(c in command for c in ("python", "node", "bash", "sh ")):
                            report.add("35-hooks-command", "WARN",
                                       f"{spot} in '{rel}' runs '{token}' directly, but it is not "
                                       "executable (chmod +x).", str(path))
            if event in CONTEXT_INJECTING_HOOK_EVENTS:
                injecting.append(event)

        if injecting:
            report.add("35-hooks-context", "INFO",
                       f"'{rel}' declares hooks on {', '.join(injecting)}: for these events Claude "
                       "Code adds plain-text stdout to the context. Whatever they print is paid in "
                       "tokens on every session - a cost the harness's own estimate leaves out, "
                       "because it prices the declaration and not the output.", str(path))


def check_orphan_references(root: Path, report: Report) -> None:
    """Every reference must be reachable from its own SKILL.md.

    A reference linked only from a sibling reference sits two hops from the
    body, and the second hop is the one Claude skips: it gets read partially,
    or not at all. Vendored skills are not exempt — reachability is not a size
    budget. Non-markdown assets are, since they are consumed as data. A file in
    a references/ subdirectory (archives, retired routes) may instead be routed
    from a top-level reference that SKILL.md links — the router pattern.
    """
    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        refs_dir = skill_dir / "references"
        if not skill_dir.is_dir() or not skill_md.is_file() or not refs_dir.is_dir():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        linked = {(skill_md.parent / link).resolve() for link, _ in iter_relative_links(text)}
        routers: list[tuple[str, set[Path]]] = []
        for router in sorted(refs_dir.glob("*.md")):
            router_rel = router.relative_to(skill_dir).as_posix()
            if not (router.resolve() in linked or router_rel in text or router.name in text):
                continue
            try:
                router_text = router.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            router_links = {(router.parent / link).resolve() for link, _ in iter_relative_links(router_text)}
            routers.append((router_text, router_links))
        for ref in sorted(refs_dir.rglob("*.md")):
            rel = ref.relative_to(skill_dir).as_posix()
            if ref.resolve() in linked or rel in text or ref.name in text:
                continue
            if ref.parent != refs_dir and any(
                ref.resolve() in router_links or ref.name in router_text
                for router_text, router_links in routers
            ):
                continue
            report.add(
                "25-orphan-reference",
                "WARN",
                f"Reference '{skill_dir.name}/{rel}' is neither linked nor named from its SKILL.md — "
                "a reference reachable only from another reference gets read partially or not at all.",
                str(ref),
            )


# One pattern, two checks. Until 2026-09-22 checks 04 and 08b carried two different
# regexes - 08b's missed "Do not use" with a space, which 04 accepted - so the same
# clause was seen on a skill and not on an agent. A detector that disagrees with its
# twin is a detector nobody can act on.
#
# The non-English alternatives are deliberate. A project that has formally exempted
# `11-english-only` writes its descriptions in its own language; refusing to see the
# clause there fires this check on precisely the projects that already declared their
# exception, which is how a criterion becomes unsatisfiable and then ignored. The list
# is not a translation table - it holds the openers actually observed on the fleet.
ANTI_TRIGGER_RE = re.compile(
    r"Do ?n'?o?t use|Never use|Not for:|Out of scope|Anti-?trigger"
    r"|Ne pas utiliser|N'utilisez? pas|Hors périmètre",
    re.IGNORECASE,
)


def looks_like_anti_trigger(case: dict) -> bool:
    label = f"{case.get('id', '')} {case.get('name', '')}".lower()
    if any(token in label for token in EVALS_ANTI_NAME_TOKENS):
        return True
    expectations = case.get("expectations")
    if isinstance(expectations, list):
        for expectation in expectations:
            lowered = str(expectation).lower()
            if any(token in lowered for token in EVALS_ANTI_EXPECTATION_TOKENS):
                return True
    return False


# Wording that states a mechanical fact about the run: whether a tool was called.
# `tool_used` answers it exactly; an llm grader reads the last message and may not
# see the trajectory at all. Measured on this plugin 2026-09-22: a rubric opening
# with "The run must load the `config-auditor` skill" passed 3 runs out of 5 in
# which the skill was never loaded. The judge was not capricious - it was blind.
JUDGED_FACT_RE = re.compile(
    r"must (?:not |NOT )?(?:load|call|invoke|use) ", re.IGNORECASE
)


def _cas_deval(root: Path) -> list[Path]:
    """Case directories `claude plugin eval` would run."""
    base = root / "evals"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.iterdir())
            if p.is_dir() and ((p / "case.yaml").is_file() or (p / "prompt.md").is_file())]


def check_eval_quality(root: Path, report: Report) -> None:
    """Whether a suite can fail - not whether it is well formed.

    Check 26 says the suite parses. These three say it measures something. All
    three come from defects found by hand on this plugin's own suite on
    2026-09-22, each of which check 26 declared sound:

    - a fact entrusted to a judge who cannot see it (the judge passed runs in
      which the skill was never loaded);
    - a case whose every grader is an opinion, so nothing about it is exact;
    - a suite with no fixture, whose cases ask about files that do not exist.
    """
    cas = _cas_deval(root)
    if not cas:
        return
    sans_fixture = 0
    for dossier in cas:
        types: list[str] = []
        rubriques: list[str] = []
        gdir = dossier / "graders"
        if gdir.is_dir():
            for g in sorted(gdir.glob("*.md")):
                try:
                    brut = g.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                # parse_frontmatter returns (fields, end line), not a body: the rubric
                # is what follows, and searching the whole file is equivalent here
                # because no frontmatter key carries that wording.
                fm, _ = parse_frontmatter(brut)
                t = str((fm or {}).get("type", ""))
                types.append(t)
                if t == "llm":
                    rubriques.append(brut)
        if not types:
            continue
        mecanique = [t for t in types if t != "llm" and t != "baseline"]
        fait_juge = any(JUDGED_FACT_RE.search(r) for r in rubriques)
        if fait_juge and not any(t == "tool_used" for t in types):
            report.add(
                "39-eval-judged-fact",
                "WARN",
                f"Case '{dossier.name}': an llm rubric states a fact about the run "
                "(\"must load\" / \"must not call\") and the case carries no `tool_used` "
                "grader. The judge reads the last message, not the trajectory, so it can "
                "pass a run that did the opposite. Add `type: tool_used` with `tool: Skill` "
                "(and `min: 0`, `max: 0`, `arm: both` when absence is the point) and let the "
                "rubric grade only what has to be judged.",
                str(dossier),
            )
        elif not mecanique:
            report.add(
                "39-eval-all-llm",
                "INFO",
                f"Case '{dossier.name}': every grader is an llm judge. Whatever in it can "
                "be counted is being voted on instead - measured on this plugin, a judge "
                "carries a standard deviation near 0.49 where a counter carries 0.000.",
                str(dossier),
            )
        if not (dossier / "case.yaml").is_file():
            sans_fixture += 1
        else:
            try:
                if "scaffold_script" not in (dossier / "case.yaml").read_text(encoding="utf-8"):
                    sans_fixture += 1
            except (OSError, UnicodeDecodeError):
                sans_fixture += 1
    if sans_fixture == len(cas):
        report.add(
            "39-eval-no-fixture",
            "INFO",
            f"None of the {len(cas)} eval case(s) declares a `scaffold_script`, so every "
            "case runs against an empty workspace. A rubric that asks the run to measure a "
            "CLAUDE.md, a skill or a budget is asking about files that are not there, and "
            "fails for a reason that has nothing to do with the skill. Either give the case "
            "a fixture (`case.yaml`, run with --scaffold) or grade doctrine rather than a "
            "measurement.",
            str(root / "evals"),
        )


def check_evals(root: Path, report: Report) -> None:
    """Schema and coverage of each skill's eval suite.

    Until 2026-09-22 a skill with no `evals/` directory was skipped in silence: a
    BAD suite was an error while NO suite was invisible. That is backwards, and it
    is the falsifiability pathology applied to tests - a skill with no evals cannot
    be shown wrong, only trusted. Absence is now reported, once, as a coverage
    figure rather than one finding per skill: a warning that fires sixty times is a
    warning people learn to scroll past.
    """
    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    dirs = [d for d in sorted(skills_dir.iterdir()) if d.is_dir()]
    # Two layouts count as a suite. The house one, `<skill>/evals/evals.json`, and the
    # one `claude plugin eval` actually runs: case directories under the container's
    # `evals/`, each holding `case.yaml` or `prompt.md`. Until 2026-09-22 this check
    # knew only the first, so it reported 0% coverage on a plugin whose suite had just
    # been made executable - it punished the migration it had itself provoked.
    official = root / "evals"
    official_cases = ([p for p in sorted(official.iterdir())
                      if p.is_dir() and ((p / "case.yaml").is_file() or (p / "prompt.md").is_file())]
                     if official.is_dir() else [])
    withed = [d for d in dirs
              if (d / "evals" / "evals.json").is_file()
              or (LAYOUT == "plugin" and len(official_cases) >= EVALS_MIN_COUNT)]
    if dirs:
        pct = len(withed) / len(dirs)
        missing = [d.name for d in dirs if d not in withed]
        detail = (" Without: " + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
                  if missing else "")
        report.add(
            "26-evals-coverage",
            "WARN" if pct < EVALS_COVERAGE_WARN else "INFO",
            f"Eval coverage: {len(withed)}/{len(dirs)} skills carry an eval suite "
            f"({pct:.0%}). A skill with no suite cannot be shown wrong - it can only be "
            f"trusted.{detail}",
            str(skills_dir),
        )
    for skill_dir in dirs:
        path = skill_dir / "evals" / "evals.json"
        if not path.is_file():
            continue
        name = skill_dir.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.add("26-evals-schema", "ERROR", f"evals.json in '{name}' does not parse: {exc}", str(path))
            continue
        if not isinstance(data, dict) or "skill_name" not in data or "evals" not in data:
            report.add(
                "26-evals-schema",
                "ERROR",
                f"evals.json in '{name}' must be an object carrying 'skill_name' and 'evals'.",
                str(path),
            )
            continue
        if data["skill_name"] != name:
            report.add(
                "26-evals-schema",
                "ERROR",
                f"evals.json in '{name}' declares skill_name '{data['skill_name']}'.",
                str(path),
            )
        cases = data["evals"]
        # projection evals/1
        if isinstance(data, dict) and data.get("schema") == "evals/1":
            # Schema evals/1 (2026-09-20): the expectations live under `assertions`.
            # Projected onto the historical keys in memory, so the checks downstream
            # stay unchanged. The file itself is never rewritten.
            cases = [
                c if not isinstance(c, dict) else {
                    **c,
                    "expectations": c.get("expectations")
                    or [a.get("text", "") for a in (c.get("assertions") or []) if isinstance(a, dict)]
                    or [f"selects skill {c.get('expected_skill', '')}"],
                    "expected_output": c.get("expected_output")
                    or ((c.get("assertions") or [{}])[0] or {}).get("text", "")
                    or f"selects skill {c.get('expected_skill', '')}",
                }
                for c in cases
            ]
        if not isinstance(cases, list):
            report.add("26-evals-schema", "ERROR", f"'evals' in '{name}' is not a list.", str(path))
            continue

        ids: list = []
        for position, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                report.add("26-evals-schema", "ERROR", f"Eval #{position} in '{name}' is not an object.", str(path))
                continue
            missing = [key for key in EVALS_REQUIRED_KEYS if key not in case]
            if missing:
                report.add(
                    "26-evals-schema",
                    "ERROR",
                    f"Eval #{position} in '{name}' is missing: {', '.join(missing)}.",
                    str(path),
                )
            expectations = case.get("expectations")
            if "expectations" in case and (
                not isinstance(expectations, list)
                or not expectations
                or not all(isinstance(item, str) for item in expectations)
            ):
                report.add(
                    "26-evals-schema",
                    "ERROR",
                    f"Eval #{position} in '{name}' has an 'expectations' value that is not a non-empty list of strings.",
                    str(path),
                )
            if "id" in case:
                if isinstance(case["id"], bool) or not isinstance(case["id"], (int, str)):
                    report.add(
                        "26-evals-schema",
                        "ERROR",
                        f"Eval #{position} in '{name}' has an 'id' that is neither an integer nor a slug string.",
                        str(path),
                    )
                else:
                    ids.append(case["id"])

        duplicates = sorted({str(i) for i in ids if ids.count(i) > 1})
        if duplicates:
            report.add(
                "26-evals-schema",
                "ERROR",
                f"Duplicate eval id(s) in '{name}': {', '.join(duplicates)}.",
                str(path),
            )
        id_types = {type(i).__name__ for i in ids}
        if len(id_types) > 1:
            report.add(
                "26-evals-id-type",
                "WARN",
                f"evals.json in '{name}' mixes integer and slug ids. Pick one form per file.",
                str(path),
            )
        elif id_types == {"str"}:
            report.add(
                "26-evals-id-type",
                "INFO",
                f"evals.json in '{name}' uses slug string ids where the documented schema says integer. "
                "Accepted — the file is internally consistent.",
                str(path),
            )

        if len(cases) < EVALS_MIN_COUNT:
            report.add(
                "26-evals-count",
                "WARN",
                f"'{name}' has {len(cases)} eval(s) (official minimum {EVALS_MIN_COUNT}).",
                str(path),
            )
        if cases and not any(looks_like_anti_trigger(c) for c in cases if isinstance(c, dict)):
            report.add(
                "26-evals-anti-trigger",
                "WARN",
                f"'{name}' has no anti-trigger eval. Heuristic: an id or name containing "
                f"{', '.join(EVALS_ANTI_NAME_TOKENS)}, or an expectation containing "
                f"{', '.join(EVALS_ANTI_EXPECTATION_TOKENS)}. A suite that only tests triggering "
                "never tests the boundary.",
                str(path),
            )


DIVISION_OWNER_NOISE_RE = re.compile(r"`|\*\*|\(this skill\)|\(the (?:method|facts)\)|➜ See skill:")
DIVISION_SEPARATOR_RE = re.compile(r"^\|[\s\-:|]+\|$")


def division_table_rows(body: str) -> list[tuple[str, str]] | None:
    """Return (concern, owner) rows of the first Division of responsibilities table.

    None when the heading is absent. Concern and owner are normalised: whitespace
    collapsed, backticks, bold markers, `(this skill)` and `➜ See skill:` removed.
    The owner is the first token of the second cell, so `shop-ssr (this skill)` and
    `**shop-ssr**` both resolve to `shop-ssr`.
    """
    heading = DIVISION_HEADING_RE.search(body)
    if not heading:
        return None
    section = body[heading.end():]
    next_heading = re.search(r"^#{1,6}\s+", section, re.MULTILINE)
    if next_heading:
        section = section[: next_heading.start()]
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or DIVISION_SEPARATOR_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in {"concern", ""}:
            continue
        concern = " ".join(DIVISION_OWNER_NOISE_RE.sub("", cells[0]).split())
        owner_cell = DIVISION_OWNER_NOISE_RE.sub("", cells[1]).strip()
        owner = owner_cell.split()[0] if owner_cell else ""
        rows.append((concern, owner))
    return rows


def check_twin_division_tables(root: Path, report: Report, skills: dict[str, dict]) -> None:
    """Mutually anti-triggering skills must both carry a division table that names the twin.

    Twin pairs are detected mechanically: A's description points at B with
    `→ B` and B's points back at A. Pointers naming an agent rather than a
    skill are ignored. Three things are asserted, each a WARN: the heading is
    present on both sides; each table has a row owned by the twin; and the
    concern text of the row naming the pair reads identically on both sides.
    The tables are family-wide, so their other rows may differ. A vendored
    skill cannot carry the heading in its upstream SKILL.md, so its
    references/ overlay counts too.
    """
    bodies: dict[str, str] = {}
    pointers: dict[str, set[str]] = {}
    for name, meta in skills.items():
        try:
            bodies[name] = Path(meta["path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        skill_dir = Path(meta["path"]).parent
        if is_vendored_skill(skill_dir):
            for overlay in sorted((skill_dir / "references").glob("*.md")):
                try:
                    bodies[name] += "\n" + overlay.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
        targets = {m.group(1) for m in POINTER_RE.finditer(meta.get("description", ""))}
        pointers[name] = targets & set(skills)

    pairs = sorted(
        {
            tuple(sorted((name, target)))
            for name, targets in pointers.items()
            for target in targets
            if target != name and name in pointers.get(target, set())
        }
    )
    tables = {name: division_table_rows(body) for name, body in bodies.items()}
    for first, second in pairs:
        for name, twin in ((first, second), (second, first)):
            if name not in bodies:
                continue
            rows = tables.get(name)
            if rows is None:
                report.add(
                    "27-twin-division-table",
                    "WARN",
                    f"Twin pair '{first}' <-> '{second}': '{name}' has no "
                    f"'Division of responsibilities' heading, so only '{twin}' documents the split.",
                    skills[name]["path"],
                )
                continue
            if not any(owner == twin for _, owner in rows):
                report.add(
                    "27-twin-division-row",
                    "WARN",
                    f"Twin pair '{first}' <-> '{second}': the table in '{name}' has no row owned by "
                    f"'{twin}', so a reader of '{name}' never learns what '{twin}' takes.",
                    skills[name]["path"],
                )
        first_rows, second_rows = tables.get(first), tables.get(second)
        if first_rows is None or second_rows is None:
            continue
        first_about_second = {c for c, o in first_rows if o == second}
        second_about_itself = {c for c, o in second_rows if o == second}
        second_about_first = {c for c, o in second_rows if o == first}
        first_about_itself = {c for c, o in first_rows if o == first}
        for reader, subject, seen, claimed in (
            (first, second, first_about_second, second_about_itself),
            (second, first, second_about_first, first_about_itself),
        ):
            if seen and claimed and not (seen & claimed):
                report.add(
                    "27-twin-division-text",
                    "WARN",
                    f"Twin pair '{first}' <-> '{second}': '{reader}' says '{subject}' owns "
                    f"'{sorted(seen)[0][:80]}' but '{subject}' words its own row as "
                    f"'{sorted(claimed)[0][:80]}'. The row naming the pair must read identically on both sides.",
                    skills[reader]["path"],
                )


# How many findings of one check the text report shows before rolling up the
# rest. A report that prints 188 dead anchors is not read: the reader learns
# the number, not the anchors, and pays 188 lines for it. The JSON output and
# the floor still carry every finding - this ceiling is a display decision, not
# a detection one, which is why it belongs here and not in a check.
ROLLUP_AFTER = 5


def print_text_report(report: Report, tout: bool = False) -> None:
    by_sev: dict[str, list[Finding]] = {"ERROR": [], "WARN": [], "INFO": [], "OK": []}
    for f in report.findings:
        by_sev.setdefault(f.severity, []).append(f)
    for sev in ("ERROR", "WARN", "INFO"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        print(f"\n=== {sev} ({len(items)}) ===")
        vus: dict[str, int] = {}
        for f in items:
            vus[f.check] = vus.get(f.check, 0) + 1
            if not tout and vus[f.check] > ROLLUP_AFTER:
                continue
            loc = f" [{f.location}]" if f.location else ""
            print(f"  [{f.check}] {f.message}{loc}")
        if not tout:
            for chk, n in vus.items():
                if n > ROLLUP_AFTER:
                    print(f"  [{chk}] ... and {n - ROLLUP_AFTER} more of the same "
                          f"({n} total). Run with --all, or --json, to see them.")
    counts = report.counts()
    print(
        f"\nExecuted {len(CHECKS)} check groups. "
        f"Summary: {counts['ERROR']} error(s), {counts['WARN']} warning(s)."
    )
    if not report.has_errors() and counts["WARN"] == 0:
        print("All checks passed.")


# ancrage
ANCHOR_SEVERITY = "WARN"   # ratchet: move to "ERROR" once this repository is at zero
ANCHOR_PATH_RE = re.compile(
    r"\b(?:src|server|scripts|electron|docker|app|lib|packages|test|tests)"
    r"/[A-Za-z0-9_./-]+\.[a-z]{2,4}\b"
)
ANCHOR_TEMPLATE_RE = re.compile(
    r"(MyPage|Feature|Example|Foo|Bar|YourThing|<[^>]+>|placeholder|xxx)", re.IGNORECASE
)


def check_skill_anchors(root: Path, report: Report) -> None:
    """Every path a SKILL.md names in its body must resolve to a real file.

    A skill cannot fail loudly: when the code it describes moves, the skill keeps
    loading and keeps saying the same thing. Naming a verifiable path is the only
    way a doctrine can be contradicted by reality. A dead anchor is worse than no
    anchor: the skill is read in full at level 2, then the model looks for a file
    that is gone and falls back to exploration (Glob/Grep) - a fixed cost turned
    into an open one.
    """
    skills_dir = root / SKILLS_DIR
    if not skills_dir.is_dir():
        return
    total = anchored = alive = dead = 0
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        total += 1
        name = skill_md.parent.name
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
        refs = sorted(set(ANCHOR_PATH_RE.findall(body)))
        if not refs:
            continue
        anchored += 1
        for ref in refs:
            if (root / ref).exists():
                alive += 1
            elif (skill_md.parent / ref).exists():
                alive += 1          # ${CLAUDE_SKILL_DIR}/... written relative in the body
            elif ANCHOR_TEMPLATE_RE.search(ref):
                continue            # template / illustrative path
            else:
                dead += 1
                report.add(
                    "28-skill-anchors",
                    ANCHOR_SEVERITY,
                    f"'{name}' names '{ref}', which does not exist. A dead anchor sends the "
                    "model exploring for a file that is gone: fix the path, or drop the claim.",
                    str(skill_md),
                )
    if total:
        report.add(
            "28-skill-anchors",
            "INFO",
            f"Falsifiability: {anchored}/{total} skills name at least one checkable path "
            f"({100 * anchored / total:.0f}%). Live anchors {alive}, dead {dead}. "
            "A skill that names nothing verifiable cannot be proven wrong - it can only rot quietly.",
            str(skills_dir),
        )


# plafond derive
def check_listing_budget_derived(root: Path, report: Report, skills: dict) -> None:
    """The listing ceiling this repository actually has, derived from its settings.

    The harness gives the skill listing a fraction of the context window (1% by
    default), scaled by `skillListingBudgetFraction`. On overflow the listing keeps
    every skill NAME and drops DESCRIPTIONS, least-invoked first - silently. So the
    real ceiling is a per-repository number even though the rule is the same
    everywhere. That is why this check derives it instead of hard-coding it: the
    fraction is a dial the repository owns.
    """
    fraction = LISTING_FRACTION_DEFAULT
    source = "harness default"
    settings = root / CLAUDE_DIR / "settings.json"
    if settings.is_file():
        try:
            value = json.loads(settings.read_text(encoding="utf-8")).get("skillListingBudgetFraction")
            if isinstance(value, (int, float)) and value > 0:
                fraction, source = float(value), "skillListingBudgetFraction"
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    ceiling = int(fraction * CONTEXT_WINDOW_TOKENS * CHARS_PER_TOKEN)
    listed = sum(len(meta.get("description", "")) for meta in skills.values()
                 if isinstance(meta, dict) and meta.get("listed", True))
    pct = 100 * listed / ceiling if ceiling else 0
    severity = "ERROR" if listed > ceiling else ("WARN" if pct > 80 else "INFO")
    report.add(
        "29-listing-budget-derived",
        severity,
        f"Listed skill descriptions: {listed} chars against a derived ceiling of {ceiling} "
        f"({fraction} x {CONTEXT_WINDOW_TOKENS} tokens x {CHARS_PER_TOKEN} chars/token, an optimistic ratio measured at 2.85 on this plugin's own description, so this ceiling is generous and a token figure under it is a floor; from "
        f"{source}) - {pct:.0f}% used. Past the ceiling the listing silently keeps names and "
        f"drops descriptions, least-invoked first. The chars/token ratio is rough: treat this "
        f"as an order of magnitude, and {ALWAYS_LOADED_WARN_CHARS} as the house ratchet.",
        str(root / CLAUDE_DIR / "settings.json"),
    )


def check_plugin_cost(
    root: Path, report: Report, skills: dict[str, dict], agents: dict[str, dict]
) -> None:
    """The always-loaded cost this plugin imposes on EACH consuming project.

    A plugin has no always-loaded budget of its own - no CLAUDE.md, no settings,
    no project context to fill. That does not make its descriptions free: they
    are paid for by every project that installs it, once per project. The budget
    check therefore does not disappear when the container is a plugin, it
    INVERTS. Check 17 asks "what does this project carry?"; check 30 asks "what
    does this plugin add to everyone who installs it?".

    Namespacing is real and reported separately: a plugin skill appears in the
    listing as `plugin-name:skill-name`, so the manifest name plus a colon is
    paid once per listed skill on top of the description.
    """
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        plugin_name = str(json.loads(manifest.read_text(encoding="utf-8")).get("name") or root.name)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        plugin_name = root.name

    hidden = listing_hidden_skills(root, skills)
    listed = {n: sk for n, sk in skills.items() if n not in hidden}
    skill_chars = sum(len(sk.get("description", "")) for sk in listed.values())
    agent_chars = sum(len(a.get("description", "")) for a in agents.values())
    total = skill_chars + agent_chars
    namespacing = sum(len(plugin_name) + 1 for _ in listed)

    detail = ""
    if hidden:
        suppressed = sum(len(skills[n].get("description", "")) for n in hidden)
        detail = (
            f" [{len(hidden)} skill(s) withheld from the listing: {suppressed} chars"
            " not paid by consumers]"
        )
    message = (
        f"Plugin `{plugin_name}` adds {total} chars to the always-loaded context of "
        f"EACH consuming project ({len(listed)} skill description(s) {skill_chars} + "
        f"{len(agents)} agent description(s) {agent_chars}), plus {namespacing} chars of "
        f"`{plugin_name}:` namespacing in the skill listing. This cost is NOT negotiable downstream: `skillOverrides` does not reach a plugin skill (measured 2026-09-22), so a consuming project can only disable the whole plugin.{detail}"
    )
    if total > PLUGIN_COST_WARN_CHARS:
        report.add(
            "30-plugin-cost",
            "WARN",
            f"{message} Above {PLUGIN_COST_WARN_CHARS} chars: every consumer pays this on "
            "every turn. Trim the descriptions or split the plugin.",
            str(manifest),
        )
    else:
        report.add("30-plugin-cost", "INFO", message, str(manifest))


def check_skill_names(root: Path, report: Report, skills: dict[str, dict]) -> None:
    """Shape and reserved words in `name`, per the Agent Skills spec.

    A non-conformant name keeps working locally, which is why it survives: nothing
    fails until the skill is packaged or published. So the severity follows the
    container. In a plugin the name blocks distribution - ERROR. In a project it is
    a latent problem that surfaces the day the skill is extracted - WARN, because a
    ratchet that cries on work nobody is doing today is a ratchet people learn to
    ignore.
    """
    skills_dir = root / SKILLS_DIR
    hard = LAYOUT == "plugin"
    for name in sorted(skills):
        loc = str(skills_dir / name / "SKILL.md")
        declared = str(skills[name].get("name") or name)
        if not SKILL_NAME_RE.match(declared):
            report.add("32-skill-name-shape", "ERROR" if hard else "WARN",
                       f"Skill name `{declared}` is not lowercase letters, digits and single "
                       "hyphens (agentskills.io/specification). The spec rejects it when the "
                       "skill is packaged.", loc)
        if len(declared) > SKILL_NAME_MAX_CHARS:
            report.add("32-skill-name-shape", "ERROR" if hard else "WARN",
                       f"Skill name `{declared}` is {len(declared)} chars (max "
                       f"{SKILL_NAME_MAX_CHARS}).", loc)
        # The Agent Skills specification enumerates the `name` constraints in full -
        # 1-64 characters, lowercase alphanumerics and hyphens, no leading, trailing
        # or consecutive hyphen, and it must match the parent directory. Verified
        # 2026-09-22 at agentskills.io/specification: THERE IS NO RESERVED WORD.
        #
        # This check used to raise an ERROR saying "the spec forbids them", and it
        # fired on a third party's plugin. A rule invented and attributed to a
        # standard is worse than no rule: the reader learns it, and learns it wrong.
        # Kept as INFO, sourced honestly, because the concern is real - a name
        # carrying a vendor's is a poor name - but it is an opinion, not a rule.
        hit = [t for t in RESERVED_NAME_TOKENS if t in declared.lower()]
        if hit:
            report.add(
                "32-skill-name-reserved", "INFO",
                f"Skill name `{declared}` contains `{', '.join(hit)}`. No specification "
                "forbids this - checked against agentskills.io/specification, which lists "
                "the `name` constraints in full. It is an opinion: a name carrying a "
                "vendor's says who made the skill rather than when to use it.",
                loc)


# --- Confusable descriptions -------------------------------------------------
# TF-IDF over the descriptions of the skills that actually compete, cosine per
# pair. Stdlib only. A withheld skill is excluded: it is not in the listing, so it
# cannot steal an activation, and counting it manufactures phantom pairs.
_OVERLAP_STOP = set("""
the a an and or of to for in on with when use used using this that it its not no
don dont skill skills agent agents project file files code claude anthropic
""".split())


def _overlap_tokens(text: str) -> list[str]:
    import unicodedata
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")
    return [w for w in re.split(r"[^a-z0-9]+", text) if len(w) >= 3 and w not in _OVERLAP_STOP]


def check_description_overlap(root: Path, report: Report, skills: dict[str, dict]) -> None:
    """Descriptions close enough to compete for the same request.

    Triggering is a competition between the descriptions listed on the same turn.
    Two close descriptions do not merely cost tokens - they steal each other's
    activations, and neither owner can see it from their own file. This is the one
    defect that is invisible skill by skill and only exists in the set.
    """
    import math
    from collections import Counter

    hidden = listing_hidden_skills(root, skills)
    listed = {n: (sk.get("description") or "") for n, sk in skills.items()
              if n not in hidden and (sk.get("description") or "").strip()}
    if len(listed) < 2:
        report.add("33-description-overlap", "INFO",
                   f"{len(listed)} listed description(s): nothing to compete with.",
                   str(root / SKILLS_DIR))
        return

    names = sorted(listed)
    tfs = [Counter(_overlap_tokens(listed[n])) for n in names]
    df: Counter = Counter()
    for tf in tfs:
        df.update(tf.keys())
    n = len(names)
    idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
    vecs = []
    for tf in tfs:
        v = {w: (1 + math.log(c)) * idf[w] for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norm for w, x in v.items()})

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = vecs[i], vecs[j]
            if len(a) > len(b):
                a, b = b, a
            score = sum(x * b.get(w, 0.0) for w, x in a.items())
            if score >= OVERLAP_THRESHOLD:
                pairs.append((score, names[i], names[j]))
    pairs.sort(reverse=True)

    for score, x, y in pairs:
        report.add("33-description-overlap", "WARN",
                   f"`{x}` and `{y}` overlap at {score:.2f} (threshold "
                   f"{OVERLAP_THRESHOLD:.2f}). They compete for the same requests: give each an "
                   "anti-trigger naming the other, or merge them.",
                   str(root / SKILLS_DIR / x / "SKILL.md"))
    report.add("33-description-overlap", "INFO",
               f"{len(pairs)} confusable pair(s) among {n} listed description(s) at threshold "
               f"{OVERLAP_THRESHOLD:.2f}. Scored on the listing only - a withheld skill cannot "
               f"steal an activation ({len(hidden)} excluded).", str(root / SKILLS_DIR))


def known_check_ids() -> set[str]:
    """Every finding id this script can emit, read from its own source.

    Derived rather than listed, so the vocabulary cannot drift from the code that
    uses it: a hand-maintained list would be one more thing to forget to update,
    and it would fail in the direction that hurts - silently accepting an
    exemption for a check that no longer exists.
    """
    try:
        src = Path(__file__).read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(re.findall(r'"(\d{2}-[a-z0-9-]+)"', src))


def check_project_overlay(root: Path, report: Report, local: dict) -> None:
    """The consuming project's overlay, audited by the plugin that reads it.

    The plugin cannot hold a project's decisions - it is the same bytes in every
    project that installs it. What it CAN hold is the schema and the detector. So
    the record lives in the project and the shape of the record is enforced here.

    An exemption without a reason is a decision nobody can review; an exemption
    without a date is a decision nobody can age out; an exemption whose path no
    longer exists is a claim about a file that is gone - the same defect as a dead
    anchor, caught by the same kind of check.
    """
    path = root / STATE_DIR / "audit.local.json"
    if "__error__" in local:
        report.add("31-overlay-parse", "ERROR",
                   "audit.local.json is unreadable or is not valid JSON: no exemption is "
                   "applied, so unrelated checks below may fire.", str(path))
        return
    if not path.is_file():
        report.add("31-overlay", "INFO",
                   "No .claude/audit.local.json: this project grants no exemption. "
                   "Absent is a valid state - do not go looking for one.", str(path))
        return

    raw = local.get("exemptions")
    if raw is None:
        # An overlay that carries only `thresholds` is legitimate since 0.4.0: a
        # project may hold its own doctrine number without granting any exemption.
        # Demanding both keys would make the file a form to fill rather than a place
        # to record what this project decided.
        if local.get("thresholds"):
            return
        report.add("31-overlay-schema", "ERROR",
                   "audit.local.json has neither `exemptions` nor `thresholds`, so it "
                   'does nothing. Schema: {"exemptions": [{"check", "path", "reason", '
                   '"date"}], "thresholds": {"<NAME>": {"value", "reason", "date"}}}.',
                   str(path))
        return
    if not isinstance(raw, list):
        report.add("31-overlay-schema", "ERROR",
                   "`exemptions` must be a list of objects.", str(path))
        return

    valid = known_check_ids()
    stale = 0
    for i, e in enumerate(raw):
        where = f"exemptions[{i}]"
        if not isinstance(e, dict):
            report.add("31-overlay-schema", "ERROR", f"{where} is not an object.", str(path))
            continue
        for key in ("check", "path", "reason", "date"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                report.add(
                    "31-overlay-schema", "ERROR",
                    f"{where} has no `{key}`. An exemption without a reason is a decision "
                    "nobody can review; without a date, one nobody can age out.", str(path))
        chk, pth = e.get("check"), e.get("path")
        if isinstance(chk, str) and chk in CHECK_ID_ALIASES:
            report.add("31-overlay-alias", "INFO",
                       f"{where} names `{chk}`, renamed to `{CHECK_ID_ALIASES[chk]}`. The old id "
                       "still works and always will; update it when convenient.", str(path))
            chk = CHECK_ID_ALIASES[chk]
        if isinstance(chk, str) and valid and chk not in valid:
            report.add("31-overlay-unknown-check", "WARN",
                       f"{where} exempts `{chk}`, which this audit never emits. Stale entry, "
                       "or a typo that makes the exemption silently inert.", str(path))
        sev = e.get("severity")
        if sev is not None and (not isinstance(sev, str) or sev.upper() not in DOWNGRADE_TO):
            report.add("31-overlay-schema", "WARN",
                       f"{where} has severity `{sev}`, which is neither WARN nor INFO. An "
                       "exemption may lower a finding, never raise or invent one; this one "
                       "is ignored and the finding is dropped outright.", str(path))
        if isinstance(chk, str) and chk in UNEXEMPTABLE:
            report.add("31-overlay-schema", "WARN",
                       f"{where} exempts `{chk}`, which audits the overlay or the ratchet "
                       "itself. It is ignored: a valve that can disconnect its own gauge is "
                       "not a valve.", str(path))
        if isinstance(e.get("date"), str) and not ISO_DATE_RE.match(e["date"]):
            report.add("31-overlay-schema", "WARN",
                       f"{where} date `{e['date']}` is not YYYY-MM-DD.", str(path))
        if isinstance(pth, str) and pth:
            if not ((root / SKILLS_DIR / pth).exists() or (root / pth).exists()):
                stale += 1
                report.add("31-overlay-stale", "WARN",
                           f"{where} exempts `{pth}`, which no longer exists. A stale exemption "
                           "is a dead anchor in the overlay: drop it.", str(path))

    dates = sorted(e["date"] for e in raw
                   if isinstance(e, dict) and isinstance(e.get("date"), str)
                   and ISO_DATE_RE.match(e["date"]))
    oldest = f", oldest {dates[0]}" if dates else ""
    report.add("31-overlay", "INFO",
               f"Project overlay: {len(raw)} exemption(s){oldest}, {stale} stale. "
               "Each one is a check this project decided not to answer - review them as a "
               "list, not one at a time.", str(path))


def audit_sha() -> str:
    """Short sha of this script. The instrument's identity - see check 34."""
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:8]
    except OSError:
        return "unknown"


def floor_path(root: Path) -> Path:
    return root / STATE_DIR / "audit" / "floor.json"


def set_floor(root: Path, report: Report, layout: str) -> Path | None:
    """Freeze the current counts as the floor this configuration may not fall below."""
    counts = report.counts()
    # The floor carries the check ids, not just the counts. They were the only thing
    # the run-history file held that this one did not - and a committed floor beats a
    # jsonl series on every other axis: `git log -p` on this file is the same
    # trajectory, timestamped to the second, with an author and a reason. The measure
    # belongs to the script, the judgement to the commit message.
    data = {
        "date": _date.today().isoformat(),
        "layout": layout,
        "audit_sha": audit_sha(),
        "errors": counts.get("ERROR", 0),
        "warnings": counts.get("WARN", 0),
        "error_ids": sorted({f.check for f in report.findings if f.severity == "ERROR"}),
        "warning_ids": sorted({f.check for f in report.findings if f.severity == "WARN"}),
    }
    out = floor_path(root)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return None
    return out


def check_floor(root: Path, report: Report) -> int:
    """Compare against the frozen floor. Returns an exit code contribution.

    This is what turns a report into a ratchet. A measurement with no floor is a
    measurement people learn to ignore: the numbers move, nobody is accountable for
    the direction, and six months later the configuration has drifted with every
    individual step looking reasonable.

    The floor records the sha of this script, and the comparison REFUSES to run
    across a change of instrument. A count taken with a different auditor is not a
    worse or better state - it is a different measurement, and comparing the two
    silently is how an instrument change gets read as progress.
    """
    path = floor_path(root)
    if not path.is_file():
        report.add("34-floor", "INFO",
                   "No floor recorded. `--set-floor` freezes the current counts; until then "
                   "nothing stops the configuration from drifting upward.", str(path))
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        report.add("34-floor", "ERROR", "floor.json is unreadable or not valid JSON.", str(path))
        return 1
    counts = report.counts()
    err, warn = counts.get("ERROR", 0), counts.get("WARN", 0)
    f_err, f_warn = int(data.get("errors", 0)), int(data.get("warnings", 0))
    if data.get("audit_sha") != audit_sha():
        report.add("34-floor", "WARN",
                   f"Floor was set with audit.py `{data.get('audit_sha')}`, this run is "
                   f"`{audit_sha()}`. Counts across two instruments are not comparable, "
                   f"so nothing is compared: now {err} error(s), {warn} warning(s), the "
                   f"floor said {f_err}/{f_warn}. Read them side by side, then re-set "
                   f"deliberately: `--set-floor`. A plugin release only reaches here when "
                   f"it changed the auditor itself - most releases do not.", str(path))
        return 0
    if err > f_err or warn > f_warn:
        report.add("34-floor", "ERROR",
                   f"Regression against the floor of {data.get('date')}: {err} error(s) / "
                   f"{warn} warning(s) against {f_err}/{f_warn}. Fix it, or raise the floor "
                   "on purpose and say why.", str(path))
        return 1
    if err < f_err or warn < f_warn:
        report.add("34-floor", "INFO",
                   f"Below the floor of {data.get('date')} ({err}/{warn} against "
                   f"{f_err}/{f_warn}). Lower it with `--set-floor` so the gain is kept.",
                   str(path))
    else:
        report.add("34-floor", "INFO",
                   f"At the floor of {data.get('date')} ({f_err} error(s), {f_warn} warning(s)).",
                   str(path))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Audit Claude configuration.")
    parser.add_argument("--root", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--all", action="store_true",
                        help="Show every finding; by default a check that fires more than "
                             f"{ROLLUP_AFTER} times is rolled up")
    parser.add_argument(
        "--layout",
        choices=("auto", "project", "plugin", "library", "none"),
        default="auto",
        help="Container being audited (default: auto, from .claude-plugin/plugin.json)",
    )
    parser.add_argument(
        "--set-floor",
        action="store_true",
        help="Freeze the current counts in .claude/audit/floor.json as the ratchet",
    )
    parser.add_argument(
        "--check-floor",
        action="store_true",
        help="Fail when the counts rose above the recorded floor (for CI)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    layout = detect_layout(root) if args.layout == "auto" else args.layout
    apply_layout(root, layout)

    global ENGLISH_ONLY_EXEMPT
    _local = load_local_config(root)
    ENGLISH_ONLY_EXEMPT = exemption_paths(_local, "11-english-only")
    report = Report()
    # Before any check runs: a moved threshold must move for EVERY check that
    # reads it, not only for the ones that happen to run afterwards.
    apply_thresholds(_local, report)
    detail = {
        "library": "skills kept at the repository root, no project and no manifest: "
                   "their content is audited, and where they would load is said.",
        "none": "no Claude Code configuration here - no CLAUDE.md, no .claude/, no "
                "skills/, no manifest. Nothing to audit, and nothing is missing.",
    }
    if layout in detail:
        msg = f"Layout `{layout}`{'' if args.layout != 'auto' else ' (detected)'}: {detail[layout]}"
    else:
        msg = (f"Layout `{layout}`{'' if args.layout != 'auto' else ' (detected)'}: "
               f"skills at `{SKILLS_DIR}/`, agents at `{AGENTS_DIR}/`."
               + ("" if layout == "project" else
                  f" {len(PROJECT_ONLY)} project-only check(s) skipped - a plugin has no "
                  "CLAUDE.md, settings, rules or skills index.")
               + (" No manifest: the plugin is named after its folder, which the manifest "
                  "is optional for." if layout == "plugin"
                  and not (root / ".claude-plugin" / "plugin.json").is_file() else ""))
    report.add("00-layout", "INFO", msg, str(root))

    def run(fn, *a):
        """Dispatch, skipping checks whose subject the current container lacks."""
        name = fn.__name__
        if layout != "project" and name in PROJECT_ONLY:
            return None
        if layout != "plugin" and name in PLUGIN_ONLY:
            return None
        # A marketplace holds a catalogue. Everything that inspects a configuration -
        # skills, agents, rules, references, budget - has no subject here, and running
        # it reports the auditor's own ignorance as the repository's defect.
        if layout == "marketplace" and name not in MARKETPLACE_CHECKS:
            return None
        if layout == "library" and name not in LIBRARY_CHECKS:
            return None
        if layout == "none" and name not in NONE_CHECKS:
            return None
        # Every check goes through here. Until 2026-09-22 half of them were called
        # directly, so PROJECT_ONLY and PLUGIN_ONLY governed only the half that
        # happened to be wrapped - a dispatch that decides for some of its subjects
        # is not a dispatch, and the hole was invisible because the two lists were
        # written for checks that were wrapped.
        return fn(*a)

    run(check_claude_md, root, report)
    skills = check_skills(root, report)
    agents = check_agents(root, report) if layout not in ("library", "none") else {}
    run(check_agent_descriptions, report, agents)
    run(check_cross_refs, root, report, skills, agents)
    run(check_english_only, root, report)
    run(check_no_code_comments_in_skills, root, report)
    run(check_no_global_scripts, root, report)
    run(check_rules, root, report)
    run(check_skill_index, root, report, skills)
    run(check_reference_sizes, root, report)
    run(check_always_loaded_budget, root, report, skills, agents)
    run(check_unreadable, root, report)
    run(check_see_skill_targets, root, report, skills)
    run(check_foreign_skill_mentions, root, report, skills)
    run(check_documented_flags, root, report)
    run(check_frontmatter_quoting, root, report)
    run(check_all_relative_links, root, report)
    run(check_rule_globs, root, report)
    run(check_agent_frontmatter_validity, root, report, skills)
    run(check_settings_scope, root, report)
    run(check_hooks, root, report)
    run(check_orphan_references, root, report)
    run(check_evals, root, report)
    run(check_eval_quality, root, report)
    run(check_twin_division_tables, root, report, skills)

    run(check_skill_anchors, root, report)
    run(check_listing_budget_derived, root, report, skills)
    run(check_plugin_cost, root, report, skills, agents)
    run(check_project_overlay, root, report, _local)
    run(check_skill_names, root, report, skills)
    run(check_description_overlap, root, report, skills)
    run(check_unloadable_skills, root, report)

    apply_overlay(report, _local, root)
    floor_rc = check_floor(root, report) if args.check_floor else 0

    if args.json:
        out = {
            "checks_executed": len(CHECKS),
            "layout": layout,
            "audit_sha": audit_sha(),
            "counts": report.counts(),
            "findings": [asdict(f) for f in report.findings],
        }
        print(json.dumps(out, indent=2))
    else:
        print_text_report(report, tout=args.all)

    if args.set_floor:
        written = set_floor(root, report, layout)
        print(f"\nFloor set in {written}" if written
              else "\nCould not write the floor (unwritable path).", file=sys.stderr)

    return 1 if (report.has_errors() or floor_rc) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
