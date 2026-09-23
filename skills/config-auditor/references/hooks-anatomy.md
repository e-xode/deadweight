<!-- The worked examples in this file (names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Hooks anatomy

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Contents: [Reading this page](#reading-this-page) · [Where a hook is declared — and what audit.py reads](#where-a-hook-is-declared--and-what-auditpy-reads) · [Events](#events) · [Matchers](#matchers) · [`if`](#if) · [Handler types and required fields](#handler-types-and-required-fields) · [Timeouts](#timeouts) · [Exit codes: what blocks and what only looks like it](#exit-codes-what-blocks-and-what-only-looks-like-it) · [Stdout: the part that enters the context](#stdout-the-part-that-enters-the-context) · [Exec form and shell form](#exec-form-and-shell-form) · [Trust, `-p`, and frontmatter hooks](#trust--p-and-frontmatter-hooks) · [`once`, `async`, `disableAllHooks`](#once-async-disableallhooks) · [House conventions](#house-conventions) · [Not checked by audit.py](#not-checked-by-auditpy)

## Reading this page

A hook is the only piece of a configuration that **executes**. Everything else is text the model may
or may not read; a hook runs code on an event, before anyone reads anything. Its characteristic
failure is not an error but a **non-event**: a hook that never fires, or fires and gates nothing,
produces no output a human would notice.

Each rule below is tagged. **[doc]** cites the page on `code.claude.com/docs/en/` and the section
(`hooks § Common fields`). **[house]** is this plugin's convention, not Anthropic's. **[inference]**
follows from documented behaviour but is not stated in those words. When audit.py covers a rule, its
check id is named; when it does not, the rule says so.

## Where a hook is declared — and what audit.py reads

[doc] `hooks § Hook locations` lists seven homes, all in the same JSON shape:

| Home | Scope | audit.py reads it? |
| :--- | :--- | :--- |
| `~/.claude/settings.json` | every project of this user | no — outside the audited root |
| `.claude/settings.json` | the project, shared | **yes** (project layout) |
| `.claude/settings.local.json` | the project, this user | **yes** (project layout) |
| managed policy settings | organisation | no |
| plugin `hooks/hooks.json` | while the plugin is enabled | **yes** (plugin layout) |
| plugin manifest `hooks` field (path, array or inline object — `plugins-reference`) | same | **no** |
| skill frontmatter `hooks:` | rest of the session once the skill is invoked | **no** |
| subagent frontmatter `hooks:` | while that subagent runs | **no** |

Said plainly: the `35-hooks-*` checks see settings files in a project and `hooks/hooks.json` in a
plugin. A hook declared in a SKILL.md or agent frontmatter, or inline in `plugin.json`, is invisible
to them today — read those by hand.

Facts that change what a declaration means:

- [doc] Hook entries **merge** across settings levels; they do not replace each other. User, project
  and local add hooks; none removes a managed one (`hooks § Hook locations`).
- [doc] The same handler defined in more than one settings file runs **once**; a plugin's or a
  skill's copy of it stays separate (`hooks § Hook handler fields`). Two identical hooks in
  `settings.json` and a plugin therefore run twice.
- [doc] Settings, managed and plugin hooks also fire inside subagents, with `agent_id`/`agent_type`
  in the input (`hooks § Hook locations`).
- [doc] A **plugin agent's** `hooks:` frontmatter is ignored, for security reasons — copy the agent
  into `.claude/agents/` to use it (`plugins-reference § Plugin agent frontmatter`). Not checked.
- [doc] Cloud sessions do not read `~/.claude/settings.json` (`hooks § Hook locations`): a hook the
  team relies on must be committed or shipped by a plugin.

## Events

[doc] 33 events (`hooks § Hook lifecycle`, table). audit.py holds the list in `KNOWN_HOOK_EVENTS`.

- **`35-hooks-parse`** — the file is not valid JSON. [doc] In an interactive session this raises a
  Settings Error dialog; a `-p` run shows nothing and skips the file (`settings § Fix a broken
  settings file`).
- **`35-hooks-shape`** — `hooks` is not an object of event → list, an entry is not an object, an
  entry has no `hooks` list, a handler is not an object or has an unknown `type`.
- **`35-hooks-event`** — an event name outside the 33. [doc] It is dropped as a *Settings Warning*
  at interactive start-up, the rest of the file staying in effect (`settings § Fix a broken settings
  file`); in `-p` nothing is shown. The hook never fires. Casing counts: `preToolUse` is a typo.

Cadence matters for cost [doc]: `SessionStart`/`SessionEnd` per session, `UserPromptSubmit`/`Stop`
per turn, `PreToolUse`/`PostToolUse` on every tool call (`hooks § Hook lifecycle`).

## Matchers

[doc] `hooks § Matcher patterns`. How a matcher string is evaluated depends on its characters:

| Matcher | Evaluated as |
| :--- | :--- |
| `"*"`, `""`, omitted | match all |
| only letters, digits, `_`, `-`, spaces, `,`, `\|` | exact string, or exact list split on `\|` or `,` |
| any other character | JavaScript regex, **unanchored** (`RegExp.test`) |

What fails silently:

- **Regex by accident.** One dot or bracket and the whole matcher becomes an unanchored regex:
  `Edit.*` also matches `NotebookEdit`. Anchor with `^…$` [doc]. A matcher written in permission
  syntax, `Bash(git *)`, is a regex that no tool name satisfies [inference] — use `if` for that.
- **Hyphens.** In the exact set only since v2.1.195; earlier, `api-socket` was a regex and also hit
  `legacy-api-socket` [doc].
- **`FileChanged` and `StopFailure`** use a narrower exact set (letters, digits, `_`, `|`): a hyphen,
  space or comma sends the matcher to the regex path, and only `|` separates alternatives [doc].
- **Case.** Matchers are case-sensitive (`hooks-guide § Hook not firing`).
- **`35-hooks-matcher` (WARN)** — a matcher on an event without matcher support (`UserPromptSubmit`,
  `PostToolBatch`, `Stop`, `TeammateIdle`, `TaskCreated`, `TaskCompleted`, `WorktreeCreate`,
  `WorktreeRemove`, `MessageDisplay`, `CwdChanged`). [doc] "silently ignored": the hook fires on
  every occurrence while the file reads as if it filtered.
- **`35-hooks-matcher` (ERROR)** — a bare server prefix `mcp__<server>`. It holds only exact-match
  characters, so it is compared as an exact string and **matches no tool**; write `mcp__<server>__.*`
  [doc] (`hooks § Match MCP tools`). The same string in a *permission rule* matches every tool of
  that server (`permissions § MCP`) — the one place where the two syntaxes diverge in effect.
- **Plugin-bundled MCP servers** are named `mcp__plugin_<plugin>_<server>__<tool>`; a matcher on the
  bare server key never fires [doc]. Not checked.

## `if`

[doc] `hooks § Common fields`. `if` holds one permission rule (`"Bash(git *)"`, `"Edit(*.ts)"`) and
filters a single handler.

- **`35-hooks-if`** — `if` on a non-tool event. It is evaluated only on `PreToolUse`, `PostToolUse`,
  `PostToolUseFailure`, `PermissionRequest`, `PermissionDenied`; elsewhere "a hook with `if` set
  **never runs**" [doc]. Not ignored — disabled.
- **`35-hooks-if`** — `&&`, `||` or a list inside `if`. There is no combination syntax; one handler
  per condition [doc].
- [doc] `if` is **best-effort**: when Claude Code cannot tell what a Bash input runs (`$VAR`, `$()`)
  it runs the hook anyway. "Use the permission system rather than a hook to enforce a hard allow or
  deny."
- [doc] Since v2.1.214, `Edit(src/**)` matches `src` in the working directory only; `**/src/**` for
  any depth. An older `if` silently narrowed on upgrade. Not checked.

## Handler types and required fields

[doc] `hooks § Hook handler fields`. Five types; `type` is required.

| `type` | Required | Default timeout |
| :--- | :--- | :--- |
| `command` | `command` | 600 s |
| `http` | `url` | 600 s |
| `mcp_tool` | `server`, `tool` | 600 s |
| `prompt` | `prompt` | 30 s |
| `agent` (experimental) | `prompt` | 60 s |

**`35-hooks-shape`** reports an unknown type and a missing required field. Caveat: audit.py reads a
handler with no `type` as `command`, which the doc does not sanction — a handler missing `type` is
not flagged as such.

Silent failures by type [doc]:

- `http`: non-2xx, connection failure, and a 2xx with a plain-text body are all **non-blocking**; an
  HTTP hook cannot block through a status code, only through a JSON decision in a 2xx body
  (`hooks § HTTP response handling`). `allowedHttpHookUrls`, when set at any level, filters HTTP
  hooks from every source.
- `mcp_tool`: a server that is not connected, or `isError: true`, is non-blocking. On `SessionStart`
  **at launch** and on every `Setup`, `mcp_tool` hooks are **skipped** — servers are not yet
  available — with a line in the debug log only (`hooks § MCP tool hook fields`). Use a `command`
  hook for what the first turn needs. Not checked.
- `mcp_tool` for a plugin server names it `plugin:<plugin>:<server>`, not the bare key.

## Timeouts

[doc] `hooks § Common fields`; `hooks-guide § Limitations`.

- **`35-hooks-timeout`** — a `command` hook with no explicit `timeout`. Defaults for `command`,
  `http`, `mcp_tool`: 600 s; lowered to 30 s on `UserPromptSubmit`, `PreModelSwitch`,
  `PostModelSwitch`; 10 s on `MessageDisplay`. `SessionEnd` hooks **share** a 1.5 s budget, raised
  to the longest per-hook `timeout` set, up to 60 s. audit.py warns when the implied default is
  ≥ 60 s and informs below.
- [doc] A timed-out `command`/`http`/`mcp_tool` hook is cancelled and its output discarded. On
  `PreToolUse` it **does not block**: the call continues through the normal permission flow — a
  stalled gate is an open gate (`hooks § Timeouts`). On `UserPromptSubmit` its `additionalContext`
  is lost and the prompt goes through without it. On `PreModelSwitch` a timeout **blocks**.

## Exit codes: what blocks and what only looks like it

[doc] `hooks § Exit code output`.

- **Exit 2** is the only code that blocks through the code alone, on events that can block; not even
  a JSON `"allow"` overrides it.
- **Exit 1 does not block.** Without valid JSON it is a non-blocking error: a `<hook> hook error`
  notice and the action proceeds. A policy script written in the Unix habit (`exit 1` on violation)
  **gates nothing**.
- **A script that cannot start** (missing, not executable) exits 127 — the same non-blocking
  bucket. The doc's own words: "a mistyped path in `settings.json` leaves the gate silently
  disabled". **`35-hooks-command`** (ERROR) catches the missing file, and (WARN) a script invoked
  directly without `+x`.
- **Events that cannot block**: exit 2 on `PermissionRequest` is not honoured — deny through the
  `decision` object; on `PostToolUse` it only shows stderr to Claude; on `SessionStart`,
  `SubagentStart`, `PostModelSwitch` it only shows a notice to the user (`hooks § Exit code 2
  behavior per event`). Checking a gate's event against that table is manual.
- `WorktreeCreate`/`WorktreeRemove` fail on **any** non-zero code.
- [doc] A `Stop` hook that blocks eight times in a row without progress is overridden; test
  `stop_hook_active` (`hooks-guide § Stop hook hits the block cap`).
- [doc] A `PreToolUse` hook's `deny` holds even in `bypassPermissions`; its `allow` cannot loosen past
  a settings deny rule (`hooks-guide § Hooks and permission modes`).

## Stdout: the part that enters the context

[doc] `hooks § Exit code 0`. For most events stdout goes to the debug log. On **`UserPromptSubmit`,
`UserPromptExpansion`, `SessionStart`, `PostModelSwitch`**, plain-text stdout is **added to the
context** Claude sees.

- **`35-hooks-context`** (INFO) lists the file's hooks on those four events. Whatever they print is
  paid in tokens on every session or every turn — a cost `/context` does not show before the hook
  runs, because it prices declarations, not output [inference].
- [doc] Plain stdout, `additionalContext`, `systemMessage` and `initialUserMessage` are each capped
  at 10,000 characters; beyond, the text is saved to a file and replaced by its path plus a
  2,000-character preview, and Claude is not asked to read the file (`hooks § JSON output`).
- [doc] JSON is parsed only if stdout starts with `{` and ends with `}`. A shell profile that
  `echo`es on start-up prepends text: the JSON becomes plain text, **no error on exit 0**
  (`hooks-guide § Hook JSON has no effect`).
- [doc] A decision field at the wrong level (`permissionDecision` outside `hookSpecificOutput`) is
  ignored without an error; `claude --debug` logs `Hook JSON output had unrecognized keys`.
- [doc] Stderr on exit 0 reaches the debug log only; Claude never sees it.

## Exec form and shell form

[doc] `hooks § Exec form and shell form`.

- `args` present → **exec form**: `command` is spawned directly, each `args` element is one argument,
  placeholders substituted as plain strings, no shell. `args` absent → **shell form** (`sh -c`,
  Git Bash, or PowerShell).
- Prefer exec form whenever a path placeholder appears; in shell form, double-quote each one.
- In exec form, a bare `command` containing whitespace (`"node scripts/lint.js"`) fails to spawn;
  Claude Code logs a warning. Move tokens into `args`.
- **`${user_config.KEY}`** is substituted in plugin hooks in **exec form only**. A shell-form plugin
  hook that references it **fails with an error instead of running** (since v2.1.207); read
  `$CLAUDE_PLUGIN_OPTION_<KEY>` instead. Not checked by audit.py.
- **`35-hooks-command`** (ERROR) — `${CLAUDE_PLUGIN_ROOT}` in a **project** hook. [house] One
  variable cannot designate one plugin among those installed; a hook that needs a plugin's files is
  shipped by that plugin. Use `${CLAUDE_PROJECT_DIR}` for project scripts.
- Limit of the check: `35-hooks-command` resolves path tokens in `command` only. In exec form the
  script usually sits in `args` (`"command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/…"]`), and a
  missing script there is **not** reported.

## Trust, `-p`, and frontmatter hooks

[doc] `hooks § Workspace trust`; `permissions § What runs before you trust a folder`.

| Hook source | Interactive, folder not trusted | `claude -p` / SDK, never trusted |
| :--- | :--- | :--- |
| any settings file (user included) | held back until the trust dialog is accepted | **run** — `-p` counts as trusted |
| project skill frontmatter | same rule as settings | **run** |
| project subagent frontmatter | not run, no dialog offered, until *this* folder is trusted | **not run** |
| plugin agent frontmatter | ignored in every case (`plugins-reference`) | ignored |

Consequences: a hook committed in a repository runs on the first `claude -p` over a fresh clone. The
doc's remedy for scripting over a repository you did not write: review `.claude/`, use `--bare`, or
`--settings '{"disableAllHooks": true}'` — a `disableAllHooks` in user settings alone is not
enough, since project settings outrank it and can set it back to `false`. Conversely, a subagent
hook that works interactively is silently absent in CI. Not checked by audit.py.

## `once`, `async`, `disableAllHooks`

- **`once: true`** [doc] is honoured **only in skill frontmatter**; in settings files and agent
  frontmatter it is ignored, so the hook runs every time (`hooks § Common fields`). A failed,
  blocking or timed-out run leaves it in place. Not checked.
- **`async: true`** [doc] exists on `command` hooks only. An async hook cannot block or decide —
  `decision`, `permissionDecision`, `continue` have no effect; `timeout` is not enforced on it; in
  `-p` it is killed at teardown (`hooks § Run hooks in the background`). An async "gate" is a
  contradiction. `asyncRewake` wakes Claude on exit 2 and keeps the timeout.
- **`disableAllHooks`** [doc] follows settings precedence (a project `false` beats a user `true`),
  cannot switch off managed hooks from outside managed settings, and also turns off the custom
  **status line** and the `@` file-suggestion command (`settings-reference § disableAllHooks`;
  `statusline § Troubleshooting`). There is no per-hook disable.

## House conventions

- [house] A hook is an architecture decision taken by the maintainer, recorded with its reason —
  never added by an agent in passing. See [antipatterns.md](./antipatterns.md) § D1.
- [house] A hook that adds time to every task (a test suite on `Stop`, a linter on every `Edit`) is
  refused; an observation hook that only measures and blocks nothing is the exception.
- [house] Every gate states its failure mode: exit 2, an explicit `timeout`, and a first run
  watched for the `hook error` notice.
- [house] A hook on a context-injecting event prints the minimum; its output is budgeted like a
  `CLAUDE.md` line.

## Not checked by audit.py

Read these by hand: hooks in skill, agent and inline `plugin.json` declarations; `once` outside
skill frontmatter; `async` on a gate; exit 2 on an event that cannot block; `mcp_tool` on
`SessionStart`/`Setup`; plugin-scoped MCP names in matchers; `${user_config.*}` in shell form;
scripts named only in `args`; a handler with no `type`; the output size of context-injecting hooks.
Confirm what actually loaded with `/hooks` (source per hook) and `claude --debug-file <path>`.
