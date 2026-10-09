"""Every quote a finding carries must be found, character for character, in the file it names.

A model asked for evidence can produce text that looks like evidence. On 2026-09-30 an agent
writing doctrine put a sentence between quotation marks that no page contained. So the check is
mechanical: whitespace normalised, nothing else forgiven. A finding with one invented quote is
rejected whole, and counted - the rate of invented quotes is part of what this layer reports.
"""
from __future__ import annotations

import json
import re

from .collect import Request
from .families import FAMILIES


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse(text: str) -> list[dict] | None:
    """The findings of one answer, or None when the answer is not the JSON asked for."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        d = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None
    found = d.get("findings") if isinstance(d, dict) else None
    return found if isinstance(found, list) else None


# An answer that disowns its own finding: "Weak; not reported as a real duplicate", "minor
# mismatch", "arguably not". 6 of 14 false findings in the 2026-10-01 measurement said so in their
# explanation and were emitted anyway, with valid quotes - the quotes cannot catch them.
DISOWNED_RE = re.compile(r"^\s*(weak\b|minor\b|borderline\b|arguably\b|not a real\b|no (real )?defect\b)"
                         r"|not reported as a real|no defect is asserted|arguably not a|probably not a real"
                         r"|\bweak,? (borderline|candidate)\b|\bthis is a minor mismatch\b|\bborderline mismatch\b"
                         # 2026-10-06, claims method: "This is weak: ... so it is not a true contradiction."
                         r"|\bthis is (weak|minor|borderline)\b|\bnot a (true|real|genuine) (contradiction|duplicate|defect)\b",
                         re.IGNORECASE)


def check(finding: dict, req: Request) -> str | None:
    """None when the finding stands; otherwise why it is rejected."""
    if DISOWNED_RE.search(str(finding.get("explanation", ""))):
        return "disowned by its own explanation"
    fam = str(finding.get("family", "")).split("-")[0]
    if fam not in req.families:
        return f"family {fam or '?'} was not asked for"
    quotes = finding.get("quotes")
    if not isinstance(quotes, list) or len(quotes) < FAMILIES[fam][3]:
        return f"{FAMILIES[fam][0]} needs {FAMILIES[fam][3]} quote(s)"
    sent = {d.rel: _norm(d.text) for d in req.docs if d.kind != "listing"}
    for q in quotes:
        if not isinstance(q, dict):
            return "a quote is not an object"
        text, path = _norm(str(q.get("text", ""))), str(q.get("file", ""))
        if path not in sent:
            return f"quotes a file it was not shown: {path or '?'}"
        if len(text) < 10 or text not in sent[path]:
            return f"invented quote: not found in {path}"
    if req.focus and not any(str(q.get("file")) == req.focus for q in quotes):
        return f"does not quote the file under review ({req.focus})"
    if fam in ("58", "59") and not _two_passages(quotes, sent if fam == "59" else None):
        return "the two sides are the same passage"
    return None


def _two_passages(quotes: list[dict], sent: dict[str, str] | None = None) -> bool:
    """Whether two of the quotes are different passages: another file, or, in the same file,
    neither text inside the other. A sentence quoted twice, or a sentence and a fragment of
    it, is one passage - it cannot contradict or repeat itself. With `sent` (duplicates only),
    the shorter text written twice in that file is two passages: a rule copied word for word
    repeats itself (audit externe 3, g9-00)."""
    sides = [(str(q.get("file", "")), _norm(str(q.get("text", "")))) for q in quotes]

    def distinct(fa: str, ta: str, fb: str, tb: str) -> bool:
        if fa != fb or (ta not in tb and tb not in ta):
            return True
        short = min(ta, tb, key=len)
        return bool(sent) and bool(short) and sent.get(fa, "").count(short) >= 2

    return any(distinct(fa, ta, fb, tb)
               for i, (fa, ta) in enumerate(sides) for fb, tb in sides[i + 1:])
