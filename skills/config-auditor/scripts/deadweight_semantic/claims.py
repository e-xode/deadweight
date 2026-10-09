"""Contradictions and duplicates found through the instructions themselves, not through file pairs.

Why. Pairing FILES by shared vocabulary misses both defects this layer is for (measured on the
defects authors declared fixing): two texts that contradict each other share little vocabulary
(ranked 141st to 1,144th, 2026-10-01), and a passage of a few lines copied into a 20 KB reference
is drowned by the rest of the file (ranked 11th of 22, 2026-10-06). So the unit is the
instruction, in three steps:

1. extract - each file's instructions, with a verbatim quote, cached by content: a file read once
   is never sent again while its bytes do not change;
2. group - one request per repository sees only the subjects, and names the shared topics; the
   same thing is called "locale JSON" in one file and "translation files" in another, which no
   word overlap joins;
3. confirm - one request per topic that spans two files or more: the instructions on that topic,
   each with its paragraph, and the same closed families and verbatim-evidence rule as the
   whole-file layer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import evidence, transport
from .collect import Doc, Request

VERSION = "claims-2"          # in the cache key: a new extraction prompt never reads an old cache
BATCH_CHARS = 12_000          # files per extraction request, by size: at 40,000 one answer in
                              # eight came back unreadable (cut JSON), 37 of 313 files lost (2026-10-06)
TOPIC_MAX_CLAIMS = 40         # instructions per confirmation request; a larger topic is split
WORKERS = 6

EXTRACT_SYSTEM = """You read instruction files written for a coding agent and list the instructions and facts \
they state. You do not judge them. Every item quotes its source VERBATIM: copy the exact characters, \
10 to 300 of them, do not paraphrase. Reply with JSON only."""

GROUP_SYSTEM = """You file short subject phrases under topics, so that phrases naming the same thing, written \
differently by different authors, share a topic. Reply with JSON only."""

CONFIRM_SYSTEM = """You review instructions from a software project's Claude Code configuration, as a careful \
human reader would, and report only defects from the closed list you are given. Every finding quotes its \
evidence VERBATIM from the instructions shown. Report nothing rather than a weak finding: an empty list is a \
good answer. If you doubt a finding, leave it out. Reply with JSON only."""


@dataclass
class Claim:
    id: str
    file: str
    subject: str
    polarity: str
    action: str
    quote: str
    context: str = ""


@dataclass
class Stage:
    requests: int = 0
    cost_usd: float = 0.0
    cached: int = 0
    errors: list = field(default_factory=list)
    served: set = field(default_factory=set)
    returned: int = 0           # subjects filed under a topic by the grouping answers


VOTES = 3                     # answers per confirmation
# Answers a finding must come back in, per family (maintainer's decision, 2026-10-08): a duplicate needs a
# majority, measured 96 % precise and short on recall; a contradiction needs all of them, measured
# 82-88 % precise, under the 90 % bar. With the vote count kept, another threshold is a recount.
NEEDED = {"59": 2, "58": 3}
# "quotes": a vote counts for a finding only when it quotes the same passages (2026-10-08);
# before, any finding between the same two files counted, whatever it quoted. "contained": an answer
# votes for a finding when one of its own findings holds that finding's quotes; grouped through any
# member ("transitive", audit externe 3, g9-03), one broad answer bridged two narrower findings into
# one group (external audit 4, se-00). A confirmation cached under either older grouping is not replayed.
POLICY = "59:2/3,58:3/3,quotes,contained"


def cache_off(kind: str) -> bool:
    """DEADWEIGHT_SEMANTIC_NO_CACHE=group,confirm turns a cache off - to measure the method itself."""
    return kind in os.environ.get("DEADWEIGHT_SEMANTIC_NO_CACHE", "").split(",")


def _merge_json(path: Path, new: dict) -> None:
    """Read, merge, replace: concurrent audits may lose an entry, never corrupt the file."""
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old.update(new)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "deadweight" / "claims"


