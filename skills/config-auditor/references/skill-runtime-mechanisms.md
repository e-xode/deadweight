<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Skill runtime mechanisms

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Contents: [Frontmatter fields](#frontmatter-fields) · [Portability outside Claude Code](#portability-outside-claude-code) · [Path-scoped skills](#path-scoped-skills) · [Listing visibility and the budget](#listing-visibility-and-the-budget) · [Skill content lifecycle](#skill-content-lifecycle) · [Running a skill as a subagent](#running-a-skill-as-a-subagent) · [Skills as slash commands](#skills-as-slash-commands) · [Discovery and precedence](#discovery-and-precedence) · [Bundled skills](#bundled-skills) · [Measuring the real cost](#measuring-the-real-cost) · [Settings scope](#settings-scope--a-key-that-is-silently-ignored)

What Claude Code actually does with a skill. Unless marked **measured** or **house convention**,
every statement comes from [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills)
(cited by section). Authoring rules live in [skill-anatomy.md](./skill-anatomy.md).

## Frontmatter fields

| Number | What it caps | Source |
| --- | --- | --- |
| **1,024** | `description` **alone** — Agent Skills spec cap; past it, upload and packaging fail. | [platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) |
| **1,536** | `description` **+** `when_to_use` combined — listing truncation only, set by `skillListingMaxDescChars`. | skills § Frontmatter reference |

Author against 1,024 (`04-skill-description-length`). In Claude Code every field is optional:
`name` defaults to the folder name, and a missing `description` falls back to "the first non-empty
line of the markdown content". Booleans accept `yes/no/on/off/1/0` as well as `true/false` since
2.1.218 ([changelog](https://code.claude.com/docs/en/changelog)).

The documented table carries **twenty fields** (skills § Frontmatter reference):

| Field | Effect |
| --- | --- |
| `name` | Display label. For a personal or project skill the **typed command comes from the folder name**; only plugin skills take it from `name`. |
| `description` | The trigger surface. Put the key use case first — the listing truncates. |
| `when_to_use` | Extra trigger text, appended to `description` in the listing and counted against the **same** 1,536 cap: readability, never budget. |
| `argument-hint` | Autocomplete hint, e.g. `[order-id]`. |
| `arguments` | Named positional arguments for `$name` substitution, in order. |
| `disable-model-invocation: true` | Only the user can invoke it. The description leaves the model's context. Also blocks `skills:` preload and, since 2.1.196, firing from a scheduled task. |
| `user-invocable: false` | Only Claude can invoke it: hidden from the `/` menu, typed `/name` does not run it. The description stays in context. |
| `allowed-tools` | Pre-approves tools for the turn that invokes the skill; clears on the next user message. Restricts nothing. **Not gated by workspace trust** (skills § Pre-approve tools). |
| `disallowed-tools` | Removes tools from the pool while the skill is active (2.1.152); clears on the next user message. The only skill-level restriction. |
| `model` | Model for the rest of the current turn (with `context: fork`, the forked subagent's). Accepts `inherit`. 2.1.259 fixed it being ignored in interactive sessions. |
| `effort` | `low` … `max` while the skill is active; overrides the session level. |
| `context: fork` | Runs the skill as a subagent; the body becomes the prompt. |
| `agent: <type>` | With `context: fork`, the executing agent type. |
| `background: false` | With `context: fork`, waits for the result in the invoking turn (default `true`, 2.1.218+). |
| `hooks` | Registers hooks when the skill is invoked, for the rest of the session. |
| `paths` | Glob patterns that limit automatic activation. See [below](#path-scoped-skills). |
| `shell` | `bash` (default) or `powershell` for `` !`command` `` injection. |
| `metadata` | Free-form map for your own tooling; Claude Code ignores its contents and drops a non-map value. |
| `license` | Spec field; accepted, not acted on. |
| `compatibility` | Spec field (≤ 500 chars); accepted, not acted on. |

Frontmatter is read only when the opening `---` is the file's first line. Malformed YAML loads the
body "with empty metadata": `/name` works, description matching does not; `claude plugin validate
.claude/skills` finds such files (2.1.233+) (skills § Skill not triggering). **Measured, not
documented** (2026-09-23, 2.1.280): an unknown key is silently ignored — `claude plugin validate` passed a probe
carrying one. `02-skill-frontmatter`, `02-skill-unknown-field`.

Edits are picked up **live** under `~/.claude/skills/`, the project `.claude/skills/` and an
`--add-dir` skills directory — `SKILL.md` text only; a skill folder that is also a plugin needs
`/reload-plugins` for its `hooks/`, `.mcp.json`, `agents/` and `output-styles/` (skills § Edit a
skill during a session).

## Portability outside Claude Code

claude.ai uploads, the Skills API and `package_skill.py` accept only the spec's six fields — `name`,
`description`, `license`, `compatibility`, `metadata`, `allowed-tools` — and **fail with a hard
error** on any other key: `Unexpected key(s) in SKILL.md frontmatter: …` (skills § Using skill
frontmatter outside Claude Code). A skill meant to travel there cannot carry `paths`,
`when_to_use`, `model`, `effort` or `disable-model-invocation`, and its `` !`command` `` injections
do not run. Those targets also require `name` and `description`, forbid XML in both, and reject
`anthropic`/`claude` in `name`
([platform best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).

## Path-scoped skills

**Doc.** `paths` takes globs in the path-specific-rules format; "When set, Claude loads the skill
automatically only when working with files matching the patterns" (skills § Frontmatter
reference). The docs say nothing about the listing.

**Measured, 2026-09-23, Claude Code 2.1.280** (2 runs per branch, all concordant):

| Situation | Is the scoped skill offered? |
| --- | --- |
| Session start (`init` event) | **No** — absent, name and description |
| After reading a file **outside** the globs | **No** |
| After reading a file **matching** the globs | **Yes** |

What that means:

- `paths:` **takes a skill out of the starting listing**: it is not paid for on turns where no
  matching file is in play. That is a budget effect, and `audit.py` counts a non-empty `paths:`
  among the withholding levers for that reason (`15-skill-index` then expects the skill in the
  `CLAUDE.md` skills index).
- It does **not** make the skill unreachable: touching a matching file brings it in, as the doc
  says.
- It is still **not a disambiguation lever**. Two skills scoped to the same globs both come in
  once a matching file is read; `paths:` only decides *when* they compete.
- Keep it off skills whose trigger is a **question** rather than a file (`shop-lore`,
  `content-strategy`): they may be needed before any file is touched. House convention.

An earlier measurement on 2.1.259 concluded that a `paths:` skill was withheld and never loaded.
**It is obsolete**: re-measure on every Claude Code upgrade before relying on either answer.

**Protocol.** In a scratch repository, create two probe skills, identical except that one carries
`paths: ["src/checkout/**"]` (the control has none), plus `src/checkout/cart.js` and
`docs/notes.md`. Then:

1. `claude -p "<prompt>" --output-format stream-json --verbose` and read the `skills` array of the
   first `{"type":"system","subtype":"init"}` event: the control is listed, the scoped probe is not.
2. Prompt a read of `docs/notes.md` (outside the globs), then ask whether the scoped probe is
   available / invoke it by name: it is not.
3. Prompt a read of `src/checkout/cart.js` (matching), then the same question: it is.

Run each branch at least twice; a single run is an anecdote.

## Listing visibility and the budget

Every listed skill's name and description are injected on every turn. "The listing always contains
every skill name"; the budget "scales at 1% of the model's context window", and on overflow
"Claude Code drops descriptions starting with the skills you invoke least, so the skills you use
most keep their full text" (skills § Skill descriptions are cut short). Degradation, not a cliff.

| Lever | Unit | Default |
| --- | --- | --- |
| `skillListingBudgetFraction` | fraction of context window | docs: **1 %**; changelog 2.1.32 shipped "2 % of context" |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` | fixed character count | unset |
| `skillListingMaxDescChars` | chars per entry | 1,536 (`description` + `when_to_use`) |

The two sources for the fraction disagree, and the budget is set against a token window while the
override counts characters. **Never extrapolate headroom from the fraction — measure it**
(`/doctor`, `/context`). `29-listing-budget-derived` reports a derived ceiling and says how
optimistic it is; `30-plugin-cost` reports what a plugin's own descriptions cost every consumer.

`skillOverrides` in settings controls visibility without editing the skill (skills § Override skill
visibility from settings). It does **not** apply to plugin skills — manage those through `/plugin`.

| Value | Listed to Claude | In the `/` menu |
| --- | --- | --- |
| `"on"` (default) | Name and description | yes |
| `"name-only"` | Name only | yes |
| `"user-invocable-only"` | **Hidden — name too** | yes |
| `"off"` | **Hidden — name too** | hidden |

So three settings remove the **name** as well as the description: `disable-model-invocation: true`,
`"user-invocable-only"` and `"off"`. `"name-only"` is the only lever that keeps the name. `"off"`
also hides the skill from Remote Control and Agent SDK command lists (2.1.199+).

The `/skills` menu writes `skillOverrides` to `.claude/settings.local.json`. **House convention:**
keep it in the tracked `.claude/settings.json`, so the decision is shared and reviewable
(`24-settings-skill-overrides` checks every entry names an existing skill).

A withheld skill costs nothing per turn and cannot be discovered semantically, so **house
convention** requires every withheld skill to be named in the `CLAUDE.md` skills index and reached
through an explicit pointer — `15-skill-index`. Since 2.1.222, when Claude tries to invoke a
`disable-model-invocation` skill it is told to ask the user to run it instead of replicating the
workflow ([changelog](https://code.claude.com/docs/en/changelog)).

## Skill content lifecycle

Invoked content enters the conversation as one message and stays for the session; the file is not
re-read on later turns — write guidance that must hold as standing instructions (skills § Skill
content lifecycle). An `allowed-tools` grant does not persist: it clears on the next message.

Auto-compaction re-attaches the most recent invocation of each skill, keeping **the first 5,000
tokens** of each, within a **25,000-token combined budget** filled most-recent-first — older skills
can be dropped whole. Consequences:

- **Truncation keeps the start.** Past ~5,000 tokens (≈ 20 KB of prose) a body silently stops
  applying after the first compaction: front-load the rules. `21-skill-md-compaction`.
- **Descriptions are not what is re-attached** — invoked bodies are.

Re-invoking a skill whose rendered content is identical adds a short note, not a second copy. A
user can stack skills at the start of one message: the first plus **up to five more** expand,
stopping at the first token that is not an inline user-invocable skill (skills § Pass arguments).

## Running a skill as a subagent

`context: fork` and a subagent's `skills:` field are inverses (skills § Run skills in a subagent):

| Approach | System prompt | Task | Also loads |
| --- | --- | --- | --- |
| Skill with `context: fork` | from the agent type | the SKILL.md content | CLAUDE.md per the agent's startup context (Explore and Plan skip it) |
| Subagent with `skills:` | the agent's own body | Claude's delegation message | preloaded skill content + CLAUDE.md |

`context: fork` only makes sense for a skill that states a task; pure guidance forks into an agent
"without meaningful output". The fork does not see the conversation history. In `-p` mode, and when
a scheduled task fires it, Claude Code waits for the result even without `background: false`. A
`disable-model-invocation` skill **cannot** be preloaded via `skills:` — an agent that needs it
reads its `SKILL.md` by path.

## Skills as slash commands

`.claude/commands/` still works but is the older format; a skill is invocable as `/name`, and a
skill wins over a command file of the same name (`45-command-shadowed`). Available substitutions
(skills § Available string substitutions):

| Placeholder | Expands to |
| --- | --- |
| `$ARGUMENTS`, `$ARGUMENTS[N]`, `$N` | all arguments, or one by position |
| `$name` | a named argument declared in `arguments` |
| `${CLAUDE_SKILL_DIR}` / `${CLAUDE_PROJECT_DIR}` | the skill's folder / the project root |
| `${CLAUDE_SESSION_ID}` | the session id |
| `${CLAUDE_EFFORT}` | the current effort level (`low` … `max`) |
| `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` | plugin skills only: the install directory / the persistent data directory that survives updates |

When arguments are passed but **no placeholder receives one**, Claude Code appends
`ARGUMENTS: <value>` to the end of the content. The directory variables are also substituted in
`allowed-tools` Bash rules, which lets a skill pre-approve its own bundled script.

`` !`<command>` `` runs before the content reaches Claude and is replaced by its output. **A failed
command aborts the whole invocation** — Claude never sees the skill — with `Shell command failed
for pattern "..."`; any non-zero exit fails except exit 1 from search and comparison commands.
Append `|| true` to a check that exits 1 on findings (skills § When an injected command fails).

## Discovery and precedence

Skills are found **by location**: enterprise, personal (`~/.claude/skills/`), project
(`.claude/skills/` in the start directory and every parent up to the repository root), nested,
`--add-dir`, plugin (`<plugin>/skills/`), and claude.ai-synced (skills § Choose where skills load).
A `SKILL.md` anywhere else loads nowhere — `40-skill-not-loaded`.

Nested `.claude/skills/` directories below the start directory load the first time Claude reads or
edits a file there; until then they are neither listed nor invocable. A clashing nested skill is
offered as `/<subdir>:<name>`.

When two skills share a name (skills § Resolve skills that share a name):

| Same name in | Which one runs |
| --- | --- |
| Two of enterprise, personal, project | enterprise over personal over project |
| One of those and a bundled skill | yours replaces the bundled command, **but not its aliases** |
| A skill and a `.claude/commands/` file | the skill |
| A plugin skill and any other | both, since plugin skills are namespaced `plugin:name` |
| Anything and a claude.ai-synced skill | the other one; the synced skill stays reachable as `/anthropic-skills:<name>` |

The alias carve-out is the trap: a project `code-review` skill replaces `/code-review`, yet "the
bundled alias `/review` never runs your skill". A project skill named after a bundled alias is
therefore not what the typed alias reaches — invoke it through the Skill tool, or rename it
(`shop-review`). Against a synced skill, names compare ignoring case, spacing and dash variants.

## Bundled skills

Claude Code ships prompt-based bundled skills (`/code-review`, `/doctor`, `/loop`, `/claude-api`,
…), listed beside project skills and changing with every release (skills § Bundled skills). A
bundled skill **can** be hidden from the project side: `disableBundledSkills: true` turns them all
off, and a `skillOverrides` entry set to `"off"` hides one — the documented example is
`"doctor": "off"`.

Typical collisions, in the fictional shop:

| Bundled skill | Competes with | How it shows |
| --- | --- | --- |
| `code-review` (alias `/review`) | a project `review` skill | the typed `/review` reaches the bundled one |
| `claude-api` | an `api-<vendor>` skill named after a model vendor | vendor terms appear in every related prompt, so both match |
| `run` | a `shop-preview` skill that launches the storefront | two paths to the running app, one blind to the project's conventions |

Mitigations: name the bundled competitor in the project skill's `Don't use for:` clause; qualify
arrows that mean "delegate to an agent" (`→ ui-design agent`) so a pointer never resolves to a
bundled skill; or hide the bundled one with `skillOverrides`. Re-read the bundled listing at each
audit — it is not stable.

## Measuring the real cost

`audit.py` counts characters statically; it cannot see what the harness injected. After any change
to the listing, a runtime pass is required — see `SKILL.md` § Audit Step 2. Documented tools and
their minimum versions, so a missing command reads as version drift rather than a wrong name:

| Tool | What it shows | Minimum | Source |
| --- | --- | --- | --- |
| `/doctor` | estimated listing cost and its biggest contributors | bundled skill since 2.1.205 | skills § Bundled skills |
| `/context` | per-category context use, per-skill estimates | — | [context-window](https://code.claude.com/docs/en/context-window) |
| `/skill-doctor` | per-skill cost and usage, to pick what to turn off | **2.1.252** | skills § Find unused skills |
| `claude plugin validate <dir>` | `SKILL.md` files whose frontmatter does not parse | 2.1.233 | skills § Skill not triggering |
| `claude --safe-mode` | a session with every customization disabled, as a baseline | 2.1.169 | [changelog](https://code.claude.com/docs/en/changelog) |
| `--debug` | the listing-overflow warning, YAML parse errors | — | skills § Skill descriptions are cut short |

If the runtime figures disagree with the audit's effective total, trust the runtime and reconcile
the script.

**House convention.** `17-always-loaded-budget` caps `CLAUDE.md` + listed skill descriptions +
agent descriptions at 43,000 / 47,000 chars. No aggregate of that kind exists upstream — the
nearest is the combined agent-description startup warning described in
[agent-anatomy.md](./agent-anatomy.md). On a 1M-token window it sits near one percent of the
context: a discipline that keeps the listing reviewable, not a cliff.

## Settings scope — a key that is silently ignored

Since **2.1.257**, `permissions.defaultMode: "bypassPermissions"` in `.claude/settings.json` or
`.claude/settings.local.json` is **ignored**, like `"auto"` before it; set it in user or managed
settings, or pass `--permission-mode` ([changelog](https://code.claude.com/docs/en/changelog)).
Other `defaultMode` values still apply at project scope. `24-settings-default-mode` flags the two
dead values.

*A key that no longer does what it says is worse than an absent one* — it reads as a posture and
produces none. See [antipatterns.md](./antipatterns.md) G1.
