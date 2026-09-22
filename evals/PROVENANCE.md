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
| `anti-trigger-application-code` | 24% | 56% |
| `anti-trigger-diff-review` | 28% | 63% |
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
| 1 | `anti-trigger-application-code`, `anti-trigger-diff-review` | Anti-triggers are the only real test of the relational property, and one of them already fails |
| 2 | `two-skills-compete`, `exemption-request` | Both describe situations that occur in real repositories and can be sourced from one |
| 3 | `budget-growth`, `description-authoring`, `plugin-container` | Closest to restating the description back to itself |

Until a case is rewritten, it keeps `source: skill` and its green result means: *the description is
consistent with itself.* That is worth something, and it is not what an eval is for.
