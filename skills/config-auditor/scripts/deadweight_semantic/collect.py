"""What is sent to the model: the instruction files of the repository, as units and as pairs.

Pairs (for contradictions and duplicates) are preselected statically by shared vocabulary, so
the number of requests stays bounded and announced before any call is made.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from deadweight_audit.checks.descriptions import _overlap_tokens
from deadweight_audit.context import AuditContext
from deadweight_audit.parsing.frontmatter import parse_frontmatter
from deadweight_audit.parsing.markdown import injected_memory
from deadweight_audit.repo import claude_md_path, readable_files

MAX_CHARS = 20_000          # per file sent; a longer file is cut, and the report says so
PAIR_MIN_OVERLAP = 0.15     # Jaccard of vocabularies; below it a pair is not worth a request


@dataclass
class Doc:
    rel: str                # repository-relative path, as the model sees it
    kind: str               # claude-md | rule | skill | agent
    text: str
    truncated: bool = False


@dataclass
class Request:
    families: tuple[str, ...]
    docs: list[Doc]
    kind: str = "law"            # law | focus | pair
    focus: str | None = None     # a finding must quote this file


def documents(ctx: AuditContext) -> list[Doc]:
    root = ctx.root
    found: list[tuple[Path, str]] = []
    claude_md = claude_md_path(root)
    if claude_md.is_file():
        found.append((claude_md, "claude-md"))
    found += [(p, "rule") for p in readable_files((root / ctx.claude_dir / "rules").rglob("*.md"))]
    found += [(p, "skill") for p in readable_files((root / ctx.skills_dir).glob("*/SKILL.md"))]
    found += [(p, "agent") for p in readable_files((root / ctx.agents_dir).glob("*.md"))]
    docs = []
    for path, kind in found:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if kind == "claude-md":
            text = injected_memory(text)
        docs.append(Doc(path.relative_to(root).as_posix(), kind, text[:MAX_CHARS], len(text) > MAX_CHARS))
    return docs


def _jaccard(a: str, b: str) -> float:
    x, y = set(_overlap_tokens(a)), set(_overlap_tokens(b))
    return len(x & y) / len(x | y) if x and y else 0.0


def plan(docs: list[Doc], max_requests: int, wanted: set[str] = frozenset({"58", "59"})) -> tuple[list[Request], dict[str, int]]:
    """The requests to make, and how many of each kind the cap left out.

    Measured on the defects authors declared fixing (2026-10-01): a contradiction sits between the
    LAW - CLAUDE.md and the rules, read in every session - and one agent or skill, or inside one
    file; two texts that contradict each other share little vocabulary, so pairing files by
    vocabulary ranked them 141st to 1144th. Duplicates do share it (ranked 2nd to 31st), so pairs
    of skills or agents are kept for duplicates only.
    """
    law = [d for d in docs if d.kind in ("claude-md", "rule")]
    lines = []
    for s in docs:
        if s.kind == "skill":
            fm, _ = parse_frontmatter(s.text)
            lines.append(f"- {s.rel}: {(fm or {}).get('description', '')}")
    listing = Doc("(skills of this repository)", "listing", "\n".join(lines) or "(none)")
    reqs = {"law": [], "focus": [], "pair": []}
    if law:
        fams = tuple(f for f in ("58", "59", "61", "62") if f in wanted)
        if fams:
            reqs["law"].append(Request(fams, law + [listing], "law"))
    for d in docs:
        if d.kind in ("skill", "agent"):
            fm, _ = parse_frontmatter(d.text)
            fams = tuple(f for f in ("58", "59", "60", "61") if f in wanted
                         and (f != "60" or (fm and fm.get("description"))))
            if fams:
                reqs["focus"].append(Request(fams, law + [d], "focus", d.rel))
    units = [d for d in docs if d.kind in ("skill", "agent")]
    pairs = sorted(((_jaccard(a.text, b.text), a, b) for i, a in enumerate(units) for b in units[i + 1:]),
                   key=lambda t: -t[0])
    reqs["pair"] = ([Request(("59",), [a, b], "pair") for score, a, b in pairs if score >= PAIR_MIN_OVERLAP]
                    if "59" in wanted else [])
    chosen, skipped = [], {}
    for kind in ("law", "focus", "pair"):
        room = max(0, max_requests - len(chosen))
        chosen += reqs[kind][:room]
        skipped[kind] = max(0, len(reqs[kind]) - room)
    return chosen, skipped