def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{VERSION}\0{model}\0{text}".encode("utf-8")).hexdigest()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _json(text: str) -> dict | None:
    """The answer's JSON, read leniently: verbatim quotes of code carry backslashes and control
    characters that a strict parser refuses (36 of 313 files lost on 2026-10-06, nondeterministic).
    Last resort: every complete item object, one by one - a cut answer keeps what it delivered."""
    try:
        s = text[text.index("{"):text.rindex("}") + 1]
    except ValueError:
        return None
    for cand in (s, re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", s)):
        try:
            return json.loads(cand, strict=False)
        except json.JSONDecodeError:
            pass
    items = []
    for m in re.finditer(r'\{[^{}]*"quote"[^{}]*\}', text):
        try:
            items.append(json.loads(m.group(0), strict=False))
        except json.JSONDecodeError:
            continue
    return {"items": items} if items else None


def _paragraph(text: str, quote: str) -> str:
    """The paragraph holding the quote: a rule read without its conditions looks like a contradiction."""
    flat = _norm(quote)
    for para in re.split(r"\n\s*\n", text):
        if flat in _norm(para):
            return para.strip()[:800]
    return quote


def _batches(docs: list[Doc]) -> list[list[Doc]]:
    out, cur, size = [], [], 0
    for d in docs:
        if cur and size + len(d.text) > BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(d)
        size += len(d.text)
    return out + ([cur] if cur else [])


def _extract_prompt(batch: list[Doc]) -> str:
    files = "\n\n".join(f'<file path="{d.rel}">\n{d.text}\n</file>' for d in batch)
    return f"""List every instruction (something the agent must, must not, or should do) and every \
project fact an instruction relies on (a version, a path, a list, a procedure step), in each file below.

{files}

For each item give:
- "file": the path as given
- "subject": what it is about, a short noun phrase (2 to 6 words), as specific as the text allows
- "polarity": "must", "must_not", "prefer", "avoid" or "fact"
- "action": what is required, forbidden or stated, in at most 12 words
- "quote": the verbatim source text, 10 to 300 characters

Answer with exactly this JSON shape:
{{"items": [{{"file": "...", "subject": "...", "polarity": "...", "action": "...", "quote": "..."}}]}}"""


def _keep(batch: list[Doc], items: list, model: str, found: dict) -> None:
    """Each file's verified items, cached by its content. An invented quote is dropped, never cached."""
    per = {d.rel: [] for d in batch}
    texts = {d.rel: _norm(d.text) for d in batch}
    for it in items:
        if not isinstance(it, dict) or it.get("file") not in per:
            continue
        q = str(it.get("quote", ""))
        if len(_norm(q)) < 10 or _norm(q) not in texts[it["file"]]:
            continue
        per[it["file"]].append({k: str(it.get(k, "")) for k in ("subject", "polarity", "action", "quote")})
    cdir = cache_dir()
    cdir.mkdir(parents=True, exist_ok=True)
    for d in batch:
        found[d.rel] = per[d.rel]
        (cdir / f"{_key(model, d.text)}.json").write_text(json.dumps(per[d.rel]), encoding="utf-8")


def extract(docs: list[Doc], model: str, stage: Stage) -> list[Claim]:
    """Every file's claims; a file whose bytes are cached is not sent."""
    cdir = cache_dir()
    found: dict[str, list[dict]] = {}
    todo = []
    for d in docs:
        f = cdir / f"{_key(model, d.text)}.json"
        try:
            found[d.rel] = json.loads(f.read_text(encoding="utf-8"))
            stage.cached += 1
        except (OSError, ValueError):
            todo.append(d)
    # A batch whose answer is unreadable is sent again one file per request: losing a batch
    # silently is how a duplicate went unseen in the first trial (a domain-rules skill, 2026-10-06).
    batches = _batches(todo)
    for wave in (1, 2, 3):
        with ThreadPoolExecutor(WORKERS) as pool:
            answers = list(pool.map(lambda b: transport.ask(EXTRACT_SYSTEM, _extract_prompt(b), model), batches))
        retry = []
        for batch, ans in zip(batches, answers):
            stage.requests += 1
            stage.cost_usd += ans.cost_usd
            stage.served.add(ans.model_served)
            items = None if ans.error else (_json(ans.text) or {}).get("items")
            if not isinstance(items, list):
                if wave == 1 and len(batch) > 1:
                    retry += [[d] for d in batch]
                elif wave < 3 and len(batch) == 1:
                    retry.append(batch)          # a single file once more: the failure is not systematic
                else:
                    stage.errors.append(ans.error or f"extraction: unreadable answer for {batch[0].rel}")
                continue
            _keep(batch, items, model, found)
        if not retry:
            break
        batches = retry
    by_rel = {d.rel: d for d in docs}
    claims = []
    for rel, items in found.items():
        for i, it in enumerate(items):
            claims.append(Claim(f"c{len(claims)}", rel, it["subject"], it["polarity"], it["action"],
                                it["quote"], _paragraph(by_rel[rel].text, it["quote"])))
    return claims


GROUP_CHUNK = 250             # subjects per grouping request
QUOTE_OVERLAP = 0.6           # share of words two quotes have in common to be compared as copies
RARE_TOKEN_MAX = 40           # a word in more claims than this joins nothing on its own


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))


