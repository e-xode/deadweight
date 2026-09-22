<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Skill runtime mechanisms

Contents: [Frontmatter fields](#frontmatter-fields) · [Portability outside Claude Code](#portability-outside-claude-code) · [Path-scoped skills](#path-scoped-skills) · [Listing visibility and the budget](#listing-visibility-and-the-budget) · [Skill content lifecycle](#skill-content-lifecycle) · [Running a skill as a subagent](#running-a-skill-as-a-subagent) · [Skills as slash commands](#skills-as-slash-commands) · [Discovery and precedence](#discovery-and-precedence) · [Measuring the real cost](#measuring-the-real-cost) · [Bundled skill collisions](#bundled-skill-collisions) · [Settings scope](#settings-scope--a-key-that-is-silently-ignored)

What Claude Code actually supports for skills, and which of it this project has adopted. Verified
2026-09-03 against Claude Code 2.1.259, the `code.claude.com/docs/en/skills` page and the Agent
Skills spec.

## Frontmatter fields

| Number | What it caps | Source |
| --- | --- | --- |
| **1,024** | `description` **alone** — hard cap of the Agent Skills spec. Past it, upload and packaging fail. | [platform.claude.com — agent-skills/best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) |
| **1,536** | `description` **+** `when_to_use` **combined** — truncation in the skill listing, nothing else. | [code.claude.com — skills](https://code.claude.com/docs/en/skills) |

Two mechanisms, two documents, two pages. **Author against 1,024.** A 1,200-character description
passes the listing and still hard-fails on upload. Table added 2026-09-20: two readers had confused
the two figures that day, one of them the author of this doctrine.

Every field is optional; only `description` is recommended, and it falls back to the first markdown
paragraph when omitted. `name` is capped at 64 characters (lowercase letters, digits and hyphens)
and must match the folder; `description` is capped at **1,024 characters by the Agent Skills spec**.
The 1,536-character figure is a different thing entirely — the _listing_ cap on `description` +
`when_to_use` combined, set by `skillListingMaxDescChars`. Booleans accept `yes/no/on/off/1/0` as
well as `true/false` since v2.1.218.

The documented table carries **twenty fields**. This project takes a position on the ones marked.

| Field                            | Effect                                                                                                                                                                                                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                           | Display label in listings. For a personal or project skill the **typed command comes from the folder name**, not from this field; only plugin skills take their command from `name`.                                                                     |
| `description`                    | The trigger surface. Spec cap 1,024 chars. Put the key use case first — the listing truncates.                                                                                                                                                           |
| `when_to_use`                    | A second trigger field (phrases, example requests). Appended to `description` in the listing and counted against the **same** 1,536-char cap, so it buys readability, never budget.                                                                      |
| `argument-hint`                  | Autocomplete hint, e.g. `[issue-number]`.                                                                                                                                                                                                                |
| `arguments`                      | Named positional arguments for `$name` substitution, in order.                                                                                                                                                                                           |
| `disable-model-invocation: true` | Only the user can invoke the skill, with `/name`. **The description leaves the model's context entirely** — the strongest budget lever, and the only one that also removes the name. Also blocks `skills:` preload and (2.1.196+) scheduled-task firing. |
| `user-invocable: false`          | Only Claude can invoke it. The description stays in context; the skill disappears from the `/` menu.                                                                                                                                                     |
| `allowed-tools`                  | Pre-approves the listed tools for the turn that invokes the skill. Clears on the next user message. Does **not** restrict anything.                                                                                                                      |
| `disallowed-tools`               | Removes tools from the pool while the skill is active (2.1.152). Also clears on the next user message. The only skill-level restriction.                                                                                                                 |
| `model`                          | Model override while the skill is active, for the rest of the current turn (with `context: fork`, sets the forked subagent's model instead). Accepts `inherit`. **2.1.259 fixed `model:` being ignored in interactive sessions.**                        |
| `effort`                         | `low` / `medium` / `high` / `xhigh` / `max` while the skill is active; overrides the session level.                                                                                                                                                      |
| `context: fork`                  | Runs the skill as a subagent; the SKILL.md body becomes the prompt.                                                                                                                                                                                      |
| `agent: <type>`                  | With `context: fork`, picks the executing agent type. Defaults to `general-purpose`.                                                                                                                                                                     |
| `background: false`              | With `context: fork`, waits for the result in the invoking turn instead of backgrounding it (default `true` since 2.1.218).                                                                                                                              |
| `hooks`                          | Registers session-lifetime hooks when the skill is invoked; supports `once: true`. Available, **not adopted** — core rule 10.                                                                                                                            |
| `paths`                          | Glob patterns scoping _automatic_ activation; same syntax as path-scoped rules. See below.                                                                                                                                                               |
| `shell`                          | `bash` (default) or `powershell` for `` !`command` `` injection.                                                                                                                                                                                         |
| `metadata`                       | Free-form YAML map for external tooling. Claude Code ignores its contents and drops a non-map value.                                                                                                                                                     |
| `license`                        | Spec field; accepted, not acted on.                                                                                                                                                                                                                      |
| `compatibility`                  | Spec field (≤ 500 chars); accepted, not acted on.                                                                                                                                                                                                        |

Frontmatter is only read when the opening `---` is the file's very first line. Otherwise the whole
file — markers included — is treated as skill body.

Skill edits are picked up **live**: Claude Code watches `~/.claude/skills/`, the project
`.claude/skills/` and any `--add-dir` skills directory and applies `SKILL.md` text changes without a
restart. A brand-new top-level skills directory needs a restart; a skill folder that is _also_ a
plugin needs `/reload-plugins` for its `hooks/`, `.mcp.json`, `agents/` and `output-styles/` changes.

## Portability outside Claude Code

Claude Code accepts all twenty fields. Everything else does not: claude.ai skill uploads, the Skills
API and `package_skill.py` accept only the spec's six — `name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools` — and **fail with a hard error**, not a warning, on any
other key (`Unexpected key(s) in SKILL.md frontmatter: …`). A skill that must stay portable therefore
cannot carry `paths`, `when_to_use`, `model`, `effort` or `disable-model-invocation`. Nothing in this
project is distributed that way today, so the constraint costs nothing here — but it is the reason
the vendored `skill-creator` keeps its frontmatter to the spec subset.

## Path-scoped skills

`paths:` limits _automatic_ activation to files matching the globs, using the same syntax and the
same brace-expansion budget as `.claude/rules/` (see [rules-anatomy.md](./rules-anatomy.md)). It
promises a skill boundary that is mechanical instead of semantic — the direct answer to two skills
whose descriptions both plausibly match one request. **Measured twice, it does not deliver that.**
This project piloted it and then removed it; no skill here carries `paths:` today.

**Measured 2026-09-03, Claude Code 2.1.259, headless `claude -p` sessions** (socket pair +
`shop-js-style` carrying `paths:`, sandbox copy of the config with probe files):

- A `paths:`-scoped skill is **absent from the listing — name and description** — while no matching
  file is in play. It is therefore a fourth budget lever, and a hard one.
- It is **not invocable by name** either: the Skill tool answers `Unknown skill: shop-js-style`.
- Reading or editing a matching file (`src/server/socket.probe.js`, `scripts/probe.mjs`) injected the
  path-scoped **rules** as usual but **no skill body**, and the skill stayed unlisted for the rest of
  the turn. A prose question in the skill's domain ("which STATUS codes exist?") went unanswered: the
  model reported the skill "was not surfaced this turn".
  **Measured 2026-09-09, interactive Claude Code session, Opus 5 (1M context), against the live
  project config — not a sandbox.** This is the one branch the headless run could not reach, since a
  `-p` run has no next turn:

- `Read` on `server.js` — a file matching `shop-js-style`'s `paths:` globs — injected the path-scoped
  **rules** `js-code-style` and `api-security` exactly as expected, and **no skill body**.
- On the **next** user turn the skill was still not offered: `Skill(shop-js-style)` answered
  `Unknown skill: shop-js-style`. There is no deferred next-turn offer; touching a matching file
  changes nothing about the skill's availability, in that turn or the one after.

Verdict, no longer conditional: `paths:` is a **withholding mechanism in both headless and
interactive modes** — never a scoping or disambiguation one, and never a routing lever. The socket
pair had it removed on 2026-09-03 (its inventory is asked for in prose and must stay discoverable).

**Closed 2026-09-09: `paths:` was removed from `shop-js-style` as well, and no skill in the measured
project carries it any more.** The pilot delivered none of the three things it was set up
to deliver — no automatic load, no invocation by name, no listing presence — while costing the skill
its whole discoverable trigger surface; and rule `.claude/rules/js-code-style.md` already fires
deterministically on the same globs, so `paths:` bought nothing the rule did not already provide.
The accepted price of reverting is that the skill's 449-char description re-enters the
always-loaded listing budget — in the project where this was measured, near 41,100 chars against
a 43,000 ratchet.

`scripts/audit.py` still counts a non-empty `paths:` as a withholding lever, deliberately: if anyone
adds one again, the "every withheld skill must be named in the `CLAUDE.md` Skills index" check fires
instead of the skill going silently unreachable.

**Before trusting `paths:` again** — a future Claude Code release could change its behaviour — re-run
the two-step check that produced this verdict: (1) in a fresh session, confirm whether the scoped
skill appears in the listing and whether `Skill(<name>)` resolves; (2) read or edit a matching file,
then on the **next** user turn try `Skill(<name>)` again. Both steps must pass before `paths:` is
treated as anything other than a fourth budget lever. Independently of the outcome, keep it off
advisory skills (`shop-lore`, `marketing-*`, `content-strategy`, `shop-art-direction`), whose trigger
is a question, not a file.

## Listing visibility and the budget

Every visible skill's name and description are injected into the system prompt each turn. The
listing "always contains every skill name"; when it overflows, **Claude Code drops descriptions
starting with the skills you invoke least, so the skills you use most keep their full text**
(verbatim, `docs/en/skills` § "Skill descriptions are cut short", re-fetched 2026-09-03). This
corrects the alphabetical-cliff conclusion recorded in case study CS-6, and it settles a
disagreement between the two 2026-09-03 research sweeps: one found the rule on the skills page, the
other found no official statement. The page states it.

Three levers size that budget:

| Lever                            | Unit                       | Default                                                                                  |
| -------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------- |
| `skillListingBudgetFraction`     | fraction of context window | docs say **1 %**; changelog 2.1.32 (2026-02-05) shipped "**2 % of context**" — see below |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` | fixed character count      | unset                                                                                    |
| `skillListingMaxDescChars`       | chars per entry            | 1,536 (`description` + `when_to_use`), stated in prose, not rendered as a default        |

The two sources for the fraction genuinely disagree, and the unit is ambiguous on top of that: the
budget is expressed against a context window measured in tokens while the override env var counts
characters. **Never extrapolate a headroom figure from the fraction.** Measure it.

`skillOverrides` in settings controls visibility per skill without editing the skill file, which
matters for anything checked into a shared repo. It does **not** apply to plugin skills.

| Value                   | Listed to Claude     | In the `/` menu |
| ----------------------- | -------------------- | --------------- |
| `"on"` (default)        | Name and description | yes             |
| `"name-only"`           | Name only            | yes             |
| `"user-invocable-only"` | Hidden               | yes             |
| `"off"`                 | Hidden               | hidden          |

The `/skills` menu writes `skillOverrides` to `.claude/settings.local.json`. This project keeps it
in the tracked `.claude/settings.json` instead, so the decision is shared and reviewable.

`scripts/audit.py` reads both mechanisms and reports the **effective** listing cost alongside the
raw character total. A skill withheld from the listing costs nothing per turn but also cannot be
discovered semantically — so every withheld skill must be named in the `CLAUDE.md` Skills index and
reachable through an explicit pointer. The audit enforces that pairing.

Since **2.1.222** a `disable-model-invocation` skill also fails safer: instead of paraphrasing the
workflow from memory, Claude asks the user to run the skill. That removes the failure mode that
made withholding feel risky.

## Skill content lifecycle

Invoked skill content enters the conversation as one message and stays for the session; Claude Code
does not re-read the file on later turns. Write guidance that must hold throughout a task as
standing instructions, not one-time steps.

Auto-compaction re-attaches only **the first 5,000 tokens of each invoked skill**, within a
**25,000-token combined budget** filled most-recent-first, so older skills can be dropped whole.
Two consequences the doctrine leans on:

- **Truncation keeps the start of the file.** Whatever sits past ~5,000 tokens (≈ 20 KB of prose)
  silently stops applying after the first compaction. Front-load the rules; put the encyclopedia in
  `references/`.
- **Skill _descriptions_ are not reloaded after compaction** — only invoked bodies are. A skill that
  was never invoked before the compaction is not re-advertised.

Re-invoking a skill whose rendered content is already in context adds a short note rather than a
second copy. A user can stack skills at the start of one message: Claude Code expands the first
skill plus **up to five more** (six in total), stopping at the first token that is not an inline
user-invocable skill.

## Running a skill as a subagent

`context: fork` and a subagent's `skills:` field are inverses of the same mechanism:

| Approach                   | System prompt        | Task                        | Also loads                                     |
| -------------------------- | -------------------- | --------------------------- | ---------------------------------------------- |
| Skill with `context: fork` | from the agent type  | the SKILL.md body           | CLAUDE.md, unless the agent is Explore or Plan |
| Subagent with `skills:`    | the agent's own body | Claude's delegation message | preloaded skill content + CLAUDE.md            |

`context: fork` only makes sense for a skill that states an actionable task. A skill that is pure
guidance ("use these conventions") forks into an agent with no work to do.

A skill carrying `disable-model-invocation: true` **cannot** be preloaded via `skills:` — preloading
draws from the same pool Claude can invoke. Agents that need such a skill must read its `SKILL.md`
by path.

## Skills as slash commands

`.claude/commands/` has been merged into skills: a skill is invocable as `/name`, and `$ARGUMENTS`
carries whatever the caller passed. This project has no `.claude/commands/` directory and does not
need one. Available substitutions include `$ARGUMENTS`, `$ARGUMENTS[N]`, `$N`, `$name`,
`${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_SESSION_ID}`.

## Discovery and precedence

Enterprise overrides personal, personal overrides project, and any of them overrides a bundled
skill of the same name — **but not that bundled skill's aliases**. The docs' own example: a project
`code-review` skill replaces the bundled `/code-review`, yet typing the alias `/review` never
reaches it.

⚠️ **Live consequence here, to verify at runtime.** This project ships a skill named `review`, and
`/review` is the bundled `code-review`'s alias. Typing `/review` may therefore reach the bundled
skill rather than the project one. The Skill tool can still select `review` by name, and the
`review` **agent** is unaffected — only the typed slash command is in doubt. Confirm with `/review`
in a fresh session before relying on it; if it resolves upstream, either invoke the project skill
by tool name or rename it.

Plugin skills are namespaced `plugin-name:skill-name` and cannot collide. Where a skill and a
`.claude/commands/` file share a name, the skill wins.

Nested `.claude/skills/` directories below the working directory are also discovered: a skill in
`apps/web/.claude/skills/` is offered as `apps/web:deploy` and applies when Claude works on files in
that subtree. Not used here — the repo is single-package — but it is the answer if it ever splits.

## Measuring the real cost

`audit.py` counts characters statically. It cannot see what the harness injected. The audit method
requires a runtime pass after any change to the listing — see `SKILL.md` § Audit Step 2 for the full
command set (`/doctor`, `/context all`, `/skills`, `/usage`, `/skill-doctor`, `--safe-mode`). The
releases that introduced them, so a missing command is read as version drift rather than as a wrong
name: `/skills` 2.1.111, `/context all` 2.1.139, `/usage` 2.1.149, `claude --safe-mode` 2.1.169,
`/doctor` 2.1.206, `/skill-doctor` 2.1.247 (early access, enabled on this account).

If the runtime figures disagree with the audit's effective total, trust the runtime and reconcile
the script.

Measured 2026-09-03 with `/context` on a 1M-token-context model, 51 listed project skills: Skills row
10.2k tokens (≈ 7.3k project descriptions + ≈ 2.9k bundled skills), every listed description present —
no truncation at the 2.5 % fraction, and none expected at the 1 % default (≈ 10k tokens); custom
agents 2.8k; `CLAUDE.md` + memory files 5.6k; system tools 17.3k; deferred MCP pool 60.9k (loaded on
demand, not resident). The always-loaded ratchet (43,000 chars ≈ 10.7k tokens) therefore sits at
about one percent of the window on this model — the ratchet is a discipline, not a cliff. It is a
**project** ratchet: no equivalent aggregate exists upstream, the nearest analogue being the
15,000-token combined-agent-description startup warning ([agent-anatomy.md](./agent-anatomy.md)).

## Bundled skill collisions

The harness lists its own bundled skills beside the project's, and four of them overlap project
names or triggers (found in the 2026-09-16 listing):

| Bundled skill                                  | Collides with                         | How it shows                                                                         |
| ---------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------ |
| `design` (Claude Design canvas)                | the `design` **agent**                | a bare `→ design` arrow now names two things                                         |
| `code-review` / `simplify` / `security-review` | the `review` skill and agent          | "review this diff" has a project-aware and a convention-blind candidate              |
| `claude-api`                                   | any project skill named after a vendor | a vendor term appears in nearly every prompt about that vendor, so both always match |
| `run` (launch / screenshot / confirm the app)  | `visual-qa` and the never-verify rule | a second path to the running app that bypasses the request-gated verification agents |

Mitigations, all on the project side because a bundled skill cannot be withheld from here:

- Arrows that mean "delegate to an agent" carry the `agent` qualifier (`→ design agent`,
  `→ translate agent`), so a pointer never resolves to a bundled skill by accident.
- A project description that competes with a bundled skill names it in its anti-trigger clause
  (a vendor-named project skill → `claude-api`; `review` → `code-review`).
- The collision is documented, not fought: the bundled listing changes with every CLI release, so
  re-read it at each audit and update this table.

## Settings scope — a key that is silently ignored

`permissions.defaultMode` is **ignored at project scope** since **2.1.257 (2026-09-01)**, exactly
like the value `"auto"`. It has to be set in user or managed settings, or passed as
`--permission-mode`. A fresh clone therefore inherits nothing from a repository that declares it.

*A key that no longer does what it says is worse than an absent one* — it reads as a posture and
produces none. See [antipatterns.md](./antipatterns.md) G1. Measured on one fleet, 2026-09-20:
three repositories still carried the dead key, unnoticed since the version bump.
