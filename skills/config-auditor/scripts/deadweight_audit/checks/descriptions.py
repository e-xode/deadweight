"""Descriptions: anti-triggers, agent description budget, confusable pairs."""
from __future__ import annotations

import re

from ..checks.budget import listing_hidden_skills
from ..context import AuditContext
from ..limits import CHARS_PER_TOKEN
from ..report import Report, house, house_note


def check_agent_descriptions(ctx: AuditContext, report: Report, agents: dict[str, dict]) -> None:
    total = sum(len(m.get("description", "")) for m in agents.values())
    if total / CHARS_PER_TOKEN > 15000:
        report.add("08b-agent-description", "WARN",
                   f"Agent descriptions total {total} chars, about {int(total / CHARS_PER_TOKEN)} "
                   "tokens: past 15,000 tokens Claude Code shows a startup warning (sub-agents).",
                   "")
    for name, meta in agents.items():
        desc = meta.get("description", "")
        if not desc:
            continue
        if len(desc) < ctx.limits.DESCRIPTION_MIN_CHARS:
            report.add(
                "08b-agent-description",
                house(ctx),
                f"Agent '{name}' description is only {len(desc)} chars (min {ctx.limits.DESCRIPTION_MIN_CHARS})."
                + house_note("80-900 chars", "10-5,000 chars, best 200-1,000 (plugin-dev, "
                             "agent-development); a startup warning past 15,000 tokens in total"),
                meta["path"],
            )
        if len(desc) > ctx.limits.AGENT_DESCRIPTION_MAX_CHARS:
            report.add(
                "08b-agent-description",
                house(ctx),
                f"Agent '{name}' description is {len(desc)} chars (> {ctx.limits.AGENT_DESCRIPTION_MAX_CHARS}). Description = trigger surface; move knowledge to the body."
                + house_note("at most 900 chars", "10-5,000 chars, best 200-1,000 (plugin-dev)"),
                meta["path"],
            )
        if not ANTI_TRIGGER_RE.search(desc):
            # Same concept as 04, same severity: a WARN here and a NOTICE there made the
            # grade depend on the object, not on the evidence (259 WARN on a public sample).
            report.add(
                "08b-agent-description",
                house(ctx),
                f"Agent '{name}' description says when to use it, not when not to."
                + house_note("an anti-trigger clause in every description",
                             "plugin-dev (agent-development) recommends \"Be specific about "
                             "when NOT to use the agent\"; the sub-agents docs require nothing"),
                meta["path"],
            )


# One pattern, two checks. Until 2026-09-22 checks 04 and 08b carried two different
# regexes - 08b's missed "Do not use" with a space, which 04 accepted - so the same
# clause was seen on a skill and not on an agent. A detector that disagrees with its
# twin is a detector nobody can act on.
#
# The non-English alternatives are deliberate. A project that has formally exempted
# `11-english-only` writes its descriptions in its own language; refusing to see the
# clause there fires this check on precisely the projects that already declared their
# exception, which is how a criterion becomes unsatisfiable and then ignored. The list
# is not a translation table - it holds the openers actually observed on the fleet.
ANTI_TRIGGER_RE = re.compile(
    r"Do ?n'?o?t use|Never use|Not for:|Out of scope|Anti-?trigger"
    r"|Ne pas utiliser|N'utilisez? pas|Hors périmètre",
    re.IGNORECASE,
)


# --- Confusable descriptions -------------------------------------------------
# TF-IDF over the descriptions of the skills that actually compete, cosine per
# pair. Stdlib only. A withheld skill is excluded: it is not in the listing, so it
# cannot steal an activation, and counting it manufactures phantom pairs.
_OVERLAP_STOP = set("""
the a an and or of to for in on with when use used using this that it its not no
don dont skill skills agent agents project file files code claude anthropic
""".split())


