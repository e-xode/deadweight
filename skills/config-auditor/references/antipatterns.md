<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Anti-patterns (observed in this project or seen elsewhere)

Each anti-pattern includes a **symptom**, a **why it is bad**, and a **correction**.

Contents: [A. `CLAUDE.md`](#a-claudemd) · [B. Skills](#b-skills) · [C. Sub-agents](#c-sub-agents) · [D. Native hooks](#d-native-hooks) · [E. Workflow / process](#e-workflow--process) · [F. Rules (`.claude/rules/`)](#f-rules-clauderules) · [G. Settings](#g-settings)

## A. `CLAUDE.md`

### A1. Pasting a skill's intro into `CLAUDE.md`

- **Symptom.** A new `## SSR` section appears in `CLAUDE.md` with two paragraphs explaining when to use `onMounted`.
- **Why bad.** Costs tokens on every turn for content the agent only needs occasionally. Duplicates the `shop-ssr` skill.
- **Fix.** Delete the section. The harness already lists the skill's description every turn; the agent will load the body on demand.

### A2. Decorative emojis or "Tips" sections

- **Symptom.** "💡 Tip: prefer computed over watch".
- **Why bad.** Tips are best practices, not hard rules. Hard rules only in `CLAUDE.md`.
- **Fix.** Move the tip into the relevant skill (e.g., `ui-composition`).

### A3. Skills index that copies the harness listing

- **Symptom.** The `CLAUDE.md` Skills index carries a row per skill — family groupings, one-liners, or full trigger descriptions.
- **Why bad.** The harness lists every skill's name and description each turn already, so the index pays for that surface twice and rots on the next rename. Since 2026-09-03 the index has exactly one job.
- **Fix.** Keep only the skills deliberately **withheld** from the listing (`disable-model-invocation`, or `skillOverrides` ≠ `on`) — one of those, unnamed, is unreachable. Delete every other row; `audit.py`'s `15-skill-index` check flags the strays ("the index carries withheld skills only").

## B. Skills

### B1. Vague description

- **Symptom.** `"Helps with UI components."`
- **Why bad.** Will never trigger reliably and will not discriminate from `ui-composition` or
  `ui-components`.
- **Fix.** State framework version, file paths, in-house systems, trigger keywords, anti-triggers.

### B2. Missing anti-trigger clause

- **Symptom.** Description lists triggers but no `Don't use for: …`.
- **Why bad.** Skill triggers on adjacent topics, conflicts with neighbouring skills.
- **Fix.** Append a `Don't use for:` clause naming the alternative skill / agent.

### B3. Rule lives only in a reference

- **Symptom.** A hard rule (e.g., "never use window at top level") is mentioned only in `references/ssr-pitfalls.md`.
- **Why bad.** References are loaded on demand. If they are skipped, the rule is invisible.
- **Fix.** Surface the rule briefly in `SKILL.md` with a pointer.

### B4. `SKILL.md` is the encyclopedia

- **Symptom.** `SKILL.md` is 1200 lines, contains 30 examples, no `references/`.
- **Why bad.** Always-loaded body explodes context.
- **Fix.** Move examples to `references/`. Keep `SKILL.md` as method + index. Aim for ≤ 500 lines.

### B5. Trimming a description that should not be listed at all

**Symptom.** The same handful of descriptions get shaved every few months and the aggregate creeps back. The trims are real but the structure is not addressed.
**Fix.** Ask whether the skill is ever selected _semantically_. One reached only through an explicit pointer — an agent body, a CLAUDE.md row — pays every turn for a trigger surface nobody uses. Withhold it (`disable-model-invocation`, or `skillOverrides: name-only`) and the cost is gone permanently. Trim what competes for selection; withhold what does not.

### B6. Twin skills without a "Division of responsibilities" table

- **Symptom.** Two skills cover related topics; neither says which owns what.
- **Why bad.** Agent picks one and ignores the other.
- **Fix.** Add a `Division of responsibilities` table on both sides. Each table carries a row owned by the twin, and the concern text of the row naming the pair reads identically in both files; the rest of each table is family-wide and may differ. `audit.py` check 27 asserts exactly that — presence, the twin's row, and the shared row's text — nothing more, because 45 mutually anti-triggering pairs share family tables that cannot all be row-identical.

### B7. `SKILL.md` over the compaction slice (~20 KB)

- **Symptom.** A `SKILL.md` sits comfortably under `audit.py`'s 50 KB error and under 500 lines, and behaviour still degrades once a long session compacts.
- **Why bad.** Compaction re-attaches only the **first 5,000 tokens** (≈ 20 KB) of each invoked skill, keeping the start. Everything past that stops applying, silently, mid-task — and the reader has no signal, because the file on disk is intact. The 50 KB threshold is 2.5× the real ceiling.
- **Fix.** Treat ~20 KB as the working ceiling. Front-load the rules and the routing table; move catalogues, examples and enumerations into `references/`, which load on demand and are never subject to the re-attach cap. When a body genuinely cannot fit, split the skill by triggering profile.

### B8. One anchor block duplicated across a skill family

- **Symptom.** Every `ui-*` skill opens with the same paragraph of project anchors — the framework versions, the SSR flag, the "prefer primitives before bespoke styles" line — restated in each body.
- **Why bad.** The family shares one truth with N copies. When the framework version or the plugin order changes, the copies drift apart and the reader cannot tell which is current; and a session that loads three of them pays for the same paragraph three times.
- **Fix.** One home per fact. Keep the anchor block in the family's entry-point skill (`ui-overview` in the worked example), and in the siblings replace it with a one-line pointer: `➜ See skill: <family-entry-point> — project anchors and plugin wiring.` Same remedy as B6, applied to a family instead of a pair.

## C. Sub-agents

### C1. Sub-agent runs validation

- **Symptom.** The `vue` agent runs `npm test` after editing a component.
- **Why bad.** Violates the centralised-validation rule.
- **Fix.** Remove validation calls. Orchestrator delegates to `hooks` after return.

### C2. Sub-agent delegates to another sub-agent

- **Symptom.** The `design` agent calls the `server` agent to fix an SSR error.
- **Why bad.** Sub-agents stay flat; the orchestrator owns delegation.
- **Fix.** Report the error in structured return; orchestrator decides the follow-up.

### C3. Agent body restates its own skill

**Symptom.** The agent paraphrases a skill it also names as the source of truth, so the two drift and the reader cannot tell which wins.
**Fix.** Name the skill in the agent's `skills:` field — the full body is injected at startup — and delete the paraphrase. Keep in the body only what the skill does not own. Note that a skill carrying `disable-model-invocation: true` cannot be preloaded; those must be read by path.

### C4. A read-only agent that fans out to a writable one

**Symptom.** An agent advertises itself as read-only, then spawns `general-purpose` workers that carry `Edit` and `Write`. The guarantee ends at the first hop.
**Fix.** Fan out to an agent type with the same envelope, and say so in the body. A guarantee that only the prompt enforces is not a guarantee.

### C5. Out-of-scope edits

- **Symptom.** Sub-agent fixes a "while we're at it" bug in an unrelated file.
- **Why bad.** Inflates the diff, breaks the orchestrator's mental model.
- **Fix.** Report discovery in structured return. Orchestrator dispatches separately.

### C6. Agent body restates CLAUDE.md hard rules

**Symptom.** An agent body opens by repeating "no code comments", "English only", "never commit without asking" — rules the agent already receives.
**Why bad.** Every custom sub-agent is given the whole `CLAUDE.md` hierarchy at startup. The restatement buys nothing, costs tokens on every dispatch, and creates a second copy that will eventually contradict the first — at which point nobody can say which one the agent followed. (The two exceptions are `Explore` and `Plan`, which skip `CLAUDE.md`; a rule they must honour goes in the delegation prompt, not in an agent file.)
**Fix.** Delete the restatement. Keep in the body only what `CLAUDE.md` and the agent's `skills:` preload do not already carry: the agent's scope, its return shape, and the domain judgement nobody else owns. This is C3's sibling — C3 duplicates a _skill_, C6 duplicates `CLAUDE.md`.

### C7. Agent description front-loads _how_ instead of _when_

**Symptom.** A description opens with the agent's method — "Runs a render-critique-refine loop, rasterizing each draft before returning" — and reaches the delegation trigger, if at all, in its last clause.
**Why bad.** The description is read every turn to answer exactly one question: _should I route this request here?_ Method text answers a question nobody asked at routing time, while the trigger keywords that would earn the dispatch sit past the point where attention has moved on. Combined agent descriptions are also budgeted upstream (a startup warning past 15,000 tokens), so words spent on method are words not spent on discrimination.
**Fix.** Lead with the trigger surface — domain, file paths, the verbs a user would type — then the anti-triggers. Method belongs in the body, which loads only once the agent is actually dispatched.

## D. Native hooks

### D1. Reintroducing native hooks ad hoc

- **Symptom.** A `PreToolUse`/`PostToolUse`/`Stop` hook appears in `.claude/settings.json`, e.g. re-running `eslint` after every Edit or re-adding a Stop-time validation chain.
- **Why bad.** A per-edit hook is slow and noisy, and it duplicates a validation path the project
  usually already has — a request-gated agent, or a rule. It adds time to every task, including the
  ones that did not need it.
- **Fix.** Treat any new hook as an architecture decision — explicit approval from the maintainer,
  recorded in the project's own `.claude/audit/decisions.md` — never an ad-hoc addition. An
  observation hook that only measures and reports is the exception: it blocks nothing.

### D2. Enabling agent teams with a named-subagent fleet

- **Symptom.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is exported "to try the new orchestration", in a project whose every delegation names its agent type.
- **Why bad.** Two documented behaviours combine badly here. While the flag is on, **a named subagent launches as a teammate** instead of a sub-agent — so every dispatch changes shape — and **teammates ignore a definition's `skills:` field**. Twelve of the fourteen agents get their domain knowledge from that preload; they would run stripped of it, silently, with no error and no marker in the output. The failure looks like the model getting worse, not like a config change.
- **Fix.** Leave it off. If teams are ever wanted, treat it as an architecture decision with a case study, and re-derive how each agent gets its knowledge without `skills:` first. ➜ See [agent-anatomy.md](./agent-anatomy.md) § Agent teams.

## E. Workflow / process

### E1. Editing locale JSON directly

- **Symptom.** Orchestrator edits `src/translate/en.json` directly to add a key.
- **Why bad.** Locale files must stay in sync; the `translate` agent enforces this.
- **Fix.** Delegate to the `translate` agent.

### E2. Validating after every micro-change

- **Symptom.** Orchestrator runs `npm test` after each `edit` call.
- **Why bad.** Violates "validation is centralised at task end". Wastes time.
- **Fix.** Make all changes, then delegate validation to the `hooks` agent at task end (measured 2026-09-20: the only hooks here are observation hooks — nothing validates automatically).

### E3. Patching a regression instead of auditing

- **Symptom.** A CSS regression appears; fixer adds `!important` to override it.
- **Why bad.** Violates the Golden Rule. Cause remains; debt doubles.
- **Fix.** Apply the 6-step regression protocol from `shop-known-issues`.

### E4. Global script pool (`.claude/scripts/`)

- **Symptom.** Scripts placed in a top-level `.claude/scripts/` folder, not attached to any skill.
- **Why bad.** Violates Anthropic's official skill anatomy. Orphan scripts have no owner, no documentation, no skill-trigger.
- **Fix.** Move each script under the owning skill: `.claude/skills/<owner>/scripts/<script>`. Enforced by `scripts/audit.py` check #13.

## F. Rules (`.claude/rules/`)

### F1. Rule that duplicates a skill's body

- **Symptom.** A rule file contains 40 lines explaining SSR architecture.
- **Why bad.** The rule loads on every matching file, duplicating the `shop-ssr` skill.
- **Fix.** Keep only the guardrail in the rule. Let the skill carry the knowledge.

### F2. Unconditional rule that should be in `CLAUDE.md`

- **Symptom.** A rule file has no `paths:` frontmatter.
- **Why bad.** Same cost as `CLAUDE.md` content but less discoverable.
- **Fix.** Move into `CLAUDE.md` or add a proper `paths:` glob.

### F3. Rule too large (should be a skill)

- **Symptom.** A rule file exceeds 2 KB.
- **Why bad.** Rules are designed to be lightweight guardrails.
- **Fix.** Extract knowledge into a skill. Keep only the core constraint in the rule.

## G. Settings

### G1. A settings key that is inert at its scope

- **Symptom.** `.claude/settings.json` carries `permissions.defaultMode: "bypassPermissions"`. Everything behaves as expected, so nobody questions it. In fact **v2.1.257 (2026-09-01) made that key ignored in `.claude/settings.json` and `.claude/settings.local.json`**, exactly like `"auto"`; the posture on this machine came entirely from user-scope `~/.claude/settings.json`.
- **Why bad.** The worst kind of drift: the config _reads_ as the source of a behaviour it no longer causes, so the next reader reasons from a false premise. A fresh clone lands in a different mode than the file promises, and the audit script cannot catch it — `audit.py` validates structure, and the key is structurally perfect. This is the same class as a stale doc, but harder to see, because nothing is broken until someone new checks the repo out.
- **Fix.** Delete the key from project scope and record where the posture actually lives (done 2026-09-03: user scope, or `--permission-mode bypassPermissions` on the command line). Generally: whenever a settings key is copied between scopes, re-read the scope rules for that key after a CLI upgrade — permission semantics have moved more than once. A key that no longer does what it says is worse than an absent one.
