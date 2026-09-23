<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Skill anatomy

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Contents: [How to read this file](#how-to-read-this-file) · [Where a skill must live](#where-a-skill-must-live) · [Folder layout](#folder-layout) · [Frontmatter](#frontmatter) · [`description` rules](#description-rules) · [`SKILL.md` body](#skillmd-body) · [`references/` rules](#references-rules) · [Scripts](#scripts) · [Evals](#evals) · [When to split a skill](#when-to-split-a-skill) · [Retiring a skill](#retiring-a-skill) · [Anti-triggers, in practice](#anti-triggers-in-practice) · [Tone of a description](#tone-of-a-description)

## How to read this file

Every rule carries one of three labels. **Doc**: an Anthropic page says it, and the link is given.
**Measured**: not documented; observed on a stated Claude Code version with a stated protocol.
**House convention**: this plugin's choice, with its reason — a consuming project may exempt it
through its `.claude/audit.local.json`. The runtime details (all twenty frontmatter fields,
visibility levers, lifecycle) live in [skill-runtime-mechanisms.md](./skill-runtime-mechanisms.md).

## Where a skill must live

**Doc.** Claude Code finds skills **by location, not by content**: `~/.claude/skills/<name>/SKILL.md`
(personal), `.claude/skills/<name>/SKILL.md` (project, and nested copies below it), a directory
passed with `--add-dir`, the managed-settings directory, and `<plugin>/skills/<name>/SKILL.md`
([skills § Choose where skills load](https://code.claude.com/docs/en/skills)). A plugin manifest is
optional: without one, components are auto-discovered in their default folders
([plugins-reference](https://code.claude.com/docs/en/plugins-reference)).

Consequences:

- A `<name>/SKILL.md` folder at the **root** of a repository loads nowhere — not as a project skill,
  not as a plugin skill. `40-skill-not-loaded` reports it.
- **Measured** (2026-09-23, 2.1.280): a `skills/<name>/SKILL.md` tree loads under
  `claude --plugin-dir <repo>` even with no `.claude-plugin/plugin.json`. Protocol: a repository
  holding only `skills/shop-probe/SKILL.md`, started with `--plugin-dir`, then the probe looked up
  in the session's skill list. The docs say only that the manifest is optional; that this layout is
  enough on its own is the measured part.
- **Doc.** Never name a skill folder `synced`, in any capitalization: Claude Code reserves
  `~/.claude/skills/synced/` for skills downloaded from claude.ai and skips an authored skill of that
  name ([skills § Choose where skills load](https://code.claude.com/docs/en/skills)).

## Folder layout

```
.claude/skills/<skill-name>/
├── SKILL.md            (required)
├── references/         (optional: detail loaded on demand)
│   ├── <topic-1>.md
│   └── <topic-2>.md
├── scripts/            (optional: executable tooling)
└── assets/             (optional: files used in output)
```

- **Doc.** `SKILL.md` is required; the other folders are recommendations
  ([agentskills.io specification](https://agentskills.io/specification)). `02-skill-md-exists`.
- **House convention: domain prefix.** A skill scoped to one area carries it as a prefix — `shop-*`,
  `ui-*`, `api-*`, `data-*` in the worked example. Cross-cutting skills (`translate`, `release`) take
  none. Reason: a prefix makes the owner of a file surface visible at a glance, in the listing, the
  `/` menu and every `➜ See skill:` pointer.

## Frontmatter

```yaml
---
name: shop-checkout
description: '<single string, no line breaks>'
---
```

**What is required depends on the target** — say which one you author for:

| Target | Required | Source |
| --- | --- | --- |
| Claude Code | nothing: every field is optional. `name` defaults to the folder name; a missing `description` falls back to "the first non-empty line of the markdown content" | [skills § Frontmatter reference](https://code.claude.com/docs/en/skills) |
| Agent Skills spec (claude.ai upload, Skills API, `package_skill.py`) | `name` **and** `description` | [agentskills.io specification](https://agentskills.io/specification) |

`02-skill-frontmatter` demands both, because a skill that loads in Claude Code but fails on upload is
a latent defect (house convention, aligned on the stricter target).

**`name` rules** — **doc**: at most 64 characters, lowercase letters, digits and hyphens, no leading,
trailing or doubled hyphen, must match the parent folder
([specification](https://agentskills.io/specification)); no XML tags, and never the reserved words
`anthropic` or `claude`, which claude.ai and the Skills API reject
([platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).
Checks: `32-skill-name-shape`, `32-skill-name-reserved`, `03-skill-name-matches-folder`,
`06-skill-duplicate-name`. For a personal or project skill the typed `/command` comes from the
folder, not from `name` ([skills § How a skill gets its command name](https://code.claude.com/docs/en/skills)).

**Silent failures** — **doc**: a frontmatter block is read only when the opening `---` is the file's
first line; if the YAML does not parse, the skill still loads "with no fields set", so `/name` works
but Claude cannot match its description ([skills § Skill not triggering](https://code.claude.com/docs/en/skills)).
`claude plugin validate .claude/skills` lists the `SKILL.md` files whose frontmatter does not parse
(2.1.233+). **Measured, not documented** (2026-09-23, 2.1.280): an unknown key is ignored without
error — a probe `SKILL.md` carrying `trigger-words:` passed `claude plugin validate` with no warning.
`02-skill-unknown-field` is the only thing that will tell you; `02-skill-frontmatter` catches the
unparseable block.

### Two caps, two documents

| Number | What it caps | Source |
| --- | --- | --- |
| **1,024** | `description` **alone** — spec cap; past it, upload and packaging fail. | [platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) |
| **1,536** | `description` **+** `when_to_use` combined — truncation in the Claude Code listing, nothing else; configurable with `skillListingMaxDescChars`. | [skills § Frontmatter reference](https://code.claude.com/docs/en/skills) |

**Author against 1,024**: a 1,200-character description passes the listing and still hard-fails on
upload. `04-skill-description-length`. `when_to_use` is appended to `description` in the listing and
counts toward the same 1,536 cap: it buys readability, never budget.

`paths:` does not disambiguate two skills whose descriptions both match: it keeps a skill out of the
starting listing until a matching file is touched. Full account in
[skill-runtime-mechanisms.md § Path-scoped skills](./skill-runtime-mechanisms.md#path-scoped-skills).

## `description` rules

The description is the trigger surface: Claude decides whether to load a skill from it alone.

1. **Doc — what and when, third person.** "Should describe what the Skill does and when to use it";
   "Always write in third person", because the text is injected into the system prompt
   ([platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).
2. **Doc — discriminating.** Name the domain, file types, key concepts and the words a user would
   actually type ([skills § Skill not triggering](https://code.claude.com/docs/en/skills)).
3. **Doc — a little pushy.** skill-creator notes that Claude tends to under-trigger skills and asks
   for descriptions "a little bit pushy" ([anthropics/skills — skill-creator](https://github.com/anthropics/skills)).
   Insistent is defensible; shouted is not — see [Tone](#tone-of-a-description).
4. **Doc — no XML, no angle brackets.** The spec forbids XML tags in `description`; skill-creator's
   `quick_validate.py` rejects any `<` or `>`. Claude Code loads it anyway, which is why
   `04-skill-description-brackets` warns rather than errors.
5. **House convention — anti-triggered.** End with a `Don't use for:` clause naming the right
   alternative. Reason: a near-miss request is where two skills collide, and the clause is the only
   text that separates them. `04-skill-description-antitrigger` (WARN); `33-description-overlap`
   flags pairs of descriptions that compete.
6. **House convention — 80 to ~500 characters.** Under 80 carries no discriminating term
   (`04-skill-description-length` also enforces the floor); over ~500 is usually knowledge that
   belongs in the body. Every listed description is paid on every turn: `17-always-loaded-budget`
   caps `CLAUDE.md` + listed skill descriptions + agent descriptions at 43,000 chars WARN / 47,000
   ERROR — a house ratchet, not an Anthropic figure.

**Doc — what triggering can and cannot do.** "Claude only consults skills for tasks it can't easily
handle on its own" (skill-creator): a one-step request ("read this file") may not load a skill
however good its description is. Test triggering with substantive requests.

Before trimming a description a third time, ask whether it should be listed at all. A skill reached
only through an explicit pointer pays for a trigger surface nobody uses: withhold it
(`disable-model-invocation`, or a `skillOverrides` entry) — see
[skill-runtime-mechanisms.md § Listing visibility](./skill-runtime-mechanisms.md#listing-visibility-and-the-budget).

### Description example (good)

```
description: "Enforces design-system-first SCSS in the shop front end. Use before touching any
.scss file, theme override, mixin, Sass token or page stylesheet; pushes back on bespoke SCSS when
a design-system component, prop, utility or token already solves the problem. Don't use for: plain
CSS outside the design system (→ ui-css), accessibility audits (→ ui-a11y), or component prop
decisions (→ ui-components)."
```

### Description example (bad)

```
description: "Helps with SCSS."
```

Why it fails: no trigger terms, no file surface, no anti-trigger, nothing that separates it from
`ui-css`.

## `SKILL.md` body

- **Doc — under 500 lines** ([platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).
- **Doc-derived — ideally under ~20 KB.** After auto-compaction Claude Code re-attaches only the
  first 5,000 tokens of each invoked skill ([skills § Skill content lifecycle](https://code.claude.com/docs/en/skills));
  past that point the text silently stops applying. `21-skill-md-compaction` warns;
  `05-skill-md-size` errors at 50 KB (house ceiling).
- **Doc — method plus index.** `SKILL.md` "serves as an overview that points Claude to detailed
  materials as needed" (platform best practices). Critical rules stay in the body: a reference may
  never be opened on a cheap task.
- **House convention — sections.** Lead paragraph (what the skill owns); in/out scope table; a
  division-of-responsibilities table for twin skills; core rules; one numbered workflow per task
  with `➜ See skill: <name>` handoffs; a routing table to `references/`. Reason: the same shape in
  every skill makes a missing section visible. `15-skill-index` reconciles the `CLAUDE.md` skills
  index; `28-skill-anchors` checks that paths the body names still exist.

## `references/` rules

- **Doc — one level deep.** Every reference is linked directly from `SKILL.md`, so Claude reads
  whole files instead of following chains (platform best practices). `25-orphan-reference` flags a
  reference `SKILL.md` never names.
- **Doc — table of contents past 100 lines** (platform best practices). skill-creator repeats it
  for files over 300 lines: "include a table of contents" — it does not say split.
- **House convention — split past ~300 lines, one topic per file.** Reason: a reference is read
  whole when opened, so one bloated file makes every consult pay for every topic in it; two
  focused files let Claude open only the one it needs. `16-reference-size` warns at 100 lines
  without a `Contents:` block, and at 300 lines even with one.
- **No frontmatter** in references — they are not skills.

## Scripts

**Doc** ([platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices),
[agentskills.io — Using scripts](https://agentskills.io/skill-creation/using-scripts)):

- **Solve, don't punt.** A script handles its error conditions itself instead of failing and
  leaving Claude to improvise.
- **No voodoo constants.** Every timeout, retry count or threshold is justified in a comment or the
  docs: "If you don't know the right value, how will Claude determine it?"
- **Forward slashes** in every path, even on Windows.
- **Say whether the script is executed or read.** "Run `scripts/check_stock.py`" (its output
  enters context, its source does not) versus "See `scripts/check_stock.py` for the algorithm".
- **Non-interactive**, with a `--help` that documents flags and exit codes: an agent cannot answer
  a TTY prompt.

**Doc — review `allowed-tools`.** Workspace trust does not gate a project skill's `allowed-tools`:
it applies even in a `-p` run in a never-trusted folder, so read that field in any committed skill
before running Claude Code there ([skills § Pre-approve tools](https://code.claude.com/docs/en/skills)).

**House conventions**, each with its reason:

- **A script belongs to one skill** — the one whose body documents its method — so it travels and
  retires with that skill. No top-level `.claude/scripts/` pool: `13-no-global-scripts`.
- **Sharing is by path, never by copy.** Example: `shop-catalog` owns
  `scripts/validate_sku.py`; `shop-import` calls `.claude/skills/shop-catalog/scripts/validate_sku.py`
  and documents that dependency in its own body. In a plugin, reference shared files through
  `${CLAUDE_PLUGIN_ROOT}`, which the docs name for exactly this
  ([skills § Available string substitutions](https://code.claude.com/docs/en/skills)).
- **Stdlib first, shebang, executable bit, exit 0 on success.** A dependency is a failure on the
  next machine.
- **No `--fix` by default** in audit scripts: they propose, the user applies.

## Evals

**Doc** ([platform best practices § Build evaluations first](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices),
[agentskills.io — Evaluating skills](https://agentskills.io/skill-creation/evaluating-skills)):
run representative tasks **without** the skill first and write down what fails; build **at least
three** scenarios from those failures; measure the baseline without the skill; write the minimum
instructions that pass; iterate against the baseline. An assertion that passes in both
configurations proves nothing and should go. Checks: `26-evals-count`, `26-evals-coverage`,
`26-evals-schema`, `26-evals-anti-trigger`, `26-evals-id-type`.

## When to split a skill

Split when the skill covers **two domains** (REST and socket events → `api-express` and
`api-socket`), when the body passes 500 lines and its parts trigger independently, or when two parts
have different triggering profiles. Do **not** split when the parts always load together (the
split costs context for nothing) or are chapters of one procedure (use `references/`). House
convention; the 500-line figure is Anthropic's.

## Retiring a skill

**Doc — the signal that matters most.** "If the agent already handles the entire task well without
the skill, the skill may not be adding value"
([agentskills.io — Best practices](https://agentskills.io/skill-creation/best-practices)). A skill
whose baseline run passes its own evals is a retirement candidate, whatever else is true; re-run
the baselines after every major model release.

**House convention — three corroborating signals**, each measurable with no new tooling:

| Signal | How it is measured |
| --- | --- |
| Nobody names it | no `➜ See skill: <name>` pointer anywhere, absent from the `CLAUDE.md` skills index |
| Its anchors are dead | paths its body names no longer exist (`28-skill-anchors`) |
| It has not moved | no commit on its folder for 3 months (`git log -1 --format=%ar -- .claude/skills/<name>`) |

A skill nobody names but whose evals show a gain over the baseline is reached by its description —
which is how a skill is meant to be reached. Keep it.

**The procedure — two steps, never one.** (1) Set its `skillOverrides` entry to `"off"` in
`.claude/settings.json`: it leaves the listing and the `/` menu without being deleted, and any
pointer still aimed at it starts failing visibly. (2) After two weeks with no request for it,
delete the folder and every pointer to it; `18-see-skill-target`, `24-settings-skill-overrides`
and `15-skill-index` catch what is left. Step 1 is reversible; step 2 is not. Doing both at once
turns a measurement into a bet.

## Anti-triggers, in practice

The clause is the **last sentence** of the description, prefixed `Don't use for:`, and every entry
points somewhere — a skill, an agent, or "framework concept":

```
Don't use for: stock reconciliation (→ data-inventory), payment provider webhooks (→ api-payments
agent), or Vue lifecycle hooks (framework concept).
```

## Tone of a description

**Doc.** Recent models are "more responsive to the system prompt": prompts written to fight
under-triggering now over-trigger, and the fix is to "dial back any aggressive language" — where you
might have written "CRITICAL: You MUST use this tool when…", "you can use more normal prompting
like 'Use this tool when…'"
([platform — prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)).
skill-creator says the same of skill bodies: "If you find yourself writing ALWAYS or NEVER in all
caps … that's a yellow flag" — explain the reason instead.

In practice: open with what the skill does, then "Use when…" / "Use before touching…". A
description that is a little insistent about its scope (item 3 above) remains defensible; capitals,
`MUST use` and `CRITICAL` are not a way to raise priority. If breaking a skill's rule produces a
defect in committed code, say **why** in one clause ("…because the checkout total is computed
server-side") — the reason carries the weight the capitals used to fake.
