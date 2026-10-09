"""One declared language, and no code comments in prose files."""
from __future__ import annotations

import re
from pathlib import Path

from ..context import AuditContext
from ..parsing.markdown import strip_code_fences
from ..repo import readable_files
from ..report import Report, house, house_note


# i18n-data: start — French on purpose, this is the check's own dictionary
FRENCH_HEURISTIC_WORDS = {
    "avec", "dans", "cette", "celui", "celle", "ceux", "celles",
    "vous", "nous", "etre", "tres", "donc", "ainsi",
    "depuis", "toujours", "jamais", "ensuite", "alors", "parce", "lorsque",
    "fichier", "exemple", "doit", "peut", "faut", "selon", "pour",
}


# i18n-data: end
# DISTINCT words of the list, not occurrences. Counted per occurrence, three English
# sentences opening with "Pour" (the verb) were reported as French (audit externe
# 2026-10-08). Counted distinct, `pour` adds 1 at most, so it stays in the list: taking it
# out as well let short French files through (audit externe 3, g4-04).
FRENCH_HEURISTIC_THRESHOLD = 3


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
# In a skill, only a FRENCH marking skips the file: the heuristic finds French only, and
# `ship-it.md` or `use-de.md` are English names, not Italian or German (audit externe 3, g4-05).
FRENCH_MARKED_RE = re.compile(r"(?:[-_.]fr\.[a-z]+$)|(?:/fr/)")


def check_english_only(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    targets: list[Path] = []
    skills_dir = root / ctx.skills_dir
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
            for p in readable_files(list(skill.rglob("*.md")) + list(skill.rglob("*.py"))
                            + list(skill.rglob("*.sh"))):
                if p.name.endswith(ENGLISH_ONLY_SUFFIX_EXEMPT):
                    continue
                # The locale marking src/ already honoured: `guide-fr.md` or `fr/guide.md`
                # in a skill declares its language as plainly as `guide.fr.md`. Prose only,
                # and read below the skill folder: `run-it.py` is not Italian.
                if p.suffix == ".md" and FRENCH_MARKED_RE.search("/" + p.relative_to(skill).as_posix()):
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
                # Exemptions are NOT consulted here: apply_overlay() drops the
                # finding, as for every other check. Skipping the file upstream (the
                # 0.2-0.10.0 behaviour) hid which exemption served, so each one looked
                # idle to `31-overlay-unused`, and a `severity` downgrade was ignored
                # for this check alone. One place applies exemptions, or none knows.
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
        hits = len(set(words) & FRENCH_HEURISTIC_WORDS)
        if hits >= FRENCH_HEURISTIC_THRESHOLD:
            report.add(
                "11-english-only",
                house(ctx),
                f"File appears to contain French content ({hits} distinct heuristic words)."
                + house_note("English only", "set the language explicitly; nothing requires English"),
                str(path),
            )


def check_no_code_comments_in_skills(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    if not skills_dir.is_dir():
        return
    for skill_md in readable_files(skills_dir.glob("*/SKILL.md")):
        # Not valid UTF-8: check_skills says so for the file; this check still reads the rest.
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        stripped = strip_code_fences(text, indented=True)
        if re.search(r"^\s*//", stripped, re.MULTILINE):
            report.add(
                "12-no-code-comments",
                house(ctx),
                f"SKILL.md in '{skill_md.parent.name}' contains a // comment outside a code block."
                + house_note("prose only, no code comments", "nothing on this"),
                str(skill_md),
            )
