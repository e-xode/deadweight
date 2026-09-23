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

## Four cases added on 2026-09-23 — same limit, stated

`mcp-secret-committed`, `permission-rule-inert`, `hook-never-fires` and `anti-trigger-mcp-setup`
were written by the session that wrote the checks they exercise, from the official pages those
checks cite. They are circular in the sense above: they certify that the skill can restate the
documentation, not that it helps on a configuration nobody designed for it. What they add is the
**trigger** half — whether a question about hooks, permissions or MCP reaches this skill at all,
after its description was widened to name them — and a baseline arm that runs without the plugin.

## Cases with real files — `silent-*` and `probe-fixture-visible`, 2026-09-23

The earlier cases paste the configuration into the prompt, so the model reasons on it directly and
the baseline arm does as well (Δ 0 on hooks and permissions). These cases plant two silent defects
in files a `scaffold_script` creates, and ask only "is this configuration sound?". Graded by
`regex`, one grader per defect, no judge. Run with `--scaffold`, 10 runs per arm.

| Case | Defect planted | With plugin | Without |
| --- | --- | --- | --- |
| `silent-agent` | `Agent(<type>)` in a subagent definition (ignored) | 10/10 | 0/10 |
| `silent-agent` | `bypassPermissions` declared by a subagent (not honoured) | 10/10 | 0/10 |
| `silent-settings` | allow rule on a tool that no longer exists | 10/10 | 8/10 |
| `silent-settings` | a managed-only key in the project file | 10/10 | 10/10 |
| `silent-hooks` | `if` on SessionStart | 10/10 | 10/10 |
| `silent-hooks` | bare `mcp__<server>` matcher | 10/10 | 10/10 |

Graders were checked by reading answers: without the plugin, the model does not merely miss the
agent defects — it gives outdated reasons ("subagents generally can't spawn subagents"). The value
of this plugin is where the harness changed after the model's training; where the model already
knows, Δ is 0 — **for that model**.

The same four cases on smaller models (5 runs per arm, `--model sonnet` / `--model haiku`):

| Defect | Default model | Sonnet | Haiku |
| --- | --- | --- | --- |
| `Agent(<type>)` ignored (two wordings) | 10/0 ; 9/7 | 5/0 ; 5/0 | 4/0 ; 4/0 |
| `bypassPermissions` not honoured (two wordings) | 10/0 ; 10/0 | 5/0 ; 5/1 | 5/2 ; 5/0 |
| bare `mcp__<server>` matcher | 10/10 | 5/1 | 5/0 |
| `if` on SessionStart | 10/10 | 5/5 | 5/2 |
| allow rule on a removed tool | 10/8 | 4/0 | 4/0 |
| managed-only key in the project file | 10/10 | 5/3 | 5/0 |

(with plugin / without, out of 10 or 5.) A Δ of 0 on the strongest model is not a case to retire:
it is a case that model no longer needs. Retire one only when its Δ is 0 on every model your
users run. With the plugin, all three models reach 4 or 5 out of 5 on every defect — the plugin's
most concrete effect is to make a cheaper model as reliable as the strongest one on these checks.

Three more cases, default model (10 runs) / Sonnet / Haiku (5 runs), with plugin / without:

| Defect | Default | Sonnet | Haiku |
| --- | --- | --- | --- |
| credential variable read as empty in an MCP header | 10/0 | 3/0 | 2/0 |
| routing variable in the shared `env` | 9/10 | 5/4 | 5/0 |
| component inside `.claude-plugin/` | 10/7 | 5/1 | 3/2 |
| plugin path without `./` | 10/9 | 5/0 | 4/0 |
| `AGENTS.md` beside a `CLAUDE.md` that does not import it | 10/10 | 5/0 | 4/0 |
| `globs:` in a rule | 10/10 | 5/0 | 4/0 |

The weak spot is the WITH arm on small models: `audit.py` reports the empty credential variable
and the misplaced component as ERRORs, and the answer drops them in about half the runs. That is
a relay failure of the skill, not a detection failure of the auditor.

## A relay instruction, tested and withdrawn — 2026-09-23

On small models the answer dropped ERRORs the auditor had printed. A one-line instruction in
`SKILL.md` ("report every ERROR first, by name") was tested as a same-batch A/B: two copies of the
plugin identical but for that line, Haiku, `silent-mcp` + `silent-plugin`, 20 runs each.

| | With the line | Without |
| --- | --- | --- |
| Targeted ERRORs relayed | 31/40 (78 %) | 25/40 (62 %) |
| Failures where `audit.py` did run | 8 | 14 |
| Failures where it did not | 1 | 1 |

+15 points, one-sided Fisher p = 0.11: inconclusive, and the line was withdrawn. It was then
re-tested at a size fixed in advance for a 15-point effect (60 runs per case and per variant, no
interim look):

| Case | With the line | Without |
| --- | --- | --- |
| `silent-mcp` — credential variable read as empty | 45/60 | 28/60 |
| `silent-plugin` — component inside `.claude-plugin/` | 41/60 | 40/60 |
| **Total** | **86/120 (72 %)** | **68/120 (57 %)** |

+15 points, one-sided Fisher p = 0.011: the effect exists, and the line is back in `SKILL.md`.
It is not uniform: the whole gain is on the counter-intuitive defect (+28 points), none on the
misplaced component (+2). An instruction to relay ERRORs helps where the finding contradicts what
the model expects; it does not help where the model reads the finding and judges it minor. The diagnostic grader (`ran-audit`) located the failure: the auditor ran in 77 of
80 runs; the answer summarised it and left the ERROR out. The next lever to test is the tool
output, not the prose.

## A recap of ERRORs at the end of `audit.py`'s output — tested and not adopted

Same design, the relay instruction kept in both variants, only the tool output differing: 45 runs
per case and per variant, Haiku. Relayed: 62/90 (69 %) with a closing "ERRORS TO REPORT" list,
58/90 (64 %) without; one-sided Fisher p = 0.32. On the misplaced component, +6.7 points against a
pre-registered +10. Not adopted: changing the auditor's output would have cost every consumer a
floor re-set for no shown effect. The model reads the finding and judges it minor; formatting does
not change a judgement.