def copies(claims: list[Claim]) -> list[list[Claim]]:
    """Claims of two different files whose paragraphs share most of their words: the shape of a copy.

    Deterministic and free. A passage of a few lines copied into a 20 KB reference is invisible
    to any comparison of whole files and plain at the level of one quote (2026-10-06).
    """
    # The paragraph, not the quote: the extraction quoted "...through an ordered phase pipeline"
    # and stopped before the phase list that was the copy (a domain-rules skill, 2026-10-06).
    words = [_words(c.context or c.quote) for c in claims]
    index: dict[str, list[int]] = {}
    for i, w in enumerate(words):
        for tok in w:
            index.setdefault(tok, []).append(i)
    shared: dict[tuple[int, int], int] = {}
    for ids in index.values():
        if len(ids) > RARE_TOKEN_MAX:
            continue
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                i, j = ids[a], ids[b]
                if claims[i].file != claims[j].file:
                    shared[(i, j)] = shared.get((i, j), 0) + 1
    parent = list(range(len(claims)))

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for (i, j), n in shared.items():
        if n >= 3 and len(words[i]) >= 5 and len(words[j]) >= 5 \
                and len(words[i] & words[j]) / min(len(words[i]), len(words[j])) >= QUOTE_OVERLAP:
            parent[root(i)] = root(j)
    groups: dict[int, list[Claim]] = {}
    for i in range(len(claims)):
        groups.setdefault(root(i), []).append(claims[i])
    return [g for g in groups.values() if len({c.file for c in g}) >= 2]


ANCHOR_MAX = 15               # an anchor named in more claims than this (CLAUDE.md, npm) opposes nothing
POSITIVE, NEGATIVE = {"must", "prefer"}, {"must_not", "avoid"}


def _anchors(quote: str) -> set[str]:
    """Code anchors of a quote: a path's folder (`src/translate/en.json` and `src/translate/*.json`
    meet at `src/translate`), or an identifier in backticks."""
    out = set()
    for span in re.findall(r"`([^`\n]{2,80})`", quote):
        span = span.strip().lower()
        if "/" in span:
            folder = span.rsplit("/", 1)[0].strip("./")
            if folder:
                out.add(folder)
        elif re.fullmatch(r"[\w.$@-]{3,}", span):
            out.add(span)
    return out


