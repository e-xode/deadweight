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
# The auditor is the `deadweight_audit` package beside this file; this file is its entry
# point, kept at the path the README, the skill and consumers' CI already call.
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import deadweight_audit  # noqa: E402
from deadweight_audit.cli import main  # noqa: E402

# Scripts that load this file as a module read the auditor's names on it - the vocabulary
# lists above all. They stay reachable here, whichever module now holds them.
for _mod in pkgutil.walk_packages(deadweight_audit.__path__, "deadweight_audit."):
    globals().update({k: v for k, v in vars(importlib.import_module(_mod.name)).items()
                      if not k.startswith("__")})

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
