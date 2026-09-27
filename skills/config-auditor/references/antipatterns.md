<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Anti-patterns

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Each entry gives a **symptom**, **why it is bad**, and a **fix**, and is tagged with its
register: **Universal** (follows from a documented mechanism, source linked) or **House
convention** (this plugin's choice, with its reason — a project may decline it). The check id is
named when `audit.py` detects the pattern.

Contents: [A. `CLAUDE.md`](#a-claudemd) · [B. Skills](#b-skills) · [C. Sub-agents](#c-sub-agents) · [D. Hooks and agent teams](#d-hooks-and-agent-teams) · [E. Layout](#e-layout) · [F. Rules (`.claude/rules/`)](#f-rules-clauderules) · [G. Settings](#g-settings)

## A. `CLAUDE.md`

### A1. Pasting a skill's intro into `CLAUDE.md` — Universal

- **Symptom.** A `## SSR` section appears in `CLAUDE.md` with two paragraphs on when to use `onMounted`.
- **Why bad.** Paid every session for content needed occasionally; duplicates the `shop-ssr`
  skill. [memory](https://code.claude.com/docs/en/memory): a multi-step procedure or something that
  "only matters for one part of the codebase" belongs in a skill or a path-scoped rule.
- **Fix.** Delete the section. The skill's description is already listed; its body loads on demand.

### A2. Tips, FAQ, and emphasis everywhere — Universal

- **Symptom.** "💡 Tip: prefer computed over watch", and half the lines start with "IMPORTANT".
- **Why bad.** [best-practices](https://code.claude.com/docs/en/best-practices): "If you emphasize
  many lines, none of them stands out"; and "If Claude already does something correctly without
  the instruction, delete it or convert it to a hook."
- **Fix.** Apply the per-line test — "Would removing this cause Claude to make mistakes?" Move tips
  into the relevant skill (`ui-composition`); keep emphasis on the one line Claude keeps skipping.

### A3. Skills index that copies the harness listing — House convention (`15-skill-index`)

- **Symptom.** The `CLAUDE.md` skills index carries a row per skill.
- **Why bad.** The harness lists every visible skill's name and description each turn
  ([context-window](https://code.claude.com/docs/en/context-window)); the index pays for that twice
  and rots on the next rename.
- **Fix.** Keep only the skills withheld from the listing (`disable-model-invocation`,
  `skillOverrides`, `paths:`), which nothing else points at. This is the plugin's convention for
  what an index is for, not a documented rule.

### A4. `CLAUDE.local.md` committed — Universal (`01-claude-local`)

- **Symptom.** `CLAUDE.local.md` is tracked by git.
- **Why bad.** [memory](https://code.claude.com/docs/en/memory): it holds "personal
  project-specific preferences; add to `.gitignore`". Committed, one person's sandbox URLs become
  everyone's instructions.
- **Fix.** `git rm --cached CLAUDE.local.md` and ignore it in the repository's `.gitignore`.

### A5. `AGENTS.md` beside a `CLAUDE.md` that does not import it — Universal (`01-agents-md-unread`)

- **Symptom.** A repository shares an `AGENTS.md` with other coding agents and also has a `CLAUDE.md`.
- **Why bad.** [memory](https://code.claude.com/docs/en/memory): by default Claude reads
  `AGENTS.md` only when no `CLAUDE.md` or `CLAUDE.local.md` exists at or above the working
  directory. Everything in it is invisible to Claude.
- **Fix.** Put `@AGENTS.md` at the top of the `CLAUDE.md`, or delete the `CLAUDE.md`.

## B. Skills

### B1. Vague description — Universal

- **Symptom.** `"Helps with UI components."`
- **Why bad.** [skills](https://code.claude.com/docs/en/skills): the description says "what the
  skill does and when to use it"; Claude decides from it. This one says neither, and cannot be told
  apart from `ui-composition` or `ui-components`.
- **Fix.** State the domain, file paths, in-house names and the words a user would type.

### B2. No "Do not use" clause — House convention

- **Symptom.** A description lists triggers but never names what it is not for.
- **Why bad.** The documented requirement is *what + when*. With neighbouring skills, a skill
  also fires on adjacent requests.
- **Fix.** The plugin recommends appending `Do not use for: … (→ <other-skill>)`. It is a useful
  discriminator, not a documented field or rule.

### B3. Rule lives only in a reference — Universal

- **Symptom.** "never use `window` at top level" appears only in `references/ssr-pitfalls.md`.
- **Why bad.** References load on demand; if skipped, the rule is invisible.
- **Fix.** State the rule briefly in `SKILL.md`, with a pointer to the detail.

### B4. `SKILL.md` is the encyclopedia — Universal

- **Symptom.** 1,200 lines, 30 examples, no `references/`.
- **Why bad.** The whole body enters context on invocation.
- **Fix.** Keep `SKILL.md` as method plus index (≤ 500 lines, [skills](https://code.claude.com/docs/en/skills));
  move examples to `references/`.

### B5. Trimming a description that should not be listed at all — House convention

- **Symptom.** The same descriptions are shaved every few months and the total creeps back.
- **Fix.** If a skill is only ever reached by an explicit pointer (an agent body, a `CLAUDE.md`
  line), withhold it (`disable-model-invocation`, `skillOverrides`, or `paths:`) instead of
  trimming. Trim what competes for selection; withhold what does not.

### B6. Twin skills that do not name each other — House convention (`27-twin-division-*`, NOTICE)

- **Symptom.** Two skills cover related topics; neither description says which requests belong to
  the other.
- **Why bad.** Selection compares the listed descriptions; two that read alike split the requests
  between them, and neither owner can see it from their own file (`33-description-overlap`).
- **Fix.** Crossed anti-triggers in the **descriptions**: each names the other with `→ <twin>`.
  Their effect depends on how alike the pair is: 1/10 → 10/10 on a synthetic pair built to collide
  (`two-skills-compete`), but only +1.7 pts (Opus 5.5) and +2.7 pts (Haiku 4.5), intervals
  containing zero, on the 8 real pairs below — whose positive clauses already told them apart.
- **Not a fix.** A `Division of responsibilities` table in the body. The body is loaded only after
  a skill is chosen, so the table can at best repair a wrong first pick by sending the model to the
  twin. Measured 2026-09-27 on 8 real twin pairs, 1,152 runs per model: the table moved "the right
  skill was loaded" by −0.3 pts on Opus 5.5 and +0.4 pts on Haiku 4.5, both 95% intervals
  containing zero. The model handed off to the twin as often without the table as with it. Keep
  one if humans read it; `27-*` reports its absence as a NOTICE and will retire after a second null
  measurement. The larger loss on the same runs was elsewhere: 14–22 % of boundary requests loaded
  **neither** skill, which nothing in a body can repair.

### B7. `SKILL.md` past the compaction slice — Universal

- **Symptom.** A `SKILL.md` well under the size errors, and behaviour still degrades once a long
  session compacts.
- **Why bad.** [context-window](https://code.claude.com/docs/en/context-window): after compaction
  each invoked skill's body is re-injected "capped at 5,000 tokens per skill", keeping the start.
- **Fix.** Front-load rules and routing; treat ~20 KB as the working ceiling; move catalogues to
  `references/`.

### B8. One anchor block duplicated across a skill family — Universal

- **Symptom.** Every `ui-*` skill opens with the same paragraph of framework versions and flags.
- **Why bad.** N copies of one truth drift apart, and a session loading three pays three times.
- **Fix.** One home per fact (the family's entry point, `ui-overview`); siblings carry a one-line pointer.

## C. Sub-agents

### C1. A sub-agent that validates on its own initiative — Universal

- **Symptom.** A `shop-checkout` implementer runs the full test suite after each file it touches.
- **Why bad.** The delegator loses control of when and how often validation runs; a slow suite
  runs N times, and results arrive scattered across returns.
- **Fix.** Decide where validation lives and write it in the delegation contract: either the
  sub-agent runs a named, bounded check and reports it, or it returns and the caller validates once.

### C2. Unbounded delegation — Universal

- **Symptom.** An agent may spawn others, which may spawn others, with no statement of depth, scope
  or return shape.
- **Why bad.** [sub-agents](https://code.claude.com/docs/en/sub-agents): a sub-agent can spawn
  sub-agents, up to three layers below the main conversation. Intermediate output stays hidden;
  only the top summary returns, so a wrong turn two levels down is invisible.
- **Fix.** When an agent needs no children, omit `Agent` from its `tools` (or add it to
  `disallowedTools`). When it does, restrict the types it may spawn and say what each must return.

### C3. Agent body restates its own skill — Universal

- **Fix.** Name the skill in `skills:` (the full body is injected at startup) and delete the
  paraphrase. A skill with `disable-model-invocation: true` cannot be preloaded.

### C4. A read-only agent that fans out to a writable one — Universal

- **Symptom.** An agent advertises itself as read-only, then spawns `general-purpose` workers
  carrying `Edit` and `Write`.
- **Fix.** Fan out to a type with the same tool envelope; a guarantee only the prompt enforces is none.

### C5. Out-of-scope edits — Universal

- **Fix.** The sub-agent reports the discovery in its return; the caller dispatches separately.

### C6. Agent body restates `CLAUDE.md` — Universal

- **Why bad.** [sub-agents](https://code.claude.com/docs/en/sub-agents): custom sub-agents load the
  `CLAUDE.md` hierarchy; `Explore` and `Plan` skip it. The copy costs tokens per dispatch and will
  eventually contradict the original.
- **Fix.** Delete it. For `Explore`/`Plan`, put the rule in the delegation prompt.

### C7. Agent description front-loads *how* instead of *when* — Universal

- **Fix.** Lead with the trigger surface (domain, paths, verbs a user would type); method belongs
  in the body, which loads only on dispatch.

## D. Hooks and agent teams

### D1. Hooks added ad hoc — Universal

- **Symptom.** A `PostToolUse` hook re-runs the linter after every edit, added in passing.
- **Why bad.** [best-practices](https://code.claude.com/docs/en/best-practices): hooks are
  deterministic — which is their value and their cost. A per-edit hook adds latency to every task,
  including those that did not need it, and may duplicate a check that already runs elsewhere.
- **Fix.** Use a hook for what "must happen every time with zero exceptions"; justify each one,
  and prefer the cheapest event that achieves it (a `Stop` gate over a per-edit run).

### D2. Agent teams enabled alongside `skills:`-dependent agents — Universal

- **Symptom.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set "to try it", in a project whose
  agents get their knowledge from `skills:`.
- **Why bad.** [agent-teams](https://code.claude.com/docs/en/agent-teams): while enabled, a
  sub-agent Claude names launches as a teammate, and a teammate does not apply the definition's
  `skills`. The agents run stripped of their preload, with no error.
- **Fix.** Leave it off, or re-derive how each agent gets its knowledge before enabling it.

## E. Layout

### E1. Global script pool (`.claude/scripts/`) — House convention (`13-no-global-scripts`, WARN)

- **Symptom.** Scripts in a top-level `.claude/scripts/` folder, attached to no skill.
- **Why bad.** A script with no owning skill has no documentation that loads with it and no
  trigger; nobody knows when it is safe to delete. Claude Code itself does not forbid the folder.
- **Fix.** Move each script under its owner: `.claude/skills/<owner>/scripts/<script>`.

## F. Rules (`.claude/rules/`)

### F1. Rule that duplicates a skill's body — Universal

- **Symptom.** A rule contains 40 lines of SSR architecture.
- **Why bad.** It loads on every matching read and duplicates `shop-ssr`.
- **Fix.** Keep only the constraint in the rule; the skill carries the knowledge.

### F2. Unconditional rule — nuanced

- **Symptom.** A rule has no `paths:`.
- **Not in itself a defect.** [memory](https://code.claude.com/docs/en/memory): rules without
  `paths` load at launch "with the same priority as `.claude/CLAUDE.md`" — a documented way to
  modularise, and they survive compaction.
- **Defect when** the rule has frontmatter but no `paths:` (`14-rule-no-paths`): that is usually
  a scoping attempt that failed, and the rule is global by accident.

### F3. Rule over 2 KB — House convention (`14-rule-size`)

- **Why bad.** A rule has no description to decide by and loads whole; past ~2 KB it is usually
  a skill's body. The 2 KB figure is the plugin's, not Anthropic's.
- **Fix.** Extract the knowledge into a skill; keep the constraint in the rule.

### F4. Path-scoped rule meant to guard file creation — Universal

- **Symptom.** `api-handler-shape.md` with `paths: ["src/api/**/*.ts"]`, written to govern how new
  handlers are created.
- **Why bad.** [memory](https://code.claude.com/docs/en/memory): path-scoped rules "trigger when
  Claude reads files matching the pattern, not on every tool use". Creating a file is not reading
  one; the rule does not fire for it (measured 2.1.280, `anthropics/claude-code#93248`).
- **Fix.** Put a creation constraint where it is always present — a rule without `paths:`,
  `CLAUDE.md`, or the skill that scaffolds handlers — or enforce it with a hook.

### F5. Contradictory rules — Universal

- **Symptom.** `ui-style.md` says "2-space indentation"; a user rule in `~/.claude/rules/` says 4.
- **Why bad.** [memory](https://code.claude.com/docs/en/memory): "if two rules contradict each
  other, Claude may pick one arbitrarily"; neither user nor project rules override the other.
- **Fix.** Review `CLAUDE.md`, nested `CLAUDE.md` files and all rules together; keep one statement
  per behaviour.

### F6. Cursor-style frontmatter — Universal (`14-rule-unknown-field`)

- **Symptom.** A rule scoped with `globs:` or carrying `alwaysApply:`.
- **Why bad.** [memory](https://code.claude.com/docs/en/memory): `paths` is the only field read;
  others are ignored without error. The rule loads globally.
- **Fix.** Rename `globs:` to `paths:`; delete the other fields.

## G. Settings

### G1. A settings key that is inert at its scope — Universal (`24-settings-default-mode`, `24-settings-scope`)

- **Symptom.** `.claude/settings.json` carries `permissions.defaultMode: "bypassPermissions"`, and
  everything behaves as expected on the author's machine.
- **Why bad.** [settings](https://code.claude.com/docs/en/settings): `auto` and
  `bypassPermissions` "don't take effect from project or local settings" (since 2.1.257). The
  posture comes from user scope; a fresh clone lands elsewhere, and the file reads as the cause of
  a behaviour it no longer causes.
- **Detection.** `24-settings-default-mode` (WARN) flags this key; `24-settings-scope` (ERROR)
  flags any key the settings reference restricts to another scope.
- **Fix.** Delete the key from project scope; set it in user or managed settings, or pass
  `--permission-mode`. After a CLI upgrade, re-read the scope rules of every key copied between
  scopes.
