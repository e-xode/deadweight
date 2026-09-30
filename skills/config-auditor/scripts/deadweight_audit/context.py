"""The state of one audit, passed to every check."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .limits import Limits


# Where the AUDITED configuration lives changes with the container (AuditContext.claude_dir).
# Where the audit's OWN bookkeeping lives does not: the overlay, the floor and the
# run history are repository state, and `.claude/` is their home in a project and
# in a plugin repository alike. Conflating the two put `audit/floor.json` at the
# root of a plugin on 2026-09-22.
STATE_DIR = ".claude"


@dataclass
class AuditContext:
    """What one audit knows about the repository it audits, passed to every check.

    Until 0.21.0 these were module globals rebound in flight - by `apply_layout` for
    the second pass of a dual-role repository, by `main` for the profile, through
    `globals()` for an overridden threshold. A global rebound in one module is not
    seen by another that imported it, so the state had to become an object before
    the script could become a package.
    """
    root: Path
    layout: str = "project"
    claude_dir: str = ".claude"
    skills_dir: str = ".claude/skills"
    agents_dir: str = ".claude/agents"
    # "house" when the overlay opts into this plugin's conventions (see house()).
    profile: str = "doc"
    # A project that is also a skills library - N skills at its root, meant to be copied.
    dual_library: bool = False
    local: dict = field(default_factory=dict)
    # An InstructionsLoaded log given with --runtime (checks/runtime.py), or None.
    runtime: Path | None = None
    limits: Limits = field(default_factory=Limits)
