"""What is sent to the model: the instruction files of the repository, as units and as pairs.

Pairs (for contradictions and duplicates) are preselected statically by shared vocabulary, so
the number of requests stays bounded and announced before any call is made.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from deadweight_audit.checks.descriptions import _overlap_tokens
from deadweight_audit.context import AuditContext
from deadweight_audit.parsing.frontmatter import parse_frontmatter
from deadweight_audit.parsing.markdown import injected_memory
from deadweight_audit.repo import claude_md_path, readable_files, repo_files

MAX_CHARS = 20_000          # per file sent; a longer file is cut, and the report says so
PAIR_MIN_OVERLAP = 0.15     # Jaccard of vocabularies; below it a pair is not worth a request
REQUEST_MAX_CHARS = 80_000  # per request; references beyond it are left out, and counted
# A Markdown file an instruction file points to: a link, an `@` import, or a path in backticks.
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)|(?<![\w`])@([\w./~-]+\.md)|`([\w./-]+\.md)`")


@dataclass
class Doc:
    rel: str                # repository-relative path, as the model sees it
    kind: str               # claude-md | rule | skill | agent | reference
    text: str
    truncated: bool = False
    parent: str | None = None   # for a reference: the instruction file that points to it


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
        doc = _read(root, path, kind)
        if doc:
            docs.append(doc)
    return docs + references(root, docs)


MEMORY_NAMES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md")


def not_collected(ctx: AuditContext, docs: list[Doc]) -> list[str]:
    """Instruction files Claude Code can read that `documents` does not collect: commands
    ("Custom commands have been merged into skills", skills), and the memory files besides the
    project CLAUDE.md - CLAUDE.local.md, CLAUDE.md in a subdirectory, AGENTS.md (memory).
    Unless an instruction file links them, they are not reviewed, and the report says so."""
    sent = {d.rel for d in docs}
    # By real path too: a CLAUDE.md symlinked to AGENTS.md sends AGENTS.md's text as CLAUDE.md,
    # a setup the memory page documents ("Either way Claude reads the content once").
    sent_real = {os.path.realpath(ctx.root / r) for r in sent}
    base = ctx.claude_dir.strip("/")
    commands = "commands/" if base in ("", ".") else base + "/commands/"
    out = []
    for rel in repo_files(ctx.root):
        name = rel.rsplit("/", 1)[-1]
        if rel in sent or os.path.realpath(ctx.root / rel) in sent_real:
            continue
        if name in MEMORY_NAMES or (rel.startswith(commands) and rel.endswith(".md")):
            out.append(rel)
    return out


def _read(root: Path, path: Path, kind: str, parent: str | None = None) -> Doc | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if kind == "claude-md":
        text = injected_memory(text)
    return Doc(path.relative_to(root).as_posix(), kind, text[:MAX_CHARS], len(text) > MAX_CHARS, parent)


def references(root: Path, docs: list[Doc]) -> list[Doc]:
    """The Markdown files the instruction files point to, one hop, inside the repository.

    Measured on the defects authors declared fixing (2026-10-01): 7 of 35 sat in a file the
    layer never read - a skill's `references/`, a `.claude/reference/` the CLAUDE.md links -
    and a duplicate between a skill and its own reference was invisible by construction.
    One hop only: what an instruction file names is configuration; what a reference names
    is documentation. Each reference is sent with the file that points to it.
    """
    real_root = os.path.realpath(root)
    seen = {d.rel for d in docs}
    out: list[Doc] = []
    for d in docs:
        base = (root / d.rel).parent
        for m in LINK.finditer(d.text):
            target = next(g for g in m.groups() if g)
            for cand in (base / target, root / target.lstrip("/")):
                real = os.path.realpath(cand)
                if not real.startswith(real_root + os.sep) or not os.path.isfile(real):
                    continue
                rel = Path(os.path.relpath(real, real_root)).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    ref = _read(root, root / rel, "reference", d.rel)
                    if ref:
                        out.append(ref)
                break
    return out


def _fit(docs: list[Doc], keep: int) -> tuple[list[Doc], int]:
    """The first `keep` documents always; the references after them while the request has room."""
    out, size, dropped = docs[:keep], sum(len(d.text) for d in docs[:keep]), 0
    for d in docs[keep:]:
        if size + len(d.text) > REQUEST_MAX_CHARS:
            dropped += 1
            continue
        out.append(d)
        size += len(d.text)
    return out, dropped


def _jaccard_sets(x: set[str], y: set[str]) -> float:
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
    law_rels = {d.rel for d in law}
    refs_of: dict[str, list[Doc]] = {}
    for d in docs:
        if d.kind == "reference":
            refs_of.setdefault(d.parent, []).append(d)
    law_refs = [r for rel in law_rels for r in refs_of.get(rel, [])]
    dropped_refs = 0
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
            sent, n = _fit(law + [listing] + law_refs, len(law) + 1)
            dropped_refs += n
            reqs["law"].append(Request(fams, sent, "law"))
    for d in docs:
        if d.kind in ("skill", "agent"):
            fm, _ = parse_frontmatter(d.text)
            fams = tuple(f for f in ("58", "59", "60", "61") if f in wanted
                         and (f != "60" or (fm and fm.get("description"))))
            if fams:
                # Closest vocabulary first: when the request cannot hold every reference, the
                # ones that can repeat the skill go in (duplicates ranked 2nd-31st, 2026-10-01).
                own = set(_overlap_tokens(d.text))
                refs = sorted(refs_of.get(d.rel, []),
                              key=lambda r: -_jaccard_sets(own, set(_overlap_tokens(r.text))))
                sent, n = _fit(law + [d] + refs, len(law) + 1)
                dropped_refs += n
                reqs["focus"].append(Request(fams, sent, "focus", d.rel))
    # References join the pairs: a rule copied from a skill into another skill's reference is
    # the duplicate authors fixed most often after release agents (2026-10-01).
    units = [d for d in docs if d.kind in ("skill", "agent", "reference") and d.rel not in
             {r.rel for r in law_refs}]
    # Each vocabulary once: recomputed per pair, the references of a large repository made
    # this quadratic in tokenisations, not only in comparisons.
    vocab = [set(_overlap_tokens(u.text)) for u in units]
    pairs = sorted(((_jaccard_sets(vocab[i], vocab[j]), units[i], units[j])
                    for i in range(len(units)) for j in range(i + 1, len(units))),
                   key=lambda t: -t[0])
    reqs["pair"] = ([Request(("59",), [a, b], "pair") for score, a, b in pairs if score >= PAIR_MIN_OVERLAP]
                    if "59" in wanted else [])
    chosen, skipped = [], {}
    for kind in ("law", "focus", "pair"):
        room = max(0, max_requests - len(chosen))
        chosen += reqs[kind][:room]
        skipped[kind] = max(0, len(reqs[kind]) - room)
    skipped["references"] = dropped_refs
    return chosen, skipped
