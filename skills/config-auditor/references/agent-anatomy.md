<!-- The worked examples in this file (agent names like `shop-review`, `api-socket`,
     `ui-scss`, `data-i18n`) describe one fictional project: an online shop, Node SSR,
     with a design system, a socket API and a content team. It is invented, and it is
     deliberately not a pair of meaningless placeholders: a model learns from the SHAPE
     of an example, and a name with no domain teaches nothing about naming, scoping or
     overlap. Where only the structure matters, the examples use <angle-bracket>
     placeholders instead, which cannot rot into dead references. -->

# Sub-agent anatomy

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Contents: [How to read this page](#how-to-read-this-page) · [Folder and file](#folder-and-file) · [Frontmatter](#frontmatter) · [Tools](#tools) · [Permission mode](#permission-mode) · [Model resolution](#model-resolution) · [What a sub-agent receives](#what-a-sub-agent-receives) · [Foreground and background](#foreground-and-background) · [Agents shipped by a plugin](#agents-shipped-by-a-plugin) · [Agent teams](#agent-teams) · [The delegation message](#the-delegation-message) · [House conventions](#house-conventions) · [When to create a new sub-agent](#when-to-create-a-new-sub-agent) · [Anti-patterns](#anti-patterns)

## How to read this page

Every statement carries one of three registers:

- **doc** — stated by an official page, linked where it is used. Sources: [sub-agents], [agent-teams],
  [tools-reference], [permissions], [sdk-subagents].
- **measured** — produced by running something; the command is named.
- **house convention** — this plugin's own rule, with its reason. `audit.py` reports these as WARN,
  never ERROR: a convention is an opinion, and an audit must not dress an opinion as a spec.

`audit.py` check identifiers are given in brackets, e.g. `[23-agent-tools]`.

## Folder and file

```
.claude/agents/<agent-name>.md        project scope
~/.claude/agents/<agent-name>.md      user scope
```

All doc, [sub-agents]:

- **Priority** when two scopes define the same `name`: managed settings > `--agents` CLI flag >
  project `.claude/agents/` > user `~/.claude/agents/` > a plugin's `agents/`.
- **Subfolders are scanned recursively** (`agents/review/`, `agents/research/`). The path does not
  affect identity; identity comes only from `name`. In a plugin, by contrast, a subfolder becomes part
  of the scoped identifier.
- **The filename does not have to match `name`.** Keeping them equal is a readability habit, not a rule.
- **Duplicate `name` in the same tree**: one file is loaded, chosen by filesystem read order — no
  documented precedence. `[08-agent-frontmatter]` warns.
- **A `:` in `name`** is reserved for plugin-scoped identifiers: since 2.1.218 the file is not loaded,
  and the error goes only to the debug log. `[08-agent-frontmatter]` reports it as ERROR.
- A frontmatter that does not parse can be found with `claude plugin validate .claude/agents`.

`[08-agents-dir]` notes a missing `.claude/agents/`; `[08-agent-frontmatter]` requires valid YAML with
`name` and `description` (the only two required fields).

## Frontmatter

```yaml
---
name: shop-review
description: '<when to delegate here, and when not - same rules as a skill description>'
tools: Read, Grep, Glob
model: sonnet
---
```

### The eighteen fields

Doc, [sub-agents]. A key outside this list is **ignored without an error** — `[23-agent-frontmatter-keys]`
reports it, because a typo such as `tool:` silently widens the agent to every tool.

| Field | What the doc says | Note |
| --- | --- | --- |
| `name` | Required. Lowercase + hyphens; hooks receive it as `agent_type`. | See [Folder and file](#folder-and-file). |
| `description` | Required. When Claude should delegate here. | Combined custom descriptions over **15,000 tokens** trigger a startup warning. `[08b-agent-description]`: 80–900 chars and an anti-trigger clause (house convention: the description is the only routing signal, and it is paid every turn). |
| `tools` | Optional; inherits every tool available to sub-agents if omitted. | See [Tools](#tools). `[23-agent-tools]` |
| `disallowedTools` | Removed from the inherited or listed set. | An entry with a specifier (`Bash(git push *)`) still removes the **whole** tool. |
| `model` | `sonnet`, `opus`, `haiku`, `fable`, `inherit`, or a full model id. | See [Model resolution](#model-resolution). `[23-agent-model]` |
| `permissionMode` | `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`, or `manual`. | See [Permission mode](#permission-mode). `[23-agent-permission-mode]` |
| `maxTurns` | Hard stop; output marked partial (2.1.246+), resumable. | The cheapest guard on a loop that can fail to converge. |
| `skills` | Preloads the **full content** of the named skills at startup. | Controls preloading, **not access** — see [Tools](#tools). `[23-agent-skills-preload]` |
| `mcpServers` | Server names or inline definitions scoped to this agent. | Inline servers from a project agent load only once the folder is trusted. |
| `hooks` | Lifecycle hooks scoped to the agent; `Stop` becomes `SubagentStop`. | Project-agent hooks are **skipped until the folder is trusted**; a `-p` session does not count as trusted. |
| `memory` | `user`, `project` or `local`: a persistent directory; first 200 lines / 25 KB of its `MEMORY.md` injected. | **Automatically enables `Read`, `Write`, `Edit`** — see [Anti-patterns](#anti-patterns). |
| `background` | `true` keeps the agent in the background even when Claude asks for foreground. | See [Foreground and background](#foreground-and-background). |
| `omitClaudeMd` | `true` launches without user/project/local CLAUDE.md (managed policy still loads). 2.1.271+. | Ignored when the agent runs as the main session via `--agent`. |
| `effort` | `low`, `medium`, `high`, `xhigh`, `max`; overrides the session level. | Try this before promoting an agent a whole model tier (house convention: effort is cheaper to reverse). |
| `isolation` | `worktree`: a temporary git worktree branched from the default branch, cleaned up if unchanged. | Worth it only for parallel writers on the same files. |
| `color` | Display colour in the task list and transcript. | — |
| `initialPrompt` | First user turn when the agent runs as the main session (`--agent`). | — |
| `experimental` | A map; `cacheTtl: 5m` or `1h` sets this agent's prompt-cache lifetime. | Must sit inside the map, not at top level. `1h` is ignored while on usage credits. |

## Tools

All doc unless marked.

**Vocabulary.** The valid names are those of [tools-reference] (46 at the date above). This page does
not copy the list — it would rot. `[23-agent-tools]` checks every `tools` entry against it: an entry
that resolves to nothing is dropped (WARN); if **no** entry resolves, the agent fails to launch (ERROR).
Parameterised forms (`Bash(git diff *)`) and `mcp__*` names are accepted.

**`Task` is `Agent`.** The fan-out tool was renamed `Agent` in 2.1.63; `Task(...)` in agent
definitions and settings still works as an alias ([sub-agents]). `[23-agent-tools]` reports it as INFO.
In the SDK the tool still appears as `"Task"` in the `system:init` list ([sdk-subagents]).

**`TaskOutput` — the docs disagree.** [tools-reference] lists it as *deprecated in favor of `Read` on
the task's output file path*; [permissions] calls it one of "the tools Claude Code has removed". Either
way, do not grant it. `[23-agent-tools]` reports it as deprecated (INFO).

**Removed from every sub-agent**, even when listed ([sub-agents]): `AskUserQuestion`, `EndConversation`,
`EnterPlanMode`, `ScheduleWakeup`, `WaitForMcpServers`, `Workflow`; `ExitPlanMode` **unless**
`permissionMode: plan`; `Agent` at the spawn-depth limit (3 layers by default,
`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`). A sub-agent cannot ask the user anything: its prompt must be
self-sufficient.

**Background set.** A background sub-agent keeps every MCP tool but only these built-ins: `Read`,
`Grep`, `Glob`, `LSP` (2.1.280+), `Bash`, `PowerShell`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`,
`WebSearch`, `TodoWrite`, `Skill`, `ToolSearch`, `EnterWorktree`, `ExitWorktree`, `Monitor`, `TaskStop`,
`SendMessage`, `Artifact`, plus `SubagentHandback` for an agent that reports through it. The removal is
silent. **The same definition resolves to different tools in the foreground and the background**, so a
contract built on a tool outside this set holds only half the time.

**`Agent(<type>)` restricts nothing in a sub-agent.** The type allowlist applies only to an agent run as
the main thread with `claude --agent`. In a sub-agent definition, `Agent` lets it spawn (within the depth
limit) and **the list in parentheses is ignored**. `[23-agent-tools]` warns. Consequence: an exception
like "`shop-review` may fan out, but only to `shop-review` workers" can be held **only by the prompt**,
not by the frontmatter.

**`skills` is not an access control.** Without it the agent can still discover and invoke project, user
and plugin skills through `Skill`. To forbid skills, omit `Skill` from `tools`. A skill carrying
`disable-model-invocation: true` cannot be preloaded — `[23-agent-skills-preload]` warns, and also warns
when a preloaded name has no `SKILL.md` in the repository.

## Permission mode

Doc, [sub-agents]:

- Unset → the agent inherits the main conversation's mode.
- Parent in `bypassPermissions`, `acceptEdits` or `auto` → the agent runs in **that** mode, and its own
  `permissionMode` is ignored.
- Parent in `default`, `dontAsk` or `plan` → the agent's mode applies, **except** `bypassPermissions`:
  since 2.1.267 an agent that declares it keeps the main conversation's mode instead.
- `manual` is an alias of `default` (2.1.200+).

`[23-agent-permission-mode]` warns on an unknown value and on `bypassPermissions` (it no longer does
what it says).

## Model resolution

Doc, [sub-agents]. First match wins:

1. the model Claude passes for that spawn;
2. the definition's `model:` (`inherit` = the main conversation's model);
3. `CLAUDE_CODE_SUBAGENT_MODEL`;
4. the main conversation's model.

`CLAUDE_CODE_SUBAGENT_MODEL` is therefore a **default**, not an override (it came first before 2.1.251).
To force one model everywhere, set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`; then every definition's `model`
is ignored. If an agent runs on an unexpected model, check those two variables before editing the file.

**A family alias follows the parent.** When the main conversation's model belongs to the alias's family,
`model: opus` resolves to the parent's **exact** model, `[1m]` suffix included — not to the version the
alias points to. An alias in `CLAUDE_CODE_SUBAGENT_MODEL` always resolves to the aliased version.
Extended thinking is inherited from the session; there is no per-agent switch.

## What a sub-agent receives

Doc, [sub-agents]. A non-fork sub-agent starts with a fresh context:

- its own body as system prompt, and the delegation message;
- the **CLAUDE.md hierarchy**, unless `omitClaudeMd: true`. The built-in `Explore` and `Plan` skip it;
- a **git-status snapshot**, unless turned off with `includeGitInstructions`. `Explore` and `Plan` skip it;
- the full content of every skill in `skills:`;
- a **sibling roster** (2.1.206+): `main` and every other named agent in the session, each a valid
  `SendMessage` target — when the agent has `SendMessage` and there is at least one other.

It does **not** see the conversation, the files already read, or the skills already invoked. A rule that
must reach `Explore` or `Plan` has to be restated in the delegation message.

Also doc: at most 20 sub-agents running at once per session; a finished custom agent can be resumed with
`SendMessage`, but `Explore` and `Plan` are one-shot and cannot.

Consequences for an agent body (house convention, reason: the body is loaded on every spawn):

- Do not restate CLAUDE.md hard rules — every agent without `omitClaudeMd` already has them.
- Do restate what the agent cannot infer from its own domain skill.
- An agent built to take everything from its delegation message (a narrow worker) is the case
  `omitClaudeMd: true` exists for.

## Foreground and background

Doc, [sub-agents]. For each spawn, the first matching case decides:

1. spawned by an in-process agent-team teammate → foreground;
2. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` → foreground, everywhere;
3. **fork mode on** (the default in an interactive session) → background, and Claude **cannot** ask for
   the foreground;
4. **fork mode off** (the default in `-p` and in the Agent SDK) → background by default, **foreground when
   Claude needs the result before continuing**. `background: true` keeps an agent in the background
   even then.

So neither "interactive = background, `-p` = foreground" nor its inverse holds. In `-p` / SDK runs a
sub-agent can land on either side, and therefore on either tool set. Build nothing on a tool outside the
[background set](#tools).

## Agents shipped by a plugin

Doc, [sub-agents]: a plugin agent **ignores `hooks`, `mcpServers` and `permissionMode`** (security), and
`initialPrompt`. To use them, copy the file into `.claude/agents/` or `~/.claude/agents/`.
`[23-agent-frontmatter-keys]` warns when an agent under a plugin layout sets one.

## Agent teams

Doc, [agent-teams]. `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` makes agents flat teammates with a shared
task list and mailboxes. Experimental, off by default, and "significantly more tokens" than a single
session: each teammate is a separate instance with its own context.

What changes for a definition used as a teammate:

- **A named sub-agent launches as a teammate** while the flag is on — including delegation you never
  framed as team work, since Claude can name agents on its own. Set the variable to `0` to restore
  sub-agents.
- **`skills` is ignored.** The teammate still loads the project's and the user's skills like any session;
  it loses only the **preload**. An agent whose body assumes its skill is already in context will run
  without it, and nothing says so.
- Start with **3 to 5 teammates**.
- Quality gates: the `TeammateIdle`, `TaskCreated` and `TaskCompleted` hooks can block with exit code 2
  and send feedback.

House convention: enable teams as an architecture decision, not a flag flipped mid-task — the first two
points silently change what every existing definition does.

## The delegation message

Anthropic's engineering post [multi-agent research system][research] (doc register, but a blog, not the
product docs) names what a delegation message needs: **an objective, an output format, guidance on tools
and sources, and clear task boundaries**. Vague delegation produced duplicated work and gaps. The same
post measures multi-agent runs at **about 15× the tokens of a chat** — the fan-out has to buy something.

## House conventions

These are this plugin's rules, not the harness's. Each is reported as WARN at most.

**1. An `## Agents directory` table in CLAUDE.md** — `[09-agent-in-claude-md]` (agent file with no row),
`[09-claude-md-agent-missing]` (row with no file). The harness does **not** need it: it already lists
every agent's description to the model. The table is therefore **paid twice** in the always-loaded
budget. Its reason: a human entry point — one place where a reader sees the roster and the delegation
triggers without opening each file. A repository that does not want that trade can ignore both checks.

```markdown
## Agents directory

| Agent | Delegate when |
| --- | --- |
| `shop-review` | A diff touches ≥ 5 files or ≥ 2 domains; read-only. |
| `data-i18n` | Locale JSON changes; never touches components. |
```

**2. The sub-agent contract.** Reason: the orchestrator is the only one that sees the whole task.

1. **Scoped work.** The agent does the scope it was given. Out-of-scope discoveries are reported, not acted on.
2. **Centralised validation.** Test/build/lint runs where the orchestrator decides, once, at task end —
   not in every agent, which would multiply cost and produce conflicting verdicts.
3. **Structured return.** What was done / files modified / blockers / suggested follow-ups.
4. **Self-contained prompts** when several agents run in parallel — they share no context.

**3. Minimal `tools`.** Reason: an unused grant is an unenforced boundary. Prefer `disallowedTools` when
the agent needs almost everything.

## When to create a new sub-agent

House convention. Create one when:

- a class of tasks has a **clear domain boundary** (locale files → `data-i18n`, parallel by nature);
- it needs a **different tool envelope or model** (`shop-review` read-only; a mechanical runner on `haiku`);
- the orchestrator would otherwise **repeat the same long preamble** on every delegation.

Extend an existing one when the task fits its scope (a new component pattern → still `ui-scss`), or when
splitting would only mean two agents called in sequence on the same files.

## Anti-patterns

- **A read-only agent that declares `memory`.** `memory` enables `Read`, `Write` and `Edit` automatically
  (doc, [sub-agents]): the read-only envelope is gone, and the frontmatter still looks read-only.
- **Restricting fan-out with `Agent(<type>)` in a sub-agent.** Ignored (doc). If `shop-review` fans out,
  the prompt must say "spawn only `shop-review` workers" — and fanning out to `general-purpose` would be a
  defect, since that type carries `Edit`/`Write` and the read-only guarantee ends at the first hop.
- **`skills:` used to fence an agent in.** It preloads; it does not restrict. Remove `Skill` from `tools`.
- **`disallowedTools: Bash(git push *)` to block one command.** It removes all of `Bash`. Use a
  permission rule or a hook for command-level control.
- **A body that restates its own skill.** The two drift and the reader cannot tell which is
  authoritative. Name the skill in `skills:` and keep in the body only what the skill does not own.
- **A contract that needs a tool outside the background set.** It holds in the foreground only.
- **Hooks in a project agent relied on in CI.** Skipped in `-p` (the folder is not trusted there).
- **A description that says "use for any …" with no anti-trigger.** `[08b-agent-description]`.
- **Agents kept "in case we need them".** Each costs listing tokens every turn and a routing decision.

[sub-agents]: https://code.claude.com/docs/en/sub-agents
[agent-teams]: https://code.claude.com/docs/en/agent-teams
[tools-reference]: https://code.claude.com/docs/en/tools-reference
[permissions]: https://code.claude.com/docs/en/permissions
[sdk-subagents]: https://code.claude.com/docs/en/agent-sdk/subagents
[research]: https://www.anthropic.com/engineering/multi-agent-research-system
