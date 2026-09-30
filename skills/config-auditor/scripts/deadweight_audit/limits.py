"""Thresholds: the numbers every check compares against, and which of them a project may move."""
from __future__ import annotations

import re
from dataclasses import dataclass


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
# A file that never loads leaves no line in an InstructionsLoaded log: absence is the only
# signal, and a few sessions prove nothing by it. House number, not measured yet.
RUNTIME_MIN_SESSIONS = 5
CHARS_PER_TOKEN = 4                   # optimistic on purpose: token figures are floors


@dataclass
class Limits:
    """The doctrine thresholds one audit runs with: the defaults, moved by the overlay.

    Field names are the overlay's keys (`thresholds` in `.claude/audit.local.json`),
    so they keep the constants' spelling.
    """
    CLAUDE_MD_MAX_BYTES: int = CLAUDE_MD_MAX_BYTES
    CLAUDE_MD_MAX_LINES: int = CLAUDE_MD_MAX_LINES
    SKILL_MD_ERROR_BYTES: int = SKILL_MD_ERROR_BYTES
    REFERENCE_WARN_LINES: int = REFERENCE_WARN_LINES
    REFERENCE_TOC_LINES: int = REFERENCE_TOC_LINES
    DESCRIPTION_MIN_CHARS: int = DESCRIPTION_MIN_CHARS
    AGENT_DESCRIPTION_MAX_CHARS: int = AGENT_DESCRIPTION_MAX_CHARS
    ALWAYS_LOADED_WARN_CHARS: int = ALWAYS_LOADED_WARN_CHARS
    ALWAYS_LOADED_ERROR_CHARS: int = ALWAYS_LOADED_ERROR_CHARS
    SKILL_DESC_AGGREGATE_WARN_CHARS: int = SKILL_DESC_AGGREGATE_WARN_CHARS
    PLUGIN_COST_WARN_CHARS: int = PLUGIN_COST_WARN_CHARS
    OVERLAP_THRESHOLD: float = OVERLAP_THRESHOLD
    EVALS_COVERAGE_WARN: float = EVALS_COVERAGE_WARN
    EVALS_MIN_COUNT: int = EVALS_MIN_COUNT
