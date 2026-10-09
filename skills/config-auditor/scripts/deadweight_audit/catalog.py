"""What this auditor checks, and the check ids it answers to.

Check ids are a compatibility surface: a consuming project names them in its overlay."""
from __future__ import annotations

import re

from .identity import instrument_files


# CHECK IDS ARE A PUBLIC API. A consuming project names them in its
# `.claude/audit.local.json`, so renaming one silently turns that project's
# exemption inert - and the audit then blames the project for an id this script
# changed. Ids are therefore never renamed: an id that must change is added here,
# old -> new, and keeps working. Never remove an entry.
CHECK_ID_ALIASES: dict[str, str] = {
    # Never emitted: the sha mismatch has always been reported as `34-floor`. Listed as
    # unexemptable until 0.23.0, so an overlay may name it (audit externe 2026-10-08).
    "34-audit-sha": "34-floor",
}


# Retired checks, same contract seen from the other side: an exemption a project wrote
# for a check this script no longer runs is reported as harmless and removable, not as
# a typo (31-overlay-unknown-check, a WARN that would raise the project's floor for a
# change made here). Never remove an entry.
RETIRED_CHECK_IDS: dict[str, str] = {
    # 0.22.0, 2026-10-02. The table it required had no measured effect on selection
    # (2026-09-27, 1,152 runs per model), and 27-twin-division-text demanded the same
    # row word for word in two files - the duplication core rule 5 and
    # 59-semantic-duplicate tell a project to remove.
    "27-twin-division-table": "0.22.0",
    "27-twin-division-row": "0.22.0",
    "27-twin-division-text": "0.22.0",
}


# Group descriptions, not ids: known_check_ids() reads every quoted "NN-name" in the package
# as an id the audit emits, so a family written that way here passed the exemption typo guard
# (31-overlay-unknown-check) while excusing nothing - 39-eval-quality, 42-permissions, 43-mcp
# and 44-plugin-manifest did until 0.23.0.
CHECKS = (
    "dangling symbolic links",
    "instructions against the repository: stale commands, dead anchors, file trees, verification",
    "security: broad allows, secrets, remote execution, MCP pinning and transport, hidden unicode",
    "hooks in skill and agent frontmatter",
    "skills in .agents/ that Claude Code never loads",
    "plugin variables in project skills",
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
    "eval quality (39-eval-*)",
    "40-skill-not-loaded",
    "permission rules (42-permissions-*)",
    "MCP configuration (43-mcp-*)",
    "plugin manifest (44-plugin-*)",
    "45-command-shadowed",
    "46-doctrine-copy",
    "other agents: AGENTS.md variants, Cursor rules, Copilot instruction files",
    "runtime: instruction files never loaded, or loaded unscoped, in an InstructionsLoaded log",
)


# The security family has its own grade, independent of the profile: a risk is not a
# house convention, and a documented pitfall of this kind is not a mere NOTICE.
SECURITY_GRADE = {"high": "ERROR", "medium": "WARN", "low": "NOTICE"}


SECURITY_CHECKS_EXTRA = ("43-mcp-secret", "43-mcp-approval")   # older ids of the same family



def known_check_ids() -> set[str]:
    """Every finding id this script can emit, read from its own source.

    Derived rather than listed, so the vocabulary cannot drift from the code that
    uses it: a hand-maintained list would be one more thing to forget to update,
    and it would fail in the direction that hurts - silently accepting an
    exemption for a check that no longer exists.
    """
    try:
        src = "".join(f.read_text(encoding="utf-8") for f in instrument_files())
    except OSError:
        return set()
    return set(re.findall(r'"(\d{2}-[a-z0-9-]+)"', src))
