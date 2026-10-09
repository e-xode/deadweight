"""Run the semantic layer over one repository and render what it found, apart from the counts."""
from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from deadweight_audit.context import AuditContext

from . import claims, collect, evidence, prompts, transport
from .families import DEFAULT, FAMILIES, ON_REQUEST

PACKAGE_DIR = Path(__file__).resolve().parent
WORKERS = 4


def identity() -> str:
    """Short sha of this package. Not the auditor's: changing a prompt moves no floor."""
    h = hashlib.sha256()
    for f in sorted(PACKAGE_DIR.glob("*.py")):
        h.update(f.name.encode() + b"\0" + f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:8]


@dataclass
class Result:
    model: str
    served: set = field(default_factory=set)
    findings: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    requests: int = 0
    skipped: dict = field(default_factory=dict)
    unreadable: int = 0
    errors: list = field(default_factory=list)
    cost_usd: float = 0.0
    files_sent: set = field(default_factory=set)
    truncated: set = field(default_factory=set)
    date: str = ""
    harness: str = ""
    families: list = field(default_factory=list)
    internal_skipped: int = 0
    method: str = "files"
    skill_internal_skipped: int = 0
    stages: dict = field(default_factory=dict)
    topics: list = field(default_factory=list)
    not_reviewed: list = field(default_factory=list)

    def identity(self) -> dict:
        return {"model": self.model, "served": sorted(self.served), "claude_code": self.harness,
                "families": self.families, "method": self.method,
                "package_sha": identity(), "date": self.date}

    def as_json(self) -> dict:
        return {"identity": self.identity(), "counted": False, "findings": self.findings,
                "rejected": self.rejected, "requests": self.requests,
                "skipped_by_cap": self.skipped, "unreadable_answers": self.unreadable,
                "errors": self.errors, "cost_usd": round(self.cost_usd, 4),
                "internal_duplicates_not_shown": self.internal_skipped,
                "files_sent": sorted(self.files_sent), "stages": self.stages,
                "topics": self.topics, "instruction_files_not_reviewed": self.not_reviewed}

    def render(self) -> str:
        out = [f"\n=== SEMANTIC ({len(self.findings)}) - not counted, not in the floor ===",
               f"  Model {self.model} (served: {', '.join(sorted(self.served)) or '-'}; {self.harness}), layer "
               f"{identity()}, {self.requests} request(s), ${self.cost_usd:.2f}. Sent "
               f"{len(self.files_sent)} file(s) to the model."
               + (" Left out by --max-requests: " + ", ".join(f"{n} {k}" for k, n in self.skipped.items()
                                                           if n and k != "references")
                  + " - those files were NOT reviewed." if any(n for k, n in self.skipped.items()
                                                                if k != "references") else "")
               + (f" {self.skipped['references']} referenced file(s) left out of a request over "
                  f"{collect.REQUEST_MAX_CHARS} characters - NOT reviewed there."
                  if self.skipped.get("references") else "")]
        if self.not_reviewed:
            names = ", ".join(self.not_reviewed[:5]) + (", ..." if len(self.not_reviewed) > 5 else "")
            out.append(f"  {len(self.not_reviewed)} instruction file(s) this layer does not collect were NOT "
                       f"reviewed (commands, CLAUDE.local.md, nested CLAUDE.md, AGENTS.md): {names}")
        for f in self.findings:
            out.append(f"  [{f['check']}] {f['explanation']}")
            out += [f"      {q['file']}: \"{q['text']}\"" for q in f["quotes"]]
        if self.internal_skipped:
            out.append(f"  {self.internal_skipped} duplicate(s) inside a single file not shown "
                       "(often a rule and its anti-pattern): --also internal-duplicates.")
        if self.rejected:
            invented = sum(1 for r in self.rejected if r["why"].startswith("invented"))
            out.append(f"  {len(self.rejected)} answer(s) rejected for missing or wrong evidence "
                       f"({invented} with an invented quote).")
        for e in self.errors:
            out.append(f"  Request failed: {e}")
        out.append("  A model's reading, not a measurement: each finding stands only on its quotes - "
                   "check them before acting.")
        return "\n".join(out)


def _describe(k: str) -> str:
    return f"- {k} ({FAMILIES[k][0]}): {FAMILIES[k][1]}. Evidence: {FAMILIES[k][2]}."


def _unit(path: str) -> str:
    """A skill folder, or the file itself: SKILL.md and its references are one unit."""
    parts = path.split("/")
    for i in (0, 1):                     # skills/<name>/ in a plugin, .claude/skills/<name>/ in a project
        if len(parts) > i + 2 and parts[i] == "skills":
            return "/".join(parts[:i + 2])
    return path