def _overlap_tokens(text: str) -> list[str]:
    import unicodedata
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")
    return [w for w in re.split(r"[^a-z0-9]+", text) if len(w) >= 3 and w not in _OVERLAP_STOP]


def check_description_overlap(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """Descriptions close enough to compete for the same request.

    Triggering is a competition between the descriptions listed on the same turn.
    Two close descriptions do not merely cost tokens - they steal each other's
    activations, and neither owner can see it from their own file. This is the one
    defect that is invisible skill by skill and only exists in the set.
    """
    root = ctx.root
    import math
    from collections import Counter

    hidden = listing_hidden_skills(ctx, skills)
    listed = {n: (sk.get("description") or "") for n, sk in skills.items()
              if n not in hidden and (sk.get("description") or "").strip()}
    if len(listed) < 2:
        report.add("33-description-overlap", "INFO",
                   f"{len(listed)} listed description(s): nothing to compete with.",
                   str(root / ctx.skills_dir))
        return

    names = sorted(listed)
    tfs = [Counter(_overlap_tokens(listed[n])) for n in names]
    df: Counter = Counter()
    for tf in tfs:
        df.update(tf.keys())
    n = len(names)
    idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
    vecs = []
    for tf in tfs:
        v = {w: (1 + math.log(c)) * idf[w] for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({w: x / norm for w, x in v.items()})

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = vecs[i], vecs[j]
            if len(a) > len(b):
                a, b = b, a
            score = sum(x * b.get(w, 0.0) for w, x in a.items())
            if score >= ctx.limits.OVERLAP_THRESHOLD:
                pairs.append((score, names[i], names[j]))
    pairs.sort(reverse=True)

    # The overlap is a proxy; the defect is the model picking the wrong skill. The
    # remedy this check recommends - each description excluding the other - is
    # visible in the text, so the check must see it before firing. Measured
    # 2026-09-23 on one repository: 8 of 9 flagged pairs already excluded each other
    # both ways, all 16 references inside a "Don't use for" clause, and the ninth was
    # the only real gap. Only an exclusion counts: a name mentioned as "see also"
    # separates nothing.
    def excludes(a: str, b: str) -> bool:
        m = ANTI_TRIGGER_RE.search(listed[a])
        return bool(m) and re.search(rf"(?<![\w-]){re.escape(b)}(?![\w-])",
                                     listed[a][m.start():]) is not None

    declared = 0
    for score, x, y in pairs:
        xy, yx = excludes(x, y), excludes(y, x)
        where = str(root / ctx.skills_dir / x / "SKILL.md")
        if xy and yx:
            declared += 1
            report.add("33-description-overlap", "NOTICE",
                       f"`{x}` and `{y}` overlap at {score:.2f}, and each excludes the other: "
                       "separated by declaration, not measured. A selection eval on the pair "
                       "would settle it.", where)
        elif xy or yx:
            src, dst = (y, x) if xy else (x, y)
            report.add("33-description-overlap", "WARN",
                       f"`{x}` and `{y}` overlap at {score:.2f}, and only one side draws the "
                       f"line: `{src}` does not exclude `{dst}`. Add `{dst}` to `{src}`'s "
                       "anti-trigger clause.", str(root / ctx.skills_dir / src / "SKILL.md"))
        else:
            report.add("33-description-overlap", "WARN",
                       f"`{x}` and `{y}` overlap at {score:.2f} (threshold "
                       f"{ctx.limits.OVERLAP_THRESHOLD:.2f}). They compete for the same requests: give each an "
                       "anti-trigger naming the other, or merge them.", where)
    report.add("33-description-overlap", "INFO",
               f"{len(pairs)} confusable pair(s) among {n} listed description(s) at threshold "
               f"{ctx.limits.OVERLAP_THRESHOLD:.2f}, {declared} of them separated by mutual exclusion. "
               "Scored on the listing only - a withheld skill cannot "
               f"steal an activation ({len(hidden)} excluded).", str(root / ctx.skills_dir))
