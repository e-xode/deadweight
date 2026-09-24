<!-- The worked examples in this file (names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Settings and permissions anatomy

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Contents: [Reading this page](#reading-this-page) · [Files and precedence](#files-and-precedence) · [Key scope: a key that is valid and inert](#key-scope-a-key-that-is-valid-and-inert) · [Rule order: deny, ask, allow](#rule-order-deny-ask-allow) · [Rule syntax per tool](#rule-syntax-per-tool) · [Rules rejected silently vs. reported](#rules-rejected-silently-vs-reported) · [Workspace trust](#workspace-trust) · [What a repository should not carry](#what-a-repository-should-not-carry) · [`settings.local.json` and git](#settingslocaljson-and-git) · [Status line and output style](#status-line-and-output-style) · [A Bash deny is not a security boundary](#a-bash-deny-is-not-a-security-boundary) · [Not checked by audit.py](#not-checked-by-auditpy)

## Reading this page

A settings file fails by **meaning less than it says**: a key ignored at its scope, an allow rule
that approves nothing, a deny that stops one spelling of a command. None raises an error at runtime.

Tags as in [hooks-anatomy.md](./hooks-anatomy.md): **[doc]** cites the page under
`code.claude.com/docs/en/` and its section, **[house]** is this plugin's convention, **[inference]**
follows from the doc without being stated. Check ids name the audit.py control; audit.py reads
`.claude/settings.json` and `.claude/settings.local.json` of the audited root, nothing else — not
user, managed or `--settings` values.

## Files and precedence

[doc] `settings § Settings precedence`, highest first:

1. **Managed** (`managed-settings.json`, MDM, server-managed) — nothing overrides it, `--settings`
   included, apart from a short list of security keys where a stricter lower value wins
   (`settings § Exceptions to managed settings precedence`).
2. **Command line** (`--settings`, `--model`, `--permission-mode`…) — one session.
3. **Project local** `.claude/settings.local.json`.
4. **Shared project** `.claude/settings.json`.
5. **User** `~/.claude/settings.json`.

Environment variables are not a level; each variable/key pair has its own rule (`settings`). A
fifth file, `~/.claude.json`, holds trust decisions, MCP configurations and the *Global config* keys.

- [doc] **Lists merge** instead of overriding (`permissions.allow` from every file combine), except
  `fallbackModel`, `modelPicker`, `availableModels` and `modelSettings`, which have their own rules
  (`settings § Lists merge instead of overriding`). A project cannot remove a user's allow rule; it
  can only add a deny.
- [doc] Shared `.claude/settings.json` is read from the session's primary working directory: a file
  committed at the repository root does not apply to a session started in `api-socket/`
  (`settings § Where Claude Code keeps the local file`).
- **`24-settings-parse`** — invalid JSON or not an object. [doc] Interactive start-up shows a
  Settings Error dialog; a `-p` run skips the file silently, and `claude doctor` says what was
  dropped (`settings § Fix a broken settings file`).
- **`24-settings-keys`** (INFO) lists the top-level keys, for the reader to compare with intent.

## Key scope: a key that is valid and inert

[doc] `settings-reference § Settings index`: each of the 231 keys carries a **Scope** — `Any file`,
`User, local, or managed`, `User or managed`, `Managed`, or `Global config` (`~/.claude.json`).
A key outside its scope is ignored; the table is not reproduced here, audit.py carries it.

- **`24-settings-unknown-key`** (NOTICE) — a key absent from the reference: a typo, or a key newer
  than the auditor.
- **`24-settings-unknown-subkey`** (NOTICE) — a field absent from an object whose fields the
  reference lists as a closed set (`attribution`, `permissions`, `autoMode`, `sandbox`,
  `statusLine`, `worktree`…). A misspelt field is ignored like a misspelt key, one level down,
  where a top-level check does not look. Objects keyed freely (`env`, `enabledPlugins`, `hooks`)
  are not checked.
- [doc] Hiding commit and PR attribution takes all three fields: `"attribution": {"commit": "",
  "pr": "", "sessionUrl": false}` (`settings-reference § attribution`). `includeCoAuthoredBy` is
  deprecated and ignored once `commit` or `pr` is set. A CLAUDE.md or memory rule about
  attribution also wins over these lines, except in managed settings — but through the model,
  which reads the rule, not through the harness: the setting holds when the rule is not read.
- **`24-settings-scope`** (ERROR) — a key ignored in the file it sits in. Examples [doc]:
  - `modelPicker` — *User or managed*: a cloned repository cannot relabel the picker.
  - `skipDangerousModePermissionPrompt` — *User, local, or managed*: a repository cannot skip the
    dialog for you.
  - `allowManagedHooksOnly`, `claudeMd` — *Managed* only.
  - `autoConnectIde`, `diffTool` — *Global config*: they live in `~/.claude.json`, never in a
    settings file.
  - `useAutoModeDuringPlan`, `syncClaudeAiSkills`, `syncClaudeAiPlugins`: a **`false` in the shared
    `settings.json` is ignored** — the opt-out is honoured from user, local, managed or
    `--settings` only (`settings § Exceptions to managed settings precedence`).
- **`24-settings-default-mode`** (WARN) — `permissions.defaultMode` set to `auto` or
  `bypassPermissions` in project or local settings: ignored there since v2.1.257; set it in user
  settings or pass `--permission-mode` (`settings-reference § permissions.defaultMode`). Other modes
  work from a project file for terminal sessions; the VS Code extension reads only user, managed and
  `--settings` for the starting mode (`permission-modes`). See
  [antipatterns.md](./antipatterns.md) § G1.
- **`24-settings-skill-overrides`** (NOTICE) — a `skillOverrides` key naming no project skill: fine
  for a bundled, user or synced skill, dead if the skill was renamed [house].

## Rule order: deny, ask, allow

[doc] `permissions § Manage permissions`: rules are evaluated **deny, then ask, then allow**; the
first match decides, and specificity does not reorder them. `Bash(aws *)` in deny blocks
`aws s3 ls` even with `Bash(aws s3 ls)` in allow; an ask rule prompts over a narrower allow.

- **`42-permissions-conflict`** (WARN) — the same rule string in `allow` and in `deny`/`ask` of one
  file: the allow entry never applies. Limit: exact string equality within one file. A broader deny
  shadowing a narrower allow, or a deny in user settings shadowing a project allow ([doc] "deny
  rules from any scope are evaluated before allow rules", `permissions § Settings precedence`), is
  not detected.
- [doc] "Yes, and don't ask again" writes an allow rule to the local file; it does not outrank a
  project or managed ask rule, so the prompt comes back (`settings § Permission rules combine…`).
- [doc] A bare-name deny (`Bash`, `Bash(*)`, a glob like `mcp__*`) removes the tool from Claude's
  context; a scoped deny leaves it visible and blocks matching calls.
- [doc] Deny rules hold in every mode, `bypassPermissions` included (`settings-reference §
  permissions.defaultMode`).
- [doc] What `bypassPermissions` still stops (`permission-modes § Skip all checks with
  bypassPermissions mode`): a critical-path removal (`rm -rf ~`, an unguarded `rm -rf "$DIR"/*`)
  prompts, and nesting it in `( … )`, `$( … )` or `{ …; }` does not hide it; with
  `permissions.blockReadsOutsideWorkingDirectories` on, reads outside the working directories
  prompt. The mode cannot be entered from a session started without it, and cloud sessions ignore
  it from settings files, silently. It is not a safety mode: it offers no protection against
  prompt injection.

## Rule syntax per tool

[doc] `permissions § Permission rule syntax` and `§ Tool-specific permission rules`. Form: `Tool` or
`Tool(specifier)`; parentheses inside the specifier are literal.

- **Bash — space vs. `:*`.** `Bash(npm run *)`: everything before the first `*` is literal, and a
  trailing ` *` also matches the bare command. The space counts: `Bash(ls *)` misses `lsof`,
  `Bash(ls*)` hits it. `:*` is an equivalent trailing wildcard, **recognised only at the end**:
  in `Bash(git:* push)` the colon is literal and the rule matches nothing it seems to →
  **`42-permissions-rule`** (WARN).
- **Bash — compound commands.** An allow rule must match each subcommand (`&&`, `||`, `;`, `|`,
  newlines); deny and ask match any subcommand, including inside `$()`. A small fixed set of
  wrappers is stripped (`timeout`, `nice`, `nohup`…); runners like `npx`, `docker exec`,
  `devbox run` are not — `Bash(npx *)` approves whatever follows.
- [doc] A `*` before the subcommand in an allow rule (`Bash(git * main)`) draws a start-up warning.
- **Read / Edit — gitignore paths.** `//abs`, `~/home`, `/relative-to-the-settings-source`,
  `path` or `./path` relative to the current directory. A single leading `/` is **not** absolute:
  in `.claude/settings.json` it anchors at the working directory, in `~/.claude/settings.json` at
  `~/.claude/`. `Edit` rules cover every built-in editing tool; a path rule on `Write`, `Glob`,
  `NotebookEdit` or `MultiEdit` is accepted, never consulted, and warned at start-up. An allow rule
  whose path is not a usable gitignore pattern approves nothing. Not checked by audit.py.
- **Negation `!`** (deny and ask only) carves paths out of the `path`/`./path` rules listed
  **before** it, in the **same source**: `Read(*.env)` then `Read(!sample.env)`. A `!` rule listed
  first carves nothing; one in project settings does not reopen a managed deny; `!~/…` cannot reach
  an anchored rule; a carve-out cannot reopen a file under a directory denied as a whole. Not checked.
- **MCP** — `mcp__<server>` or `mcp__<server>__*` (every tool of the server), `mcp__<server>__<tool>`.
  In allow, a glob is accepted only after a literal `mcp__<server>__` prefix. **Any `mcp__` rule with
  parentheses is skipped when the file loads** → **`42-permissions-rule`** (ERROR); to match an MCP
  parameter, deny with `--disallowedTools`. Note the divergence with hook matchers: bare
  `mcp__<server>` matches all its tools here, and none in a matcher.
- **WebFetch** — `WebFetch(domain:shop.example)`; `*.shop.example` covers subdomains but not the
  apex; a middle `*` never crosses a dot. Bare `WebFetch` and `WebFetch(domain:*)` differ: only the
  `domain:` form feeds the sandbox network list.
- **Parameters** — `Tool(param:value)` works in deny and ask on built-in tools
  (`Agent(model:opus)`); on a tool's primary field (`Bash(command:rm *)`) it is ignored with a
  start-up warning.
- Use canonical tool names (`tools-reference`), not transcript labels.

## Rules rejected silently vs. reported

[doc] `permissions § Tool name wildcards`. The asymmetry is the audit's point:

| Defect | deny / ask | allow |
| :--- | :--- | :--- |
| tool name matching no known tool | start-up warning (names with `_` or `*` exempt) | no warning documented [inference: silent] → **`42-permissions-rule`** (WARN) |
| unanchored glob `"*"`, `"B*"`, `"mcp__*"` | valid: matches every tool / every MCP tool | **skipped with a warning, approves nothing** → **`42-permissions-rule`** (ERROR) |
| `mcp__…(…)` | skipped at load, listed in the invalid-settings dialog and `claude doctor` | same → **`42-permissions-rule`** (ERROR) |

[doc] Warnings appear at **interactive** start-up; a `-p` run shows no dialog (`settings § Fix a
broken settings file`). A rule nobody saw warned about is the common case in CI.

## Workspace trust

[doc] `permissions § Project allow rules and workspace trust`; `§ What runs before you trust a
folder`; `settings § A committed key doesn't reach teammates`.

- `permissions.allow`, `additionalDirectories`, `extraKnownMarketplaces` and most `env` values from
  the shared file wait for the trust dialog. `deny` and `ask` apply at once — they only restrict.
- Trust is keyed on the git repository root; nested repositories need their own.
- `claude -p` and the SDK never show the dialog: shared **allow rules are not used** (a stderr
  warning says so), while **hooks, `env`, `apiKeyHelper` and `.mcp.json` servers are used**. A
  pipeline that relies on project allow rules is running on prompts it cannot answer [inference].
- A skill's `allowed-tools` is never gated by trust.

## What a repository should not carry

- **`24-settings-env`** (WARN) — `env` in the shared file setting a variable that routes requests or
  carries a credential (`ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `*_TOKEN`, `*_SECRET`…). [doc]
  `env` values are plain text, reach every subprocess, and from a project file apply after trust —
  or at once in `-p` (`settings-reference § env`). Some variables are dropped from project and local
  `env` since v2.1.251 (`CLAUDE_CONFIG_DIR`, `HOME`, `TMPDIR`, `XDG_*`…); the credential and endpoint
  variables above are not among them. [house] The warning cites CVE-2026-21852 (Check Point
  Research) — an external source, not the docs.
- **`43-mcp-approval`** (WARN) — `enableAllProjectMcpServers` or `enabledMcpjsonServers` committed
  in the shared file. [doc] In an untrusted folder the shared file's approval is ignored; after trust
  it is honoured, and in `-p` `.mcp.json` servers connect "approved or not"
  (`settings-reference § enableAllProjectMcpServers`; `permissions § What runs before…`). Claude
  Code itself writes these keys to `settings.local.json`. [house] An approval shipped with the code
  is how CVE-2025-59536 worked (external source); approvals stay local.
- [doc] Keys a repository cannot set for you at all are the `24-settings-scope` findings above.

## `settings.local.json` and git

[doc] `settings § Keep personal settings out of a repository`.

- Claude Code adds `**/.claude/settings.local.json` to the **global** git excludes the first time
  **it** writes the file; a file created by hand is not ignored until someone adds it.
- Since v2.1.211 the file lives at the **repository root** even when the session starts in a
  subdirectory (not in a worktree: the main checkout's root).
- A **tracked** local file (or a symlinked `.claude`) is treated as repository-supplied: its allow
  rules wait for trust (`permissions § When your local settings file needs trust`).
- **`24-settings-local`** (WARN) — the file exists and the **repository's own** ignore rules do not
  cover it. audit.py disables `core.excludesFile` on purpose [house]: a global exclude protects one
  machine, and the same repository reads differently on the next clone. Limit: whether the file is
  already tracked is not checked.

## Status line and output style

- **`24-settings-statusline`** — (WARN) the `statusLine` command names a script that does not exist;
  (ERROR) `refreshInterval` below 1, the documented minimum (`statusline § Manually configure`).
  [doc] A script that exits non-zero or prints nothing gives a **blank** line, not an error; the
  status line also stays blank until the folder is trusted (debug log: `Status line command skipped:
  workspace trust not accepted`), and is off when `disableAllHooks` is `true` outside managed
  settings (`statusline § Troubleshooting`).
- **`24-settings-output-style`** — [doc] `outputStyle` is **case-sensitive**; a value that does not
  match exactly (`explanatory`) gives the **Default** style, silently, while `/output-style` ignores
  case (`output-styles`). WARN when the value differs from a known style by case only; NOTICE when it
  matches no built-in and no project style (it may be a user or plugin style). Built-ins: `Default`,
  `Explanatory`, `Learning`, `Proactive`, `Concise`.

## A Bash deny is not a security boundary

[doc] `permissions § What a Bash rule doesn't match`: a Bash rule matches the command text Claude
writes. `Bash(curl *)` in deny does not stop `/usr/bin/curl …` or `sh -c 'curl …'`; `Bash(git push *)`
does not stop `git -C . push`. Read/Edit denies cover built-in tools and recognised file commands
(`cat`, `sed`, redirections), not `grep -r` nor a script that opens files itself.

For enforcement that does not depend on spelling, the doc points to **sandboxing** (OS-level,
filesystem and network, Bash and its children) and to a `PreToolUse` hook for custom inspection
(`permissions § How permissions interact with sandboxing`). With the sandbox on and
`autoAllowBashIfSandboxed` at its default, a bare `Bash` ask rule no longer prompts for sandboxed
commands; content-scoped ask rules and explicit denies still apply.

[house] A deny list is a guard against the model's usual spelling, reviewed as such; a finding that
reads "secrets protected by `Read(./.env)`" is only true together with the sandbox.

## Not checked by audit.py

User, managed and `--settings` files; a broad deny shadowing a narrower allow, and conflicts across
files; path rules on `Write`/`Glob`; unusable gitignore patterns; `!` ordering and cross-source
carve-outs; `Bash(command:…)` parameter rules; wildcards before the subcommand; a tracked
`settings.local.json`; allow rules a `-p` pipeline depends on. Confirm what loaded with `/status`
(setting sources), `/permissions` (each rule and its file) and `claude doctor` (what was dropped).