def opposed(claims: list[Claim]) -> list[list[Claim]]:
    """Claims of two different files that name the same code anchor with opposite polarity:
    the shape of a contradiction. Deterministic and free.

    The extraction filed "Add keys to both `src/translate/en.json` AND `fr.json`" under
    "Translation keys files" and "Never edit `src/translate/{en,fr,km}.json` directly" under
    "Editing locale files"; no grouping request joined them, in either repository that had
    this declared contradiction (2026-10-06). Both name the folder.
    """
    by_anchor: dict[str, list[Claim]] = {}
    for c in claims:
        for a in _anchors(c.quote):
            by_anchor.setdefault(a, []).append(c)
    out = []
    for members in by_anchor.values():
        if len(members) > ANCHOR_MAX:
            continue
        pos = [c for c in members if c.polarity in POSITIVE]
        neg = [c for c in members if c.polarity in NEGATIVE]
        if pos and neg and len({c.file for c in pos} | {c.file for c in neg}) >= 2 \
                and any(a.file != b.file for a in pos for b in neg):
            out.append(pos + neg)
    return out


def _assign_prompt(topics: list[str], chunk: list[tuple[str, str]]) -> str:
    known = "\n".join(f"t{i}: {n}" for i, n in enumerate(topics)) or "(none yet)"
    listing = "\n".join(f"{sid}: {s}" for sid, s in chunk)
    return f"""Subject phrases from the instruction files of one project must be filed under topics. A topic \
names one precise thing - the same files, setting, procedure, convention, list or fact - never a broad theme.

Topics so far:
{known}

Subjects to file:
{listing}

For each subject, give the id of the topic that names the same thing, or a new topic name (3 to 6 words) \
when none does. Answer with exactly this JSON shape:
{{"assign": [["s0", "t3"], ["s1", "new: engine phase order"]]}}"""


