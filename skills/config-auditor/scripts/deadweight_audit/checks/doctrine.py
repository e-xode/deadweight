"""A skill that copies the doctrine of this plugin instead of pointing at it."""
from __future__ import annotations

import re

from ..context import AuditContext
from ..repo import readable_files
from ..report import Report
from ..vocabulary.doctrine import DOCTRINE_CODE_TERMS, DOCTRINE_REFERENCE_NAMES


# A reference copied into a project from this plugin, or rewritten from the same
# documentation, overlaps it far more than a record of the project's own decisions.
# Until 0.21.0 a term counted when it appeared ANYWHERE in the references' 247,000
# characters, and short terms (`id`, `paths`) always did: 3 of 5 findings right on 3,013
# public reference files. Counted as exact code terms of the references (frozen in
# vocabulary/doctrine.py), 4 of 4 at this threshold, labelled by hand, 2026-09-30.
DOCTRINE_COPY_OVERLAP = 0.50


DOCTRINE_COPY_MIN_TERMS = 15


def check_doctrine_copy(ctx: AuditContext, report: Report) -> None:
    """A project skill that carries this plugin's doctrine instead of pointing to it.

    The plugin's references are checked against the documentation at each release; a
    copy in a project is checked by nothing, and diverges without a sign. Worse, the
    model reads whichever of the two the listing leads it to. What a project keeps is
    its decisions and their reasons - the method stays here. Two signals, both cheap:
    a file named like one of these references, or a file whose code terms are mostly
    found in them. Neither proves a copy: a file ABOUT Claude Code configuration shares
    the vocabulary by nature, so this is a notice, and an overlay exemption answers it.
    """
    root = ctx.root
    if ctx.layout != "project":
        return
    skills_dir = root / ctx.skills_dir
    if not skills_dir.is_dir():
        return
    for f in readable_files(skills_dir.glob("*/references/**/*.md")):
        try:
            terms = set(re.findall(r"`([^`\n]{2,60})`", f.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
        share = sum(1 for t in terms if t in DOCTRINE_CODE_TERMS) / len(terms) if terms else 0.0
        # The name alone only for names no other subject uses: `skill-anatomy.md` is about
        # this plugin's subject, `antipatterns.md` or `audit-checklist.md` can be about
        # anything (a React review skill's antipatterns.md fired, audit externe 2026-10-08).
        # A copy under a generic name is caught by its terms once it holds
        # DOCTRINE_COPY_MIN_TERMS of them; a fragment of 25 lines may hold fewer.
        # `skill-runtime-mechanisms.md` names this subject as plainly as an anatomy does
        # (external audit 3, g8-01); `semantic-layer.md` and `runtime-data.md` are data
        # vocabulary too, and stay with the generic names.
        same_name = f.name in DOCTRINE_REFERENCE_NAMES and (
            f.name.endswith("-anatomy.md") or f.name == "skill-runtime-mechanisms.md")
        if not (same_name or (len(terms) >= DOCTRINE_COPY_MIN_TERMS and share >= DOCTRINE_COPY_OVERLAP)):
            continue
        why = (f"is named like this plugin's references/{f.name}" if same_name else
               f"shares {share:.0%} of its {len(terms)} code terms with this plugin's references")
        report.add("46-doctrine-copy", "NOTICE",
                   f"'{f.relative_to(root)}' {why}. If it restates how Claude Code works, it "
                   "is a second copy that nothing keeps current: keep only this project's "
                   "decisions and their reasons, and point to deadweight:config-auditor for "
                   "the rest.", str(f))
