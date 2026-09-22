<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Sub-agent anatomy

Contents: [Folder and file](#folder-and-file) · [Frontmatter](#frontmatter) · [Sub-agent contract (non-negotiable)](#sub-agent-contract-non-negotiable) · [Current agent fleet (14 agents)](#current-agent-fleet-14-agents) · [What a sub-agent actually receives](#what-a-sub-agent-actually-receives) · [Model resolution](#model-resolution) · [Agent teams — off, and why](#agent-teams--off-and-why) · [Advisory agents](#advisory-agents) · [Coherence with `CLAUDE.md`](#coherence-with-claudemd) · [When to create a new sub-agent (vs. extending one)](#when-to-create-a-new-sub-agent-vs-extending-one) · [Anti-patterns specific to agents](#anti-patterns-specific-to-agents)

Verified 2026-09-03 against Claude Code 2.1.259.

Partially re-verified 2026-09-20, at the source, on these points only: the 1,024-character cap on `description` (agent-skills/best-practices), the 1,536-character listing truncation of `description` + `when_to_use` (skills), the hook event catalogue and the semantics of `SessionStart` (hooks), and the behaviour of `disable-model-invocation` (skills). **Everything else on this page still carries the 2026-09-03 date** — it was not re-checked.


## Folder and file

```
.claude/agents/<agent-name>.md
```

- **One file per agent.** Flat directory preferred.
- **`<agent-name>` is kebab-case** and matches the frontmatter `name`.
- Listed in **one place** in `CLAUDE.md`: the `## Agents directory` table (mandatory, enforced both ways by `scripts/audit.py`).

## Frontmatter

```yaml
---
name: hooks
description: '<single string — same rules as a skill description>'
tools: Bash
model: haiku
---
```

### The seventeen fields

Only `name` and `description` are required. Claude Code documents seventeen; the ones this project
has a position on are marked.

| Field                                  | Used here | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| -------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                                 | yes       | Lowercase + hyphens, no `:` (reserved for plugin scoping). Must match the row in `CLAUDE.md`. Hooks receive it as `agent_type`.                                                                                                                                                                                                                                                                                                                                                                                  |
| `description`                          | yes       | Same discriminating + pushy + anti-trigger rules as skills; 80–900 chars (audit-warned), paid every turn from the always-loaded budget.                                                                                                                                                                                                                                                                                                                                                                          |
| `tools`                                | yes       | Allowlist. Restrict to the minimum. **Quote nothing you cannot justify from the body**: an unused grant is an unenforced boundary.                                                                                                                                                                                                                                                                                                                                                                               |
| `disallowedTools`                      | no        | Denylist applied _before_ `tools` resolves. Composes with inheritance — often cleaner than a maximal allowlist. Accepts `mcp__<server>` patterns.                                                                                                                                                                                                                                                                                                                                                                |
| `model`                                | yes       | `sonnet`, `opus`, `haiku`, `fable`, a full model ID, or `inherit` (the default). Tier to the judgement the work needs, not to its importance.                                                                                                                                                                                                                                                                                                                                                                    |
| `effort`                               | no        | `low` … `max`, independent of model tier. Reach for this before promoting an agent a whole tier.                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `skills`                               | **yes**   | Preloads the **full body** of the named skills at startup. Prefer this over restating a skill inside the agent body — see the anti-patterns below.                                                                                                                                                                                                                                                                                                                                                               |
| `memory`                               | **no**    | `user` / `project` / `local`. `project` writes to `.claude/agent-memory/<name>/` and injects that file's first 200 lines / 25 KB into the agent's system prompt. Documented; **recommendation: decline**. An advisory agent already persists its rulings into its skill's `references/`, and a second store is a second source of truth — one written by the agent and read by nothing else. |
| `permissionMode`                       | no        | `default` (labelled _Manual_ in the UI) / `acceptEdits` / `auto` / `dontAsk` / `bypassPermissions` / `plan`. There is **no separate `manual` value** — an earlier note here said otherwise. A parent in `bypassPermissions` or `acceptEdits` wins and cannot be overridden. Ignored on plugin agents.                                                                                                                                                                                                            |
| `maxTurns`                             | no        | Hard stop on agentic turns (2.1.246+). Output is marked _partial_ and the agent is resumable with `SendMessage`. The cheapest runaway guard for a loop that can fail to converge — `svg-artist` and `sfx-designer` run render-critique-refine loops and are the obvious candidates.                                                                                                                                                                                                                              |
| `isolation`                            | no        | `worktree` gives the agent its own checkout off the default branch, auto-cleaned when unchanged; Bash/PowerShell/Monitor are confined to it. Only worth it for a parallel fan-out that mutates the same files — the one-writer-per-file rule already prevents that case here.                                                                                                                                                                                                                                    |
| `hooks`                                | **no**    | Agent-scoped lifecycle hooks (`Stop` becomes `SubagentStop`; they live only while the agent runs). Available, deliberately not adopted — see core rule 10 and case study CS-8. Ignored on plugin agents.                                                                                                                                                                                                                                                                                                         |
| `background`                           | no        | Force background execution. Backgrounding is already the interactive default since v2.1.198 — but **not in `-p` / SDK runs, where subagents run in the foreground with the full tool set**.                                                                                                                                                                                                                                                                                                                      |
| `experimental`                         | no        | `cacheTtl: 5m` or `1h` (v2.1.248) — a per-agent prompt cache. A 14-agent fleet re-pays a cold cache on every dispatch; `1h` is a one-line change, billed at a higher cache-write rate and ignored on usage credits.                                                                                                                                                                                                                                                                                              |
| `color`, `initialPrompt`, `mcpServers` | no        | Display colour, auto-submitted first turn when run as the main agent, per-agent MCP scoping (`mcpServers` ignored on plugin agents).                                                                                                                                                                                                                                                                                                                                                                             |

**Upstream description budget.** Combined agent descriptions over **15,000 tokens** trigger a
startup warning. That is the only aggregate limit Anthropic publishes anywhere near this project's
always-loaded ratchet; the fleet's ~7 KB of descriptions sit around 12 % of it. Keep descriptions
short and move detail into the body — the project's own 80–900-char rule is the stricter proxy.

**Structural validation.** `claude plugin validate --strict --json .claude/agents` would parse agent
frontmatter with upstream's own parser, but measured on 2.1.259 (2026-09-03) it inspects nothing on a
bare directory — `success: true`, empty `contents`. `audit.py` check 23 (tools, `skills:` targets,
`model`) is the structural check until a manifest-bearing wrapper exists; re-test after upgrades.

### Tool-name accuracy

The fan-out tool is **`Agent`**. There is no `Task` tool. The environment does expose
`TaskStop`/`TaskOutput` tools, but those manage background tasks (`Bash run_in_background`, named
background agents/monitors) — they are not sub-agent fan-out and do not contradict this. An entry
that resolves to nothing is
dropped, and if _nothing_ in the list resolves the agent refuses to launch. Restrict which types an
agent may spawn with `Agent(<type>)`.

`AskUserQuestion`, `EnterPlanMode`, `ExitPlanMode`, `EndConversation`, `ScheduleWakeup`,
`TaskOutput`, `WaitForMcpServers` and `Workflow` are removed from every sub-agent, and `Agent`
itself is stripped at the spawn-depth limit — an agent cannot ask the user anything, so its prompt
must be self-sufficient.

A **background** sub-agent (the interactive default) keeps only this built-in set: `Read`, `Grep`,
`Glob`, `Bash`, `PowerShell`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, `WebSearch`, `TodoWrite`,
`Skill`, `ToolSearch`, `EnterWorktree`, `ExitWorktree`, `Monitor`, `TaskStop`, `SendMessage` — plus
every MCP tool. The same definition therefore resolves to different tools in the foreground and the
background, so never build a contract on a tool outside that set. In `-p` / SDK runs the question
does not arise: subagents run foreground with the full set.

## Sub-agent contract (non-negotiable)

1. **Scoped work.** The orchestrator gives the agent a precise scope. The agent does that work and nothing more. Out-of-scope discoveries are **reported, not acted on**.
2. **No validation** (single exception: the `hooks` agent). Sub-agents never run `npm test/build/lint/format`. Validation is centralised on the `hooks` agent invoked by the orchestrator at task end.
3. **No code comments** in produced output (`.vue`/`.js`/`.mjs`/`.scss`/`.css`), same as the rest of the project.
4. **Structured return.** What was done / which files were modified / blockers encountered / suggested follow-ups.
5. **Self-contained prompts.** When the orchestrator launches a fleet (multiple sub-agents in parallel), each prompt is complete — sub-agents do not share context with each other.

## Current agent fleet (14 agents)

The roster, scopes, and delegation triggers live in `CLAUDE.md` § Agents directory — the single
source of truth, kept in sync with `.claude/agents/` by `scripts/audit.py`. Only the
anatomy-relevant differentiators are recorded here:

- **Model tiers** (read from `.claude/agents/*.md` frontmatter, 2026-09-09) — `haiku` for the two
  mechanical runners, `hooks` and `release`; `opus` for the three that must judge a rendered or
  audible result, `svg-artist`, `sfx-designer` and `visual-qa`; `sonnet` for the other nine
  (`content`, `deploy`, `design`, `lore`, `marketing`, `review`, `server`, `translate`, `vue`). The
  advisory agents (`lore`, `marketing`) are **sonnet**: their output is prose anchored in their own
  skill's `references/`, not an artefact that has to be looked at to be graded.
- **Tool envelopes** — read-only agents (`review`, `visual-qa`) carry no write tools; advisory
  agents (`lore`, `marketing`) write only their skill's `references/`; `hooks` runs `Bash` alone.
- **Delegation shape** — `review` alone ships the `Agent` tool, for its sanctioned fan-out, and
  spawns `review` workers so the read-only envelope survives one level down (see anti-patterns).

## What a sub-agent actually receives

A non-fork sub-agent starts with a fresh context containing its own system prompt (the markdown
body), the orchestrator's delegation message, **the whole CLAUDE.md hierarchy**, a git-status
snapshot, and the full content of any skill named in `skills:`. It does **not** see the
conversation, the files already read, or the skills already invoked.

The built-in `Explore` and `Plan` agents are the only ones that skip CLAUDE.md and git status. A
rule that must reach them has to be restated in the delegation prompt.

Practical consequences for writing an agent body:

- Do not restate CLAUDE.md hard rules. Every custom agent already loads them.
- Do restate anything the agent must not infer from its own domain skill.
- Concurrency: 20 running sub-agents per session (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`), nested
  spawn depth 3 (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, raised from 1 in 2.1.219). There is no cap
  on how many agents may be _defined_.
- A finished agent can be resumed with `SendMessage`; `Explore` and `Plan` cannot.
- Sub-agents inherit the session's extended-thinking setting; there is no per-agent switch.
- **`/rewind` does not restore a background sub-agent's edits.** Checkpoints cover the main
  session's file-editing tools only. With a background-by-default fleet, git is the only undo —
  which is why the no-auto-commit rule never means no-branch.

## Model resolution

Highest wins: an explicit per-spawn model → the definition's `model:` → `CLAUDE_CODE_SUBAGENT_MODEL`
→ the main session model.

**The order reversed on 2026-08-28 (v2.1.251).** `CLAUDE_CODE_SUBAGENT_MODEL` used to override the
definition; it is now only a _default_, and the frontmatter wins. All 14 agents pin `model:`, so
they win either way — **no action needed**, but the inverse held for any reasoning recorded before
that date. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (2.1.257) overrides everything, frontmatter
included; if an agent ever runs on an unexpected tier, check that variable before editing the file.

## Agent teams — off, and why

`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` turns subagents into teammates: flat peers with a shared
task list and mailboxes. It is experimental, off by default, interactive-only, and Anthropic's own
docs warn it uses significantly more tokens.

**Do not enable it on this repo.** Two documented behaviours would break the fleet contract:

1. **A named subagent silently launches as a teammate** while the flag is on. Every delegation in
   this project names its agent type.
2. **Teammates ignore a definition's `skills:` field.** Twelve of the fourteen agents rely on that
   preload for their domain knowledge; they would run stripped of it, and nothing would say so.

If teams are ever wanted, they are a separate architecture decision with a case study, not a flag
flipped mid-task.

## Advisory agents

`lore`, `marketing` and `content` are **advisory**: they decide and persist, they never ship the
thing they decided. They share one contract, defined here once so the three bodies do not each carry
a copy that drifts.

An advisory agent:

1. **Writes only its own skill's `references/`.** Never game code, fixtures, locale JSON or visuals.
   It recommends the change and delegates it. One carve-out, stated in the agent's own body:
   `content` additionally writes the content trees it owns — `src/assets/social/**`,
   `src/content/codex/**` and `src/json/codex.json` — because a post or a Codex entry _is_ its
   deliverable, not a decision about one. `lore` and `marketing` stay references-only.
2. **Delivers a decision with its rationale**, persisted as a reference — not a chat answer. A ruling
   that is not written down did not happen. A ruling it cannot anchor in the repo is an open
   question, and goes in the skill's open-questions file.
3. **Hands off explicitly.** Words to `content`, i18n keys to `translate`, visuals to `design`,
   mechanics to `server`/`vue`. Out-of-scope discoveries are reported, never acted on.
4. **Runs no validation** (the general sub-agent contract above), and returns the structured summary.

They are kept separate rather than merged because their judgement is not interchangeable: in-world
canon, go-to-market positioning and editorial voice are three different competences, and a merged
agent would have to load all three skill sets to answer any one request. What was duplicated was the
contract, not the agents — so the contract moved here.

## Coherence with `CLAUDE.md`

`scripts/audit.py` enforces (as ERRORS):

- Every file in `.claude/agents/` has a corresponding row in `CLAUDE.md` § Agents directory.
- Every agent name referenced in that section exists as `.claude/agents/<name>.md`.

## When to create a new sub-agent (vs. extending one)

Create a new agent when:

- A class of tasks has a **clear domain boundary** (e.g., i18n JSON handled by a `data-i18n` agent: locale files, fleet parallelism is natural).
- Tasks need a **different tool set or model** (`hooks` runs only `Bash` on `haiku`; `review` is read-only).
- The orchestrator would otherwise **repeat the same long preamble** to delegate the work.

Extend an existing agent when:

- The new task fits inside an existing scope (e.g., a new Vue pattern → still the `vue` agent).
- Splitting would just mean two agents called in sequence on the same files.

## Anti-patterns specific to agents

- **A sub-agent that validates its own work.** Violates the centralised-validation rule.
- **A sub-agent that delegates to another sub-agent.** Sub-agents stay flat; only the orchestrator delegates. Single sanctioned exception: `review` fans out `review` workers via `Agent` on large diffs (≥ 5 files / ≥ 2 domains) — a review must cover its whole surface in one pass. Fanning out to `general-purpose` would be a defect: that type carries `Edit`/`Write`, so the read-only guarantee would end at the first hop.
- **An agent body that restates its own skill.** The body and the skill drift apart, and the reader cannot tell which is authoritative. Name the skill in `skills:` and delete the restatement; keep in the body only what the skill does not own.
- **An agent description that lists "use for any …" without anti-triggers.** Triggers on too much.
- **Agents kept "in case we need them".** Each agent costs context and decision overhead.