def run_claims(ctx: AuditContext, model: str, max_requests: int, res: Result,
               also: tuple[str, ...] = ()) -> Result:
    """Contradictions and duplicates between files, through the instructions (claims.py)."""
    docs = collect.documents(ctx)
    res.not_reviewed = collect.not_collected(ctx, docs)
    sources = {d.rel: claims._norm(d.text) for d in docs}
    ext, grp, con = claims.Stage(), claims.Stage(), claims.Stage()
    found = claims.extract(docs, model, ext)
    topics = claims.group(found, model, grp)
    reqs = claims.confirm_requests(topics, docs, ("58", "59"))
    res.skipped = {"topics": max(0, len(reqs) - max_requests)}
    # What was compared, and what the cap left out: the reader sees which subjects were never asked.
    res.topics = [{"subjects": sorted({c.subject for c in t}), "files": sorted({c.file for c in t}),
                   "sent": i < max_requests} for i, t in enumerate(topics)]
    reqs = reqs[:max_requests]
    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda r: claims.confirm(r, claims.confirm_prompt(r, _describe), model,
                                                         sources, con), reqs))
    seen = set()
    for req, (got, rejected, unreadable) in zip(reqs, results):
        res.files_sent |= {d.rel for d in req.docs}
        res.rejected += rejected
        res.unreadable += unreadable
        for f in got:
            fam = str(f["family"]).split("-")[0]
            key = (fam, tuple(sorted((q["file"], " ".join(q["text"].split())) for q in f["quotes"])))
            if key in seen:
                continue
            seen.add(key)
            # A SKILL.md restating its own reference is shown like any duplicate: 15 of 21 sampled
            # were rules copied from the reference, 0 were pointers (2026-10-08), and the copy in
            # SKILL.md is read on every trigger. `drifted` says which copies already disagree.
            res.findings.append({"check": FAMILIES[fam][0], "explanation": str(f.get("explanation", "")),
                                 "drifted": bool(f.get("drifted")), "votes": f.get("votes"),
                                 "quotes": [{"file": q["file"], "text": q["text"]} for q in f["quotes"]]})
    for name, s in (("extract", ext), ("group", grp), ("confirm", con)):
        res.stages[name] = {"requests": s.requests, "cost_usd": round(s.cost_usd, 4), "cached": s.cached,
                            "errors": len(s.errors)}
        res.requests += s.requests
        res.cost_usd += s.cost_usd
        res.served |= s.served
        res.errors += s.errors
    res.stages["claims"] = len(found)
    res.stages["topics"] = len(topics)
    res.stages["subjects_filed"] = grp.returned
    res.stages["skill_internal_not_shown"] = res.skill_internal_skipped
    return res


def run_semantic(ctx: AuditContext, model: str, max_requests: int, also: tuple[str, ...] = (),
                 method: str = "files") -> Result:
    res = Result(model=model, date=time.strftime("%Y-%m-%d"), harness=transport.harness_version())
    res.method = method
    if method == "claims":
        res.families = ["58", "59"]
        return run_claims(ctx, model, max_requests, res, also)
    wanted = set(DEFAULT) | {ON_REQUEST[a] for a in also}
    internal = "internal-duplicates" in also
    res.families = sorted(wanted) + (["59-internal"] if internal else [])
    docs = collect.documents(ctx)
    res.not_reviewed = collect.not_collected(ctx, docs)
    reqs, res.skipped = collect.plan(docs, max_requests, wanted)
    seen = set()
    # Requests are independent: a few run at once. Answers are read back in request order, so
    # the report does not depend on which one returned first.
    with ThreadPoolExecutor(WORKERS) as pool:
        answers = list(pool.map(lambda r: transport.ask(prompts.SYSTEM, prompts.user_prompt(r), model), reqs))
    for req, ans in zip(reqs, answers):
        res.requests += 1
        res.cost_usd += ans.cost_usd
        res.served.add(ans.model_served)
        res.files_sent |= {d.rel for d in req.docs if d.kind != "listing"}
        if ans.error:
            res.errors.append(ans.error)
            continue
        found = evidence.parse(ans.text)
        if found is None:
            res.unreadable += 1
            continue
        for f in found:
            why = evidence.check(f, req) if isinstance(f, dict) else "not an object"
            if why:
                res.rejected.append({"why": why, "family": str(f.get("family", "")) if isinstance(f, dict) else ""})
                continue
            fam = str(f["family"]).split("-")[0]
            if fam == "59" and not internal and len({q["file"] for q in f["quotes"]}) < 2:
                res.internal_skipped += 1      # the same rule twice in one file: on request only
                continue
            key = (fam, tuple(sorted((q["file"], " ".join(q["text"].split())) for q in f["quotes"])))
            if key in seen:
                continue
            seen.add(key)
            res.findings.append({"check": FAMILIES[fam][0], "explanation": str(f.get("explanation", "")),
                                 "quotes": [{"file": q["file"], "text": q["text"]} for q in f["quotes"]]})
    return res
