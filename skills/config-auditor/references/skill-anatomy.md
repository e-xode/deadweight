<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Skill anatomy

Contents: [Folder layout](#folder-layout) · [Frontmatter](#frontmatter) · [`SKILL.md` body](#skillmd-body) · [`references/` rules](#references-rules) · [Scripts placement](#scripts-placement) · [When to split a skill](#when-to-split-a-skill) · [Retiring a skill](#retiring-a-skill) · [Anti-triggers, in practice](#anti-triggers-in-practice) · [Trigger-verb tiering](#trigger-verb-tiering)

## Folder layout

```
.claude/skills/<skill-name>/
├── SKILL.md            (required)
├── references/         (optional, recommended for any skill > ~200 lines)
│   ├── <topic-1>.md
│   └── <topic-2>.md
├── scripts/            (optional, deterministic tooling)
└── assets/             (optional, files used in output)
```

- **`<skill-name>` is kebab-case** and matches the frontmatter `name` exactly. Enforced by `scripts/audit.py`.
- **Domain prefix is mandatory** when the skill is scoped to one area of the project — in the worked example below, `shop-*`, `ui-*`, `api-*`, `data-*`. Cross-cutting skills (`translate`, `review`, `skill-creator`, `git-workflow`, this one) take no prefix.

## Frontmatter

```yaml
---
name: skill-name
description: '<single string, no line breaks>'
---
```

Only `name` and `description` are required.

### Truncation budget (official Anthropic)

| Number | What it caps | Source |
| --- | --- | --- |
| **1,024** | `description` **alone** — hard cap of the Agent Skills spec. Past it, upload and packaging fail. | [platform.claude.com — agent-skills/best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) |
| **1,536** | `description` **+** `when_to_use` **combined** — truncation in the skill listing, nothing else. | [code.claude.com — skills](https://code.claude.com/docs/en/skills) |

Two mechanisms, two documents, two pages. **Author against 1,024.** A 1,200-character description
passes the listing and still hard-fails on upload. Table added 2026-09-20: two readers had confused
the two figures that day, one of them the author of this doctrine.

The Agent Skills spec caps `description` at **1,024 characters** — that is the number to author against. The **1,536-character** figure is a different cap: the _listing_ truncation of `description` + `when_to_use` combined, itself configurable through `skillListingMaxDescChars`. A 1,200-char description passes the listing and still hard-fails on upload or packaging. Put the most important trigger information first.

`when_to_use` is a second, separately-named trigger field, appended to `description` in the listing and counted against the **same** 1,536-char cap. It buys readability — "what it is" split from "when to fire" — never budget. Not used here; a description that needs the split is usually a description that needs cutting.

`paths:` scopes _automatic_ activation to a glob list, the same syntax as `.claude/rules/`. It looks like the structural answer to two skills whose descriptions both plausibly match — a boundary that is mechanical instead of semantic. Measured, it does **not** deliver that: a `paths:`-scoped skill is withheld from the listing entirely — name and description — is not invocable by name, and never auto-loads, in headless and interactive sessions alike. It is a **withholding lever, not a disambiguation one, and never a routing lever**. Do not reach for it to separate two skills. Measured both ways and ruled against on 2026-09-09; see [skill-runtime-mechanisms.md](./skill-runtime-mechanisms.md) § Path-scoped skills.

Twenty frontmatter fields exist in total; four of them change what a description costs. Full table, and the six-field spec subset that survives upload or packaging: [skill-runtime-mechanisms.md](./skill-runtime-mechanisms.md).

### `description` rules

The description is the **primary triggering mechanism**. Three constraints:

1. **Discriminating.** State the _exact_ domain, key file paths, key types, and key concepts. Listing 5–10 trigger keywords beats a vague sentence.
2. **Pushy.** Claude under-triggers skills by default. Use phrasings like "Trigger this skill **whenever** the user mentions X, even if they don't say 'skill'" or "Always load X together with Y".
3. **Anti-triggered.** Always include a `Don't use for: ...` clause that points to the correct alternative skill. This both improves precision and aids discovery.

Minimum length enforced: 80 characters. Anti-trigger clause enforced as a warning by `scripts/audit.py`.

### Description budget

The description is the trigger surface, nothing more: triggers + anti-triggers. Enumerated knowledge (entity lists, technique catalogs, option enumerations) belongs in the body or `references/`. Target ≤ 500 chars; only primary routing skills earn more.

Every **listed** description is paid every turn from the shared always-loaded budget (CLAUDE.md bytes + listed skill descriptions + all agent descriptions ≤ 43,000 chars WARN / 47,000 ERROR), audited by `scripts/audit.py`, which prints the effective total as INFO and reports separately how much is withheld.

Before trimming a description a third time, ask whether it should be listed at all. A skill reached only through an explicit pointer — an agent body, a CLAUDE.md row — pays for a trigger surface nobody uses. Withhold it (`disable-model-invocation`, or `skillOverrides: name-only`) and the whole cost disappears. Trim what genuinely competes for semantic selection; withhold what does not.

### Description example (good)

```
description: "Enforce design-system-first SCSS architecture for this project. Use this
before touching any .scss file, design-system theme override, mixin, Sass token, page
stylesheet, or shared style helper. Push back on bespoke SCSS when the design system
components, props, utilities, defaults, or theme tokens already solve the problem.
Don't use for: plain CSS outside the design system (→ ui-css), UX/a11y quality
audits (→ ui-a11y), or component prop/slot decisions (→ ui-components)."
```

### Description example (bad)

```
description: "Helps with SCSS in the project."
```

Why it fails: no triggers, no anti-triggers, no file paths, no discrimination from any other skill.

## `SKILL.md` body

### Target shape

- **≤ ~500 lines, and ideally ≤ 20 KB.** 500 lines is Anthropic's figure. 20 KB is the _effective_ ceiling: after the first auto-compaction only the first 5,000 tokens of an invoked skill are re-attached, truncation keeps the start, and anything past the cut silently stops applying. The 50 KB figure `scripts/audit.py` enforces is a hard error, not the target — a 30 KB `SKILL.md` passes the script and is still half-dropped mid-session.
- **Method + index.** What to do, and where to look for details. Not the encyclopedia itself.
- **Imperative voice.** Same as `CLAUDE.md`.
- **Tables for enumerations** (responsibilities, routing, decision matrices).
- **No code comments** outside fenced blocks.

### Recommended sections (project convention)

1. **Lead paragraph** — what the skill owns in one or two sentences.
2. **In/out scope table** — what belongs here, what is delegated elsewhere.
3. **Division of responsibilities** (only for twin skills, e.g. `config-auditor` ↔ `skill-creator`).
4. **Core rules** — the minimum set to remember without reading references.
5. **Workflows** — one numbered list per common task, with `➜ See skill: ...` handoffs.
6. **Routing table** — "if you need X, read references/Y".

## `references/` rules

- **One topic per file.** If a reference grows past ~300 lines, split it.
- **Table of contents** at the top of any reference > 100 lines.
- **No frontmatter** in references — they are not skills.
- **Heading hierarchy** starts at `#` (top-level), same as `SKILL.md`.
- References are loaded **on demand** — they may be skipped on cheap tasks. Never put a critical rule only in a reference; mention it briefly in `SKILL.md` with a pointer.

## Scripts placement

Skills may bundle executable tooling under `scripts/`:

### Rules

- **Scripts belong to one skill.** The owner is the skill whose body or references document the script's method. Never share a script across skills via a global pool. One sanctioned shared toolbox exists: `shop-art-direction/scripts/` hosts the visual verification tooling (`measure.mjs`, `screenshots.mjs`, `anim-probe.mjs`, `lib/session.mjs`) because that skill owns the charter the tools grade against; `ui-css`, `ui-performance`, `visual-qa`, `shop-known-issues` and `shop-preview-video` consume them by path and never copy them.
- **No `.claude/scripts/` pool.** Top-level `.claude/scripts/` is an anti-pattern. Anthropic's official skill anatomy lists `scripts/` as a **bundled resource of a skill**, not a project-wide directory. `audit.py` check #13 enforces this as an ERROR.
- **Documented in the owning `SKILL.md` or a reference.** A script that no skill calls or describes is orphan code.
- **Stdlib first.** Prefer Python/Bash with no external dependencies.
- **Executable + shebang.** `chmod +x` and a `#!/usr/bin/env python3` / `#!/usr/bin/env bash` line.
- **Exit code 0 on success, 1 on failure.**
- **No `--fix` mode by default.** Audit/validation scripts propose corrections; the user applies them.

## When to split a skill

Split when:

- The skill touches **two distinct domains** (e.g., REST API and Socket events → split into `api-express` and `api-socket`).
- The body exceeds **500 lines** and the topics inside are independently triggerable.
- Two parts have **different triggering profiles**.

Do NOT split when:

- The two parts are always loaded together (split is cosmetic and costs context).
- The "split" is just chapters of the same procedure (use `references/` instead).

## Retiring a skill

Everything above is about birth: when to write a skill, when to split one. Nothing said when to
remove one. Measured 2026-09-20 across the 16 personal repositories
(`git log --diff-filter=A|D --name-only -- '.claude/skills/*/SKILL.md'`): **352 `SKILL.md` created,
8 deleted, 348 live.** A configuration with no retirement procedure does not degrade — it
accumulates. A budget that only ever goes up is not a budget.

### The four signals

A skill is a candidate for retirement when **all four** are true. Each is measurable today, from
this repository, with no new tooling.

| Signal | How it is measured |
| --- | --- |
| Nobody names it | no `➜ See skill: <name>` anywhere in the tree, and absent from the `CLAUDE.md` skills index |
| It has no eval | no `evals/evals.json`, or fewer than 3 cases |
| Its anchors are dead | the paths its body names no longer exist (checked by `audit.py`, check 28) |
| It has not moved | no commit on its folder for 3 months (`git log -1 --format=%ar -- .claude/skills/<name>`) |

Three signals out of four is not a candidate. A skill nobody names by pointer, whose eval passes and
whose anchors are live, is a skill reached by its description — which is how a skill is meant to be
reached.

### The procedure — two steps, never one

1. **Withhold it.** Set its `skillOverrides` entry to `"off"` in `.claude/settings.json`. It leaves
   the listing *and* the `/` menu without being deleted: the description stops costing context on
   every turn, and any pointer still aimed at it starts failing visibly instead of silently.
2. **Wait two weeks.** If nobody asked for it back, delete the folder and remove every
   `➜ See skill:` pointer and index line that named it. `audit.py` catches what is left: check
   `18-see-skill-target` errors on a dangling pointer, `24-settings-skill-overrides` on a
   `skillOverrides` entry naming a folder that no longer exists, and `15-skill-index` warns on an
   index line for a skill that is no longer withheld.

Step 1 is reversible; step 2 is not. Doing both in one move turns a measurement into a bet.

> **This section states the procedure; it authorises no deletion.** Added 2026-09-20 with none
> pending anywhere in the fleet.

## Anti-triggers, in practice

The anti-trigger clause should be the **last sentence** of the description, prefixed with `Don't use for:`. Each anti-trigger must point to the correct alternative (skill, agent, or "this is a framework concept").

```
Don't use for: post-task code validation (→ hooks agent), git commit format (→ git-workflow), or Vue lifecycle hooks (framework concept).
```

## Trigger-verb tiering

Descriptions across the tree open with whatever verb their author reached for, so the listing gives
Claude no signal about which skills are _mandatory_ before touching a file and which are advice.
Three tiers, to apply **on the next touch of a description** — never as a bulk rewrite, which would
churn every skill for no measured gain:

| Tier      | Opening verb | Applies to                                                                                                  |
| --------- | ------------ | ----------------------------------------------------------------------------------------------------------- |
| Mandatory | `MUST use`   | Skills owning a file surface no agent may edit without them: the file-owning `shop-*` and `api-*` skills.   |
| Domain    | `Use for`    | Skills that carry a domain's knowledge but gate nothing: `ui-*`, `data-*`.                                  |
| Advisory  | `Trigger on` | Skills answering a question rather than guarding a file: `shop-lore`, `content-*`.                          |

The tier is a claim about consequence, not importance. If breaking a skill's rule produces a defect
in committed code, it is mandatory; if it produces a weaker answer, it is not.
