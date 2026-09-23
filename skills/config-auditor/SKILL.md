---
name: config-auditor
description: "Audit and govern a Claude Code configuration - a project's (CLAUDE.md, skills, sub-agents, path-scoped rules, hooks, settings and permissions, .mcp.json servers, the always-loaded context budget) or a plugin's (manifest, marketplace entry, the skills it ships). Trigger when authoring or auditing a skill, an agent, a rule or a hook, when a description is written or trimmed, when two skills fire on each other's requests or one never fires, when a hook never runs or a permission rule seems ignored, when an MCP config or settings file is about to be committed, when CLAUDE.md or the context budget grows, when an audit finding is contested, or when asked whether a configuration is sound. Runs scripts/audit.py for the mechanical checks. Do not use to author or scaffold a configuration - it judges one that exists - nor to build, tag or ship a release, review a diff, or write application code."
---

# Config auditor — audit and doctrine for a project's Claude Code configuration

> Owns the rules and audit method for a `.claude/` folder, its `CLAUDE.md`, and a plugin's manifest. Every rule says whether it is Anthropic's documentation, a measurement, or this plugin's house convention. Follows the [AgentSkills.io](https://agentskills.io) open standard for skill interoperability.

## What this skill does (and does not)

| In scope                                                     | Out of scope                                                            |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Rules for writing/editing `CLAUDE.md`                        | Validating modified application code (your own validation agent)                  |
| Anatomy of a project skill (frontmatter, references, budget) | The workflow of drafting and evaluating a new skill (Anthropic's `skill-creator`, where installed) |
| Anatomy of a project sub-agent                               | Git hooks and commit format                                                       |
| Anatomy of path-scoped rules (`.claude/rules/`)              | Framework lifecycle hooks (Vue, React…)                                           |
| Hooks, settings, permissions, MCP servers, plugin manifests  | Skill description optimisation tooling (`skill-creator`, where installed)         |
| Audit checklist + automated `scripts/audit.py`               | Application architecture                                                          |
| Anthropic doctrine: progressive disclosure, agent design     |                                                                                   |

## Division of responsibilities — `config-auditor` ↔ `skill-creator`

**`skill-creator` may not be installed where you are reading this, and absent is a valid state.**
This plugin needs nothing from it and declares no dependency on it: the table below is a routing
hint for projects that have both, not a requirement. A plugin that routes to a skill it does not
ship hands the reader a dangling reference — a human shrugs at one, a model goes looking, and the
cost of looking is unbounded.

`skill-creator` is Anthropic's upstream skill (Apache-2.0). The two are complementary, not
competing: `skill-creator` builds one skill, `config-auditor` judges the configuration a skill
lands in. Load both when authoring a skill; load this one alone when auditing.

| Concern                                                                   | Owner            |
| ------------------------------------------------------------------------- | ---------------- |
| Generic create / evaluate / iterate workflow                              | `skill-creator`  |
| Eval harness, grading, benchmarking, blind A/B comparison                 | `skill-creator`  |
| Description-optimisation loop, packaging a skill for distribution         | `skill-creator`  |
| Description conventions (discriminating, what + when, anti-triggers)      | `config-auditor` |
| Skill naming, placement, folder layout                                    | `config-auditor` |
| `SKILL.md` anatomy and the always-loaded token budget                     | `config-auditor` |
| Skill and agent runtime mechanisms available in Claude Code               | `config-auditor` |
| Configuration anti-patterns                                               | `config-auditor` |
| Post-creation audit and skills-index update                               | `config-auditor` |
| Configuration audit (`scripts/audit.py`), project and plugin alike        | `config-auditor` |
| Anthropic doctrine (model spec, progressive disclosure, agent design)     | `config-auditor` |

When this skill hands off, use the convention: `➜ See skill: <name> — <reason>`.


## Core rules (the strict minimum)

1. **`CLAUDE.md` ≤ 12 KB / ~3000 tokens, and ≤ 200 lines.** Hard rules only; knowledge belongs in skills. The 200-line figure is Anthropic's (`01-claude-md-lines`); the byte ceiling is this plugin's house proxy (`01-claude-md-size`), movable per project through the overlay. Why each number is what it is: [references/claude-md-anatomy.md](./references/claude-md-anatomy.md).
2. **One skill = one subject.** Discriminating description saying what it does and when, in the third person, with explicit anti-triggers. Current models over-trigger on shouted imperatives: write "use when…", not "MUST use". See [references/skill-anatomy.md](./references/skill-anatomy.md).
3. **`SKILL.md` is method + index.** Knowledge goes in `references/`, one level deep. Under **~500 lines** (Anthropic) **and ~20 KB** (effective): after compaction the re-attached body keeps only its start, so what lies past it stops applying while the file looks intact (`21`). Front-load rules and routing. Details: [references/skill-runtime-mechanisms.md](./references/skill-runtime-mechanisms.md).
4. **Sub-agents have a strict contract:** an objective, an output format, the tools and sources to use, clear boundaries, a structured return. See [references/agent-anatomy.md](./references/agent-anatomy.md).
5. **No duplication between skills.** Search existing skills before authoring a new one. If overlap is unavoidable, both twin skills carry a "Division of responsibilities" table, each table has a row owned by the twin, and the concern text of the row naming the pair reads identically on both sides (the tables themselves are family-wide and may differ elsewhere — see antipattern B6); each side's anti-trigger arrow still points at the other for routing.
6. **One declared language** for persisted artefacts. House convention (checks `11`, `14-rule-english-only`), exemptable per file through the overlay: a mixed-language configuration is harder to audit, not wrong.
7. **No code comments in `CLAUDE.md` or `SKILL.md`** outside fenced code blocks. Prose is the medium.
8. **Cross-references use a stable convention:** `➜ See skill: <name> — <reason>` (greppable, visible in diffs).
9. **`name` in frontmatter == folder name.** Mechanical, enforced by `scripts/audit.py`.
10. **Hooks execute — audit them before anything that is only read.** An event name that does not exist, an `if` on a non-tool event, a bare `mcp__<server>` matcher: each never fires and never says so (`35-*`). What a hook prints on `SessionStart`, `UserPromptSubmit`, `UserPromptExpansion` or `PostModelSwitch` enters the context of every session. House convention: a hook that adds time to every task (a test suite on `Stop`) is refused; placing a hook is the maintainer's decision, never an agent's. Details: [references/hooks-anatomy.md](./references/hooks-anatomy.md).
11. **Scripts belong to a skill.** House convention (`13-no-global-scripts`, WARN): executable tooling lives in `.claude/skills/<owner>/scripts/`, so it travels and retires with the skill that runs it.
12. **Description = trigger surface.** Triggers + anti-triggers only; knowledge belongs in the body. Skill descriptions **80–1,024 chars** (the spec's cap on the field); **1,536** is the listing cutoff for `description` + `when_to_use` together, not a field cap. Agent descriptions 80–900 (house). Most important trigger first: [references/skill-anatomy.md](./references/skill-anatomy.md).
13. **Rules are lightweight guardrails.** `.claude/rules/` files are path-scoped constraints (< 2 KB, imperative, no references). They complement skills (which carry knowledge). Use rules for hard DON'Ts tied to specific file paths; use skills for how-to procedures. See [references/rules-anatomy.md](./references/rules-anatomy.md).
14. **Domain prefixes:** a skill scoped to one area of the project carries its area as a prefix. The worked example used throughout these references is a fictional shop: `shop-*`, `ui-*`, `api-*`, `data-*`. Cross-cutting skills (`translate`, `review`, `release`, `skill-creator`, `git-workflow`, this one) take none. A project-scoped skill keeps its project prefix even inside a go-to-market topic (`shop-onboarding-email`).
15. **Always-loaded budget — measured, never extrapolated.** `CLAUDE.md` + every _listed_ skill description + every agent description load every turn; `17` caps the sum at 43,000 / 47,000 chars. **A house ratchet, not Anthropic guidance**: the harness sizes its own listing budget from `skillListingBudgetFraction` (`29`). Re-measure with `/context` and `/skill-doctor` after any listing change.
16. **The ratchet, not the report.** A measurement with no floor is a measurement people learn to ignore. `--set-floor` freezes the counts, `--check-floor` fails when they rise, and the floor carries the **sha of `audit.py`**: the comparison refuses to run across two instruments, because a count taken with a different auditor is a different measurement, not a better state. Run it in CI.
17. **Check ids are a compatibility surface.** A consuming project names them in its `.claude/audit.local.json`, so they are never renamed — an id that must change gets an entry in `CHECK_ID_ALIASES` and the old one keeps working, for good.
    On overflow the harness keeps every skill **name** and drops **descriptions, least-invoked first** — degradation, not a cliff. Three levers keep a **project** skill out of the starting listing: `disable-model-invocation` (name goes too), `skillOverrides` (`name-only` drops the description; `user-invocable-only` and `off` drop the name as well), and `paths:` — absent at start, loaded when a matching file is read (measured on 2.1.280, and what the docs say); all three are audit-aware. **None of them reaches a plugin skill** — measured 2026-09-22, both with and without the `<plugin>:` prefix on the key, against a project skill that the same setting did remove. A consuming project's only lever on a plugin skill is disabling the whole plugin, so a plugin's listing cost is a tax its consumers cannot negotiate: write the description short because nobody downstream can trim it. **Every withheld skill the model cannot come upon by itself must be named in the `CLAUDE.md` Skills index — and only those** (house convention, `15`): a `paths:` skill surfaces on its own and is not required there. Levers, overflow rule and the measured `/context` figures: [references/skill-runtime-mechanisms.md](./references/skill-runtime-mechanisms.md).

## Audit method

Run before any non-trivial change to `.claude/` and after creating/modifying a skill; run the whole
method on Anthropic's cadence — **every three to six months, and after any major model release**.

### Step 1 — Automated checks

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --json          # adds layout + audit_sha
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --all          # no roll-up: every finding
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --set-floor     # freeze today's counts
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --check-floor   # fail if they rose (CI)
```

**Report every ERROR first, each one by name, before any WARN** — an ERROR is a certain defect,
and a summary that picks the familiar findings drops exactly the surprising ones (a credential
variable read as empty, a component the plugin never loads).

The script's `CHECKS` tuple is the authoritative inventory of what it covers — read it there rather
than trusting a count copied into prose; a clean run prints the number it executed (`Executed N
check groups … All checks passed.`). Most checks report only on failure; the always-loaded budget
always prints its total as INFO. Exit code 1 on any error. A check that fires more than
five times is rolled up in the text report - `--all` or `--json` show every finding, and the
floor always counts every one, because the ceiling is a display decision, not a detection one.

`claude plugin validate --strict <dir>` is the upstream check: it parses manifests, and since
2.1.233 it reports `SKILL.md` frontmatter that does not parse. Run it first and do not duplicate
it; `audit.py` covers what it does not — what the harness ignores **silently**.

### Step 2 — Runtime measurement (after any listing change)

`audit.py` counts characters on disk; nothing static sees what the harness injected. Confirm in a
fresh session:

| Command              | What it answers                                                                                        |
| -------------------- | ------------------------------------------------------------------------------------------------------ |
| `/skill-doctor`      | Per-skill listing cost, 7-day tokens, invocation counts, never-invoked warnings.                       |
| `/doctor`            | Setup checkup: listing cost, top contributors, version drift, **CLAUDE.md trim proposals**.            |
| `/context all`       | Tokenizer-accurate per-skill estimates. Plain `/context` shows the Skills row _after_ budget.          |
| `/skills`            | The listing sorted by estimated token cost.                                                            |
| `/usage`             | Per-category breakdown — skills, subagents, plugins, per-MCP — over 24 h and 7 d.                      |
| `claude --safe-mode` | The baseline arm: the session with **none** of this config — the only way to ask if it earns its keep. |

Invocation counts are the input most projects have never had: without them, every "merge or keep"
argument is intuition. Check 33 gives the static half of that answer — which descriptions compete —
but only a runtime count says which one actually wins. Where a runtime
figure disagrees with the audit's effective total, trust the runtime one and fix the script. Which
release introduced each command: [references/skill-runtime-mechanisms.md](./references/skill-runtime-mechanisms.md) § Measuring the real cost.

### Step 3 — Manual checks

Walk [references/audit-checklist.md](./references/audit-checklist.md). Each item is tagged `[AUTO]` (covered by the script) or `[MANUAL]` — the qualitative half the script cannot see.

### Step 4 — Anti-pattern sweep

Cross-check the work against [references/antipatterns.md](./references/antipatterns.md): most configuration defects are recurring patterns documented there.

### Step 5 — Propose, never auto-fix

If issues are found, propose corrections to the user. **Never silently rewrite** a skill, an agent, or `CLAUDE.md`. The audit script has no `--fix` flag for the same reason.

## Workflows

Step-by-step procedures — create a skill, modify `CLAUDE.md`, add a sub-agent,
introduce a native hook, add or modify a rule: keep them in the project's own
`.claude/audit/decisions.md` or alongside it, not in this skill. They are project
procedure, and a body that carries them drifts past the 20,000-byte compaction
ceiling of core rule 3.

## Where to look (routing table)

| If you need…                                            | Read                                                                                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Why `CLAUDE.md` is so terse / what belongs there        | [references/claude-md-anatomy.md](./references/claude-md-anatomy.md)                                                                                         |
| How to write a discriminating description               | [references/skill-anatomy.md](./references/skill-anatomy.md)                                                                                                 |
| How to choose `tools` / `model` for an agent            | [references/agent-anatomy.md](./references/agent-anatomy.md)                                                                                                 |
| When to use rules vs skills / rule anatomy              | [references/rules-anatomy.md](./references/rules-anatomy.md)                                                                                                 |
| Hooks: events, matchers, `if`, timeouts, exit codes     | [references/hooks-anatomy.md](./references/hooks-anatomy.md)                                                                                                 |
| Settings scope, permission rules, status line           | [references/settings-permissions-anatomy.md](./references/settings-permissions-anatomy.md)                                                                   |
| `.mcp.json`: secrets, credential variables, approvals   | [references/mcp-anatomy.md](./references/mcp-anatomy.md)                                                                                                     |
| Plugin manifest, marketplace, component paths           | [references/plugin-anatomy.md](./references/plugin-anatomy.md)                                                                                               |
| Full audit checklist (auto + manual)                    | [references/audit-checklist.md](./references/audit-checklist.md)                                                                                             |
| Known anti-patterns and corrections                     | [references/antipatterns.md](./references/antipatterns.md)                                                                                                   |
| Why the project is organised this way (its own decisions) | `.claude/audit/decisions.md` — **in the consuming project**, absent by default |
| What each exemption was granted for, and when            | `.claude/audit.local.json` — in the consuming project |
| What the audit reported, run by run                     | the git history of `.claude/audit/floor.json` — timestamped, with an author and a reason |
| Skill/agent runtime mechanisms available in Claude Code | [references/skill-runtime-mechanisms.md](./references/skill-runtime-mechanisms.md)                                                                           |
| Anthropic official documentation                        | [references/official-links.md](./references/official-links.md)                                                                                               |
| The step-by-step procedure for a given change           | the project's own notes — not this skill |
