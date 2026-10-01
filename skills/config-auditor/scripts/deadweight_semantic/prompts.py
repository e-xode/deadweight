"""The request sent to the model: the families asked for, the files, and the answer's shape."""
from __future__ import annotations

from .collect import Request
from .families import FAMILIES, NOT_DEFECTS

SYSTEM = """You review the instruction files of a software project's Claude Code configuration, as a careful \
human reader would, and report only defects from the closed list you are given. You never judge whether a rule \
is useful or beneficial. Every finding must quote its evidence VERBATIM from the files shown - copy the exact \
characters, do not paraphrase, do not fix typos. Report nothing rather than a weak finding: an empty list is \
a good answer. If you doubt a finding, leave it out - never include one while calling it weak, minor or \
borderline. Reply with JSON only."""


def user_prompt(req: Request) -> str:
    fams = "\n".join(f"- {k} ({FAMILIES[k][0]}): {FAMILIES[k][1]}. Evidence: {FAMILIES[k][2]}."
                     for k in req.families)
    nots = "\n".join(f"- {n}" for n in NOT_DEFECTS)
    files = "\n\n".join(f'<file path="{d.rel}">\n{d.text}\n</file>' for d in req.docs)
    focus = (f"\nReport only defects that involve {req.focus}: every finding quotes it at least once. "
             "The other files are the rules every session reads - context for contradictions and "
             "duplicates with it.\n" if req.focus else "")
    return f"""Defects to look for (and only these):
{fams}

These are NOT defects:
{nots}

Files:
{files}
{focus}
Answer with exactly this JSON shape:
{{"findings": [{{"family": "<one of {', '.join(req.families)}>", "quotes": [{{"file": "<path as given>", "text": "<verbatim excerpt, 10-300 characters>"}}], "explanation": "<one or two sentences: the situation and why it is a defect>"}}]}}"""