def group(claims: list[Claim], model: str, stage: Stage) -> list[list[Claim]]:
    """Topics spanning two files or more: subjects filed under shared topics, plus copies.

    One request holding every subject of a large repository (about 5,000 for the largest)
    returned 153 groups once and 55 the next time on the same input, and lost the topic the
    trial was looking for (2026-10-06). So subjects are filed in chunks, in order, each chunk
    seeing the topics already named - the names stay consistent across chunks.
    """
    subjects = sorted({_norm(c.subject).lower() for c in claims if c.subject})
    # A subject filed once keeps its topic: re-filing it is where two runs on the same files
    # diverged (2026-10-07, 0.59 agreement with the extraction cached).
    filed_path = cache_dir() / f"topics-{model}.json"
    filed: dict[str, str] = {}
    if not cache_off("group"):
        try:
            filed = json.loads(filed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            filed = {}
    topic_names: list[str] = sorted({filed[s] for s in subjects if s in filed})
    topic_of: dict[str, int] = {s: topic_names.index(filed[s]) for s in subjects if s in filed}
    stage.cached = len(topic_of)
    ids = [(f"s{i}", s) for i, s in enumerate(subjects) if s not in topic_of]
    for k in range(0, len(ids), GROUP_CHUNK):
        chunk = ids[k:k + GROUP_CHUNK]
        ans = transport.ask(GROUP_SYSTEM, _assign_prompt(topic_names, chunk), model)
        stage.requests += 1
        stage.cost_usd += ans.cost_usd
        stage.served.add(ans.model_served)
        pairs = None if ans.error else (_json(ans.text) or {}).get("assign")
        if not isinstance(pairs, list):
            stage.errors.append(ans.error or f"grouping: unreadable answer for subjects {k}-{k + len(chunk) - 1}")
            continue
        by_id = dict(chunk)
        for pair in pairs:
            if not (isinstance(pair, list) and len(pair) == 2 and pair[0] in by_id):
                continue
            target = str(pair[1])
            if re.fullmatch(r"t\d+", target) and int(target[1:]) < len(topic_names):
                topic_of[by_id[pair[0]]] = int(target[1:])
            else:
                topic_names.append(re.sub(r"^new:\s*", "", target).strip()[:80])
                topic_of[by_id[pair[0]]] = len(topic_names) - 1
            stage.returned += 1
    if not cache_off("group") and topic_of:
        filed_path.parent.mkdir(parents=True, exist_ok=True)
        _merge_json(filed_path, {s: topic_names[n] for s, n in topic_of.items()})
    members: dict[int, list[Claim]] = {}
    for c in claims:
        n = topic_of.get(_norm(c.subject).lower())
        if n is not None:
            members.setdefault(n, []).append(c)
    topics = [m for m in members.values() if len({c.file for c in m}) >= 2]
    # Copies the topics did not already bring together in one request.
    within = [{c.id for c in t} for t in topics]
    for g in copies(claims) + opposed(claims):
        if not any({c.id for c in g} <= w for w in within):
            topics.append(g)
            within.append({c.id for c in g})
    out = []
    for t in topics:
        for i in range(0, len(t), TOPIC_MAX_CLAIMS):
            part = t[i:i + TOPIC_MAX_CLAIMS]
            if len({c.file for c in part}) >= 2:
                out.append(part)
    return out


def confirm_requests(topics: list[list[Claim]], docs: list[Doc], families: tuple[str, ...]) -> list[Request]:
    """One request per topic. Its documents are the paragraphs shown, so evidence.check validates
    every quote against text the model actually saw, and each paragraph is in its source file."""
    out = []
    for t in topics:
        shown: dict[str, list[str]] = {}
        for c in t:
            shown.setdefault(c.file, [])
            if c.context not in shown[c.file]:
                shown[c.file].append(c.context)
        req_docs = [Doc(rel, "claims", "\n\n[...]\n\n".join(paras)) for rel, paras in shown.items()]
        out.append(Request(families, req_docs, "topic"))
    return out


def confirm_prompt(req: Request, describe) -> str:
    fams = "\n".join(describe(k) for k in req.families)
    files = "\n\n".join(f'<file path="{d.rel}">\n{d.text}\n</file>' for d in req.docs)
    return f"""The excerpts below come from different files of one project's agent configuration and \
were selected because they concern the same subject. Excerpts from one file are separated by [...].

Defects to look for (and only these), each between two DIFFERENT files:
{fams}
These are NOT defects:
- a general rule and a scoped rule that narrows it (a different folder, step, situation or role)
- a pointer to another file ("see X.md")
- a safety instruction deliberately repeated in an agent
- instructions for different situations that only look alike

{files}

Answer with exactly this JSON shape:
{{"findings": [{{"family": "<one of {', '.join(req.families)}>", "quotes": [{{"file": "<path as given>", \
"text": "<verbatim excerpt, 10-300 characters>"}}], "drifted": <true when the copies already say different \
things, false when they say the same thing in other words; false for a contradiction>, "explanation": "<one \
or two sentences: the situation and why it is a defect>"}}]}}"""


def checked(finding: dict, req: Request, sources: dict[str, str]) -> str | None:
    """evidence.check on the excerpts shown, then each quote against its full source file."""
    why = evidence.check(finding, req)
    if why:
        return why
    for q in finding["quotes"]:
        if _norm(str(q["text"])) not in sources.get(q["file"], ""):
            return f"invented quote: not found in {q['file']}"
    if len({q["file"] for q in finding["quotes"]}) < 2:
        return "both sides in one file: this method reports duplicates between files only"
    return None


def _vote_key(f: dict) -> tuple:
    return (str(f["family"]).split("-")[0], tuple(sorted({q["file"] for q in f["quotes"]})))


def _holds(big: dict, small: dict) -> bool:
    """`big` gives the finding `small` is: same family, same files, and in each file a quote of
    `small` inside a quote of `big` - the excerpt may be as long or longer, not elsewhere.
    Keyed on the files alone, three answers naming three different contradictions between the
    same two files counted as one unanimous finding (audit, 2026-10-08). One way only: matched
    both ways, a paragraph-sized quote matched each sentence in it, and linked findings that no
    answer gave together (external audit 4, se-00)."""
    if _vote_key(big) != _vote_key(small):
        return False
    for file in _vote_key(big)[1]:
        qb = [_norm(str(q["text"])) for q in big["quotes"] if q["file"] == file]
        qs = [_norm(str(q["text"])) for q in small["quotes"] if q["file"] == file]
        if not any(x in y for x in qs for y in qb):
            return False
    return True


def confirm(req: Request, prompt: str, model: str, sources: dict[str, str], stage: Stage,
            votes: int = VOTES) -> tuple[list[dict], list[dict], int]:
    """Findings that come back in a majority of `votes` answers, cached by the request's exact text.

    One answer per topic made the report change between two runs: 0.59 of the file pairs found
    by one run came back in the next (2026-10-07). A finding the model gives once in three is,
    by construction, one that makes the report vary.
    """
    path = cache_dir() / f"confirm-{_key(model, f'{votes}\0{POLICY}\0{prompt}')}.json"
    if not cache_off("confirm"):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            stage.cached += 1
            return d["findings"], d["rejected"], 0
        except (OSError, ValueError, KeyError):
            pass
    accepted: list[tuple[int, dict]] = []     # (which answer, finding), every checked finding
    rejected, unreadable, failed = [], 0, 0
    for vote in range(votes):
        ans = transport.ask(CONFIRM_SYSTEM, prompt, model)
        stage.requests += 1
        stage.cost_usd += ans.cost_usd
        stage.served.add(ans.model_served)
        if ans.error:
            stage.errors.append(ans.error)
            failed += 1
            continue
        got = evidence.parse(ans.text)
        if got is None:
            unreadable += 1
            continue
        for f in got:
            why = checked(f, req, sources) if isinstance(f, dict) else "not an object"
            if why:
                rejected.append({"why": why, "family": str(f.get("family", "")) if isinstance(f, dict) else ""})
                continue
            accepted.append((vote, f))
    # Each distinct finding is a candidate; an answer votes for it when one of its findings holds
    # its quotes (the same passage, or a longer excerpt of it). No chaining: a broad answer votes
    # for every narrower finding it holds, but a narrow answer does not vote for the broad one, so
    # one broad answer cannot link two narrow findings into a group nobody gave in full (external
    # audit 4, se-00). The order of the answers decides nothing (audit externe 3, g9-03).
    distinct: dict[str, dict] = {}
    for _, f in accepted:
        distinct.setdefault(json.dumps([_vote_key(f), sorted(_norm(str(q["text"])) for q in f["quotes"])],
                                       ensure_ascii=False), f)
    cands = []
    for f in distinct.values():
        voters = {v for v, g in accepted if _holds(g, f)}
        if len(voters) >= min(NEEDED.get(_vote_key(f)[0], votes // 2 + 1), votes):
            cands.append((f, voters))
    kept = []
    for f, voters in cands:
        # A shorter excerpt of a finding that is kept with as many votes is that finding.
        if any(g is not f and _holds(g, f) and not _holds(f, g) and len(gv) >= len(voters)
               for g, gv in cands):
            continue
        f = dict(f)
        f["votes"] = len(voters)
        f["drifted"] = any(bool(g.get("drifted")) for v, g in accepted if _holds(g, f))
        kept.append(f)
    kept.sort(key=lambda x: json.dumps(x["quotes"], sort_keys=True, ensure_ascii=False))
    # A vote that failed or came back unreadable is not a vote for "nothing": cached, it would be
    # replayed as an empty result, with 0 requests and 0 errors, until the prompt changes.
    if not cache_off("confirm") and not failed and not unreadable:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"findings": kept, "rejected": rejected}, ensure_ascii=False), encoding="utf-8")
    return kept, rejected, unreadable
