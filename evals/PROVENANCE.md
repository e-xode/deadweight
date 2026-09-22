# Where these cases come from — and why that limits what they prove

An eval written from the skill's own description is an **echo**: it asks the model what the
description has already told it. It tends to **pass**, which is exactly what makes it dangerous —
it certifies the description against itself. Provenance is therefore not metadata, it is the
single fact that decides how much a green result is worth.

## The finding, measured on 2026-09-22

**All seven cases were written from the skill, by the session that wrote the skill, on the day the
skill was written.** The evidence is unambiguous and reproducible:

```bash
# The prompts appear nowhere in the fleet these checks came from, at any point in its history:
git -C <any consuming repository> log --all -S "Our CLAUDE.md keeps growing" -- .claude   # nothing
# They appear for the first time in this plugin's initial commit:
git log --all -S "Our CLAUDE.md keeps growing" --format="%h %ad %s" --date=short
#   e97676a 2026-09-22 feat: deadweight v0.1.0
```

The motive is on record too: a coverage check (26) reported that a skill without an eval suite
"cannot be shown wrong — it can only be trusted". The suite was written to answer that check.
**A suite written to satisfy a coverage metric, by the author, from the description, is the
textbook shape of a circular corpus.**

## A lexical indicator that does not discriminate — reported, not used

| Case | overlap with the description | overlap with the body |
| --- | --- | --- |
| ~~`anti-trigger-application-code`~~ | 24% | 56% | *(retired 2026-09-22)* |
| ~~`anti-trigger-diff-review`~~ | 28% | 63% | *(retired 2026-09-22)* |
| `budget-growth` | 24% | 71% |
| `description-authoring` | 15% | 70% |
| `exemption-request` | 14% | 51% |
| `plugin-container` | 26% | 59% |
| `two-skills-compete` | 12% | 56% |

Overlap with the description looks reassuringly low. It proves nothing: overlap with the **body**
is 51–71% for every case, because a long body contains almost any technical vocabulary. The
measure separates nothing, so it is recorded and not relied on. The git evidence above is what
carries the claim.

## What is still worth reading in a run

Circularity biases a corpus **towards passing**. So in this suite:

- **a failure is informative** — an echo does not usually fail. The first run already produced one:
  `anti-trigger-application-code` scored 0.00 / 1.00 / 0.00 with the plugin loaded, meaning the
  anti-trigger does not hold two times out of three. A description cannot fail its own echo unless
  something is genuinely wrong with it;
- **a pass is not informative** on its own, and should be read through the **ablation delta**. The
  runner executes a no-plugin baseline arm for every case: a question answerable without the skill
  passes in both arms and its delta is zero. Circularity shows up as an absent difference, not as a
  low score.

## What to do with this file

Nothing is deleted on the strength of provenance alone. The flag says which cases are owed a
rewrite from an **independent source** — real sessions, the git history of a configuration that was
actually repaired, a question someone actually asked — and in what order:

| Priority | Case | Why |
| --- | --- | --- |
| ~~1~~ | ~~`anti-trigger-application-code`, `anti-trigger-diff-review`~~ | **Done 2026-09-22** — see below |
| 2 | `two-skills-compete`, `exemption-request` | Both describe situations that occur in real repositories and can be sourced from one |
| 3 | `budget-growth`, `description-authoring`, `plugin-container` | Closest to restating the description back to itself |

## Priority 1, done — and why the replacements differ in kind (2026-09-22)

The two retired anti-triggers were not only echoes; they were **too easy**. "Refactor our
checkout controller" and "review this diff" sit nowhere near a configuration audit, so they
passed on lexical distance alone. A case that any description passes measures no description.

The independent source is a sample of **15 public Claude Code repositories** cloned and audited
on 2026-09-22 — third-party configurations this plugin had never seen. Two supplied a genuine
near miss:

| New case | Sourced from | Why it is near, not far |
| --- | --- | --- |
| `anti-trigger-scaffolding` | a public bootstrapper whose skill description reads *"generates a complete `.claude/` structure — agents, pipelines, skills, memory, hooks, settings"* | It names every object the auditor audits, in the same container. Only the **verb** separates them: generate vs judge. |
| `anti-trigger-release-packaging` | a public CLI whose release skill *"cuts and ships a release, publishes it, verifies the package index picked it up"* | Packaging is assigned to `skill-creator` by the division-of-responsibilities table, yet this repository visibly owns release machinery — the trap is reasoning from the repo instead of from the skill. |

Neither prompt is quoted from those repositories: the **situation** is borrowed, the wording is
this file's, so nothing of a third party is redistributed here.

**What the replacement is worth is itself measurable.** An anti-trigger case is only load-bearing
if removing the anti-trigger clause from the description makes it fail. That test is the entry
below; a case that survives a deliberately degraded description is decoration, and gets retired
like its predecessors.

Until a case is rewritten, it keeps `source: skill` and its green result means: *the description is
consistent with itself.* That is worth something, and it is not what an eval is for.

## The degradation test, and what it actually measured (2026-09-22)

The replacement cases were to be validated by one criterion: **deliberately degrading the
description must make them fail.** The test was run. It did not answer the question, and the
reason is worth more than the answer would have been.

Three conditions, `--runs 3` per arm, the whole anti-trigger clause removed for the third:

| Condition | `anti-trigger-release-packaging` with / without | `anti-trigger-scaffolding` with / without |
| --- | --- | --- |
| Original description (`packaging skills as a plugin` as a trigger) | 0.33 / 0.67 — **Δ −0.33** | 1.00 / 0.67 |
| Trigger narrowed to `a plugin manifest or marketplace entry`, anti-trigger extended | 0.67 / 0.33 — Δ +0.33 | — |
| **Anti-trigger clause removed entirely** | 1.00 / 1.00 — Δ 0.00 | 1.00 / 0.67 |

Read the `without` column. That arm runs with **no plugin loaded at all**, so no edit to the
description can reach it. It scored 0.67, then 0.33, then 1.00 — a spread of 0.67 on a control
that was never touched. At 3 runs the resolution is one third of a point, so every difference
in the `with` column above is inside the noise.

**The conclusion is therefore about the instrument, not the description.** Two things are real
and one is not:

- **Real, and a defect that was fixed**: the original description offered `packaging skills as a
  plugin` as a trigger, which a release task matches. It is now `a plugin manifest or marketplace
  entry needs checking`, and the anti-trigger names authoring, scaffolding and shipping. The
  defect was found by writing a near-miss case, not by running it.
- **Real, and unresolved**: the one direction the numbers consistently leaned is the
  counter-intuitive one — removing the anti-trigger clause **raised** the score. A plausible
  mechanism exists: a listing that names "build, tag or ship a release" carries that vocabulary
  into retrieval, and negation is the part of a sentence retrieval discards first. If that holds,
  an anti-trigger clause buys its precision by paying in recall — for the wrong task.
- **Not real**: any claim, in either direction, from these numbers. What separates the two is
  sample size, and it is priced: standard error 0.29 at n=3, 0.10 at n=25. Settling this costs
  about **$56** in agent runs (2 cases × 2 arms × 2 conditions × 25 runs).

Until someone pays that, `04-skill-description-antitrigger` says in its own message that it is
doctrine and that the one attempt to measure it was inconclusive. A check that demands a practice
whose benefit is unmeasured should say so in the sentence that demands it.
