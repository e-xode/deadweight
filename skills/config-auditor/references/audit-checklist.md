<!-- The worked examples in these references (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example. -->

# Audit checklist

Contents: [How to run](#how-to-run) · [`CLAUDE.md`](#claudemd) · [Skills](#skills) · [References](#references) · [Evals](#evals) · [Agents](#agents) · [Rules](#rules) · [Hooks](#hooks) · [Settings and permissions](#settings-and-permissions) · [MCP](#mcp) · [Plugins](#plugins) · [Cross-cutting](#cross-cutting) · [Required exit](#required-exit)

Verified against the docs on 2026-09-23 (Claude Code 2.1.280). Each item is tagged `[AUTO]` with
the check id that covers it, or `[MANUAL]` — the qualitative half no script sees. Severity follows
one rule: **ERROR** when the harness rejects or silently ignores the thing, **WARN** for a probable
defect or a house convention the project opted into, **NOTICE** for what names a file without being a
defect (a house convention by default, what cannot be verified from the repository), **INFO** for a
measurement every run emits. Counters and the floor leave INFO out; a report never does.

## How to run

```bash
claude plugin validate --strict .        # upstream: manifests, SKILL.md frontmatter
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py
```

Then, in a fresh session, confirm what the harness actually loaded — `audit.py` reads files on disk:

- `[MANUAL]` `/context` and `/doctor` — the real cost of the listing and its biggest contributors.
- `[MANUAL]` `/skills`, `/skill-doctor` — per-skill cost and invocation counts.

## `CLAUDE.md`

- `[AUTO 01-claude-md-exists]` Present at `./CLAUDE.md` or `./.claude/CLAUDE.md`; an `AGENTS.md` alone is INFO.
- `[AUTO 01-claude-md-lines]` ≤ 200 lines — the documented target, for each of `./CLAUDE.md`, `./.claude/CLAUDE.md` and `./CLAUDE.local.md`.
- `[AUTO 01-claude-md-size]` ≤ 12 KB per memory file — house proxy, movable per project through the overlay.
- `[AUTO 01-claude-md-import]` Every `@path` import resolves, relative to the importing file.
- `[AUTO 01-agents-md-unread]` An `AGENTS.md` beside a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` is imported or it is not read; the path resolves from the importing file (`@../AGENTS.md` from `.claude/CLAUDE.md`), imports are followed four hops, and an `@` in code is not an import.
- `[AUTO 54-agents-md-variant]` No `AGENTS.override.md` / `AGENTS.local.md` relied on for Claude Code: Claude Code reads neither, Codex reads `AGENTS.override.md`, and no agent documents reading `AGENTS.local.md`. Silent when a `CLAUDE.md` imports the file. See [agents-md-anatomy.md](./agents-md-anatomy.md).
- `[AUTO 01-claude-local]` `CLAUDE.local.md` is ignored by the repository's git rules.
- `[AUTO 12-no-code-comments]` No `//` or `/* */` outside code blocks (fenced or indented).
- `[MANUAL]` Every line passes the deletion test: "would removing this cause Claude to make mistakes?"
- `[MANUAL]` One `IMPORTANT` at most; nothing Claude already does without being told.
- `[MANUAL]` No section duplicates a skill; nothing contradicts a rule.

## Skills

- `[AUTO 02-skill-frontmatter]` Frontmatter parses; `name` and `description` present.
- `[AUTO 02-skill-unknown-field]` No field outside the twenty documented ones — an unknown field is ignored without an error.
- `[AUTO 02-skill-md-exists]` Every skill folder has a `SKILL.md`; no folder named `synced`, and no folder or `name` `anthropic-skills` / `anthropic-skills:*`, outside a plugin (reserved: ERROR); no `SKILL.md` in a category folder `.claude/skills/<category>/<skill>/` in a project (not loaded: WARN).
- `[AUTO 03-skill-name-matches-folder]` `name` equals the folder name.
- `[AUTO 04-skill-description-length]` Description 80–1,024 chars; description + `when_to_use` ≤ 1,536 (listing cutoff).
- `[AUTO 04-skill-description-antitrigger]` An anti-trigger clause — house convention.
- `[AUTO 04-skill-description-brackets]` No `<` or `>` (claude.ai upload and `quick_validate` reject them).
- `[AUTO 05-skill-md-size]` / `[AUTO 21-skill-md-compaction]` ≤ 50 KB hard, ≤ ~20 KB effective (compaction re-attach).
- `[AUTO 06-skill-duplicate-name]` Unique `name`.
- `[AUTO 15-skill-index]` A skill the model cannot reach by itself (`disable-model-invocation`, `skillOverrides` off) is named in the Skills index — house convention. A `paths:` skill surfaces on a matching read and is not required. A listed skill named in the index is a house NOTICE as well.
- `[AUTO 19-frontmatter-quoting]` Scalars containing `': '` are quoted (a ` #` comment is cut first); a plain value that opens and closes `[...]` or `{...}` and goes on is quoted.
- `[AUTO 28-skill-anchors]` Every repository path a skill names under the folders the check reads (`src/`, `server/`, `scripts/`, `electron/`, `docker/`, `app/`, `lib/`, `packages/`, `test/`, `tests/`) exists — paths elsewhere (`docs/`, `config/`...) are not checked; paths git ignores or outside the repository are listed as unverifiable, not counted.
- `[AUTO 32-skill-name-shape]` / `[AUTO 32-skill-name-reserved]` Lowercase, digits, single hyphens, ≤ 64; no `anthropic` / `claude`. Shape is a WARN (the spec rejects it on upload or packaging); a plugin's own `<name>:` prefix is accepted.
- `[AUTO 33-description-overlap]` Close descriptions exclude each other, `description` + `when_to_use` read together; a one-way exclusion names the missing side (WARN), a pair neither side separates is a NOTICE. An exclusion counts in its own clause: its sentence (past "e.g." and "i.e."), and a bulleted list under it. Known limit: an exclusion written in the NEXT sentence ("Do not use for refunds. Those go to `shop-refunds`.") is not seen.
- `[AUTO 40-skill-not-loaded]` No `SKILL.md` outside a location Claude Code loads.
- `[AUTO 48-agents-dir-skills]` No skill kept only in `.agents/skills/`: Claude Code does not load it. Link it into `.claude/skills/` to share it between tools.
- `[AUTO 55-cursor-*]` Cursor rules are `.mdc` (a `.md` in `.cursor/rules/` is ignored), each has `alwaysApply`, `globs` or a `description`, and every `globs` matches a file; no legacy `.cursorrules`. See [cursor-anatomy.md](./cursor-anatomy.md).
- `[AUTO 56-copilot-*]` Copilot instruction files end `.instructions.md`, each has `applyTo` or `description`, every `applyTo` matches a file; no chat mode left in `.github/chatmodes/`. See [copilot-anatomy.md](./copilot-anatomy.md).
- `[AUTO 55-cursor-reads-claude-md, 56-copilot-reads-claude-md]` Where Cursor or Copilot also works on the repository, `CLAUDE.md` does not give them Claude Code-only instructions (`/compact`, the `Task` tool, `.claude/agents/`): Cursor applies `CLAUDE.md` to every conversation, Copilot's agent reads it.
- `[MANUAL]` `CLAUDE.md` and the other agents' files (`AGENTS.md`, `copilot-instructions.md`) do not contradict each other. Gemini CLI: doctrine only, [gemini-anatomy.md](./gemini-anatomy.md).
- `[AUTO 49-plugin-var-in-project]` No `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` used in a project skill: substituted only in plugin skills.
- `[AUTO 50-security-*]` Security family, own grade (high ERROR, medium WARN, low NOTICE): no allow rule granting arbitrary code execution, no unpinned stdio MCP server, no download-and-run command, no hidden bidi/tag character, no literal secret in settings `env`, no plain-http remote MCP server, no `additionalDirectories` wider than the project, no `claude -p` isolated by allow/deny lists alone.
- `[AUTO 51-stale-command]` / `[AUTO 28-config-anchors]` / `[AUTO 52-claude-md-tree]` / `[AUTO 53-no-verification-command]` Instructions match the repository: named commands are defined, named paths exist, no file tree in CLAUDE.md, a verification command is named where the repository has one.
- `[MANUAL]` Twin skills name each other with a crossed anti-trigger in their descriptions (antipattern B6). A "Division of responsibilities" table is optional, kept once and pointed to, never copied into each twin.
- `[MANUAL]` Description says what and when, in the third person, without shouted imperatives.
- `[MANUAL]` `SKILL.md` is method + index; `allowed-tools` of a committed skill reviewed (not gated by workspace trust).
- `[MANUAL]` A `` !`cmd` `` injection cannot fail the whole invocation (`|| true` where exit 1 is normal).

## References

- `[AUTO 16-reference-size]` > 100 lines open with a `Contents:` block; > 300 lines split — house convention (the docs ask only for a table of contents).
- `[AUTO 25-orphan-reference]` Every reference (`references/`, `reference/`, or a `.md` at the skill's root) is linked from its own `SKILL.md` — one level deep.
- `[AUTO 07-skill-broken-link]` / `[AUTO 20-relative-links]` Relative links resolve.
- `[MANUAL]` One topic per file; no critical rule lives only in a reference.
- `[AUTO 46-doctrine-copy]` A project reference named like one of this plugin's `*-anatomy.md` files or skill-runtime-mechanisms.md,
  or sharing most of its code terms with them (15 terms at least), restates the doctrine instead of recording the project's decisions.
  Known limit: a copy named `semantic-layer.md` or `runtime-data.md` is not matched by its name, since both are common names in data
  repositories; under 15 code terms it goes unseen.
  Keep the decisions and their reasons; point to this skill for how the harness works.

## Evals

- `[AUTO 26-evals-*]` Suite parses, ≥ 3 cases, ids consistent; coverage per skill. A missing `expected_output` is a NOTICE. At least one anti-trigger case (`should_trigger: false`, in any JSON of the skill's `evals/`) — house convention.
- `[AUTO 39-eval-*]` A suite can fail: a fact is graded by `tool_used`, not by a judge; not every grader is a judge (graders listed in `case.yaml` count); cases that measure files have a fixture (`scaffold_script` or `context.add_dirs`).
- `[MANUAL]` The anti-trigger case is a genuine near miss; a case passes WITH the skill and fails without it.

## Agents

- `[AUTO 08-agent-frontmatter]` Frontmatter parses as YAML (ERROR: the agent does not load); `---` on line 1; `name` and `description` present; no `:` in `name`, no leading `-`, ≤ 256 chars; no duplicate `name`. In a plugin, an empty or unparsable frontmatter is a WARN: the agent loads under its filename.
- `[AUTO 08b-agent-description]` 80–900 chars with an anti-trigger clause — house convention.
- `[AUTO 09-*]` Listed in `## Agents directory` and back — house convention (WARN).
- `[AUTO 23-agent-tools]` Every tool resolves (tools-reference); `Task` is an alias (NOTICE); `Agent(<type>)` in a subagent definition is ignored (WARN), except for the agent the `agent` setting names; a tool removed from sub-agents is a WARN; ERROR only when no entry resolves.
- `[AUTO 23-agent-model]` An alias (`sonnet`, `opus`, `haiku`, `fable`, `best`, `opusplan`, `inherit`; `[1m]` goes on an alias other than `inherit` or on a full name), an id starting with `claude-` (or after `.`, `/`, `:`) or a Bedrock ARN; anything else is a NOTICE (a provider deployment name is free-form).
- `[AUTO 23-agent-permission-mode]` A documented mode; `bypassPermissions` declared by a subagent is not honoured.
- `[AUTO 23-agent-skills-preload]` Preload targets exist (a `plugin:skill` target is INFO).
- `[AUTO 23-agent-frontmatter-keys]` No key outside the eighteen documented; in a plugin, no `hooks` / `mcpServers` / `permissionMode`.
- `[MANUAL]` `tools` is the minimum; `memory` re-enables Read, Write and Edit.
- `[MANUAL]` The delegation carries an objective, an output format, the tools and sources, and boundaries.

## Rules

- `[AUTO 14-rule-no-paths]` A frontmatter block holds a non-empty `paths:`.
- `[AUTO 14-rule-unknown-field]` `paths` is the only field read (`globs:` is ignored).
- `[AUTO 22-rule-glob-match]` Every glob matches a file (`\[` escapes; an unclosed `[` matches nothing); a glob into a directory git ignores is NOTICE, not in the floor.
- `[AUTO 14-rule-size]` / `[AUTO 14-rule-code-comments]` / `[AUTO 14-rule-english-only]` House conventions.
- `[MANUAL]` A rule meant to guard file **creation** does not rely on `paths:` — rules trigger on reads.
- `[MANUAL]` Two rules never contradict each other: Claude may pick one arbitrarily.

## Hooks

- `[AUTO 35-hooks-parse]` / `[AUTO 35-hooks-shape]` Valid JSON; known handler type with its required field.
- `[AUTO 35-hooks-event]` One of the thirty-three events.
- `[AUTO 35-hooks-matcher]` No matcher on a matcherless event; no bare `mcp__<server>` (use `mcp__<server>__.*`).
- `[AUTO 35-hooks-if]` `if` only on tool events, one rule, no `&&` / `||`.
- `[AUTO 35-hooks-timeout]` NOTICE: no explicit timeout where the default is long; the per-event default is named. Not reported on an `async: true` hook.
- `[AUTO 35-hooks-command]` The script exists; a script run directly is executable; no `CLAUDE_PLUGIN_ROOT` in a project hook; no `./` path in a skill's hook (it resolves from the working directory).
- `[AUTO 35-hooks-context]` What a context-injecting event prints is paid every session.
- `[MANUAL]` A blocking policy exits 2, not 1. Hooks inline in `plugin.json` are reviewed by hand — `audit.py` does not read them; skill and agent frontmatter hooks are read.

## Settings and permissions

- `[AUTO 24-settings-parse]` Valid JSON object.
- `[AUTO 24-settings-scope]` No key outside its documented scope, nested keys (`sandbox.*`) included; no opt-out `false` the shared file cannot set.
- `[AUTO 24-settings-default-mode]` No `bypassPermissions` / `auto` default mode in a project file.
- `[AUTO 24-settings-env]` No credential or request-routing variable in the shared file.
- `[AUTO 24-settings-local]` `settings.local.json` ignored by the repository's git rules.
- `[AUTO 24-settings-skill-overrides]` Keys name a project skill, or are NOTICE (bundled, user, synced).
- `[AUTO 24-settings-statusline]` / `[AUTO 24-settings-output-style]` The script exists, `refreshInterval` ≥ 1; the style name matches exactly.
- `[AUTO 42-permissions-conflict]` No rule both allowed and denied or asked.
- `[AUTO 42-permissions-rule]` Allow rules name known tools, no unanchored glob, no `mcp__…(…)`, `:*` only at the end of a `Bash` or `PowerShell` pattern.
- `[AUTO 24-settings-unknown-subkey]` Every field of a closed object (`attribution`, `permissions`…) is documented.
- `[MANUAL]` A rule the prose states and a setting can enforce is in the setting too — commit attribution first: a
  CLAUDE.md that forbids a co-author trailer, with no `attribution` in settings, holds only while the rule is read.
- `[MANUAL]` A Bash deny is not a security boundary; sandboxing is.

## MCP

- `[AUTO 43-mcp-shape]` `.mcp.json` parses; a `url` has a `type`; SSE is deprecated (NOTICE).
- `[AUTO 43-mcp-secret]` No literal credential — reference `${VAR}`.
- `[AUTO 43-mcp-credential-var]` No protected credential variable in a remote `url` or header (read as empty): the five the docs name, and eight more measured on Claude Code 2.1.294.
- `[AUTO 43-mcp-approval]` No server approval committed in the shared settings file.

## Plugins

- `[AUTO 44-plugin-layout]` No component directory inside `.claude-plugin/`.
- `[AUTO 44-plugin-path]` Component paths start with `./` and stay inside the plugin; a field that replaces a default directory (`agents`, `commands`, `outputStyles`, `workflows`, `experimental.themes`, `experimental.monitors`) lists every file in it.
- `[AUTO 44-plugin-version]` `plugin.json` and the marketplace entry agree.
- `[AUTO 30-plugin-cost]` / `[AUTO 36-foreign-skill]` The listing cost consumers cannot trim; no routing to a skill the plugin does not ship.
- `[AUTO 45-command-shadowed]` No command sharing a skill's name; no `name` / `paths` in a command file.

## Cross-cutting

- `[AUTO 17-always-loaded-budget]` / `[AUTO 29-listing-budget-derived]` House ratchet and the harness-derived ceiling.
- `[AUTO 13-no-global-scripts]` Scripts live under the skill that runs them — house convention. A script that a hook, the `statusLine`, the `subagentStatusLine`, the `fileSuggestion` command or a credential helper (`apiKeyHelper`, `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`) of `.claude/settings.json` runs, or that a hook in an agent's or a skill's frontmatter runs, is exempt; a permission rule, an `env` value or a description naming it does not exempt it.
- `[AUTO 18-see-skill-target]` Every `➜ See skill:` target exists (a skill or a `.claude/commands/` name).
- `[MANUAL]` Configuration disabled by renaming (`settings._json`, `*.disabled`, `*.bak` beside a live
  file) loads nothing and misleads a reader: restore it or delete it; git keeps the history.
- `[AUTO 11-english-only]` One declared language — house convention, exemptable. Heuristic on distinct marker words; a `.md` in a skill marked French by its name (.fr.md, `-fr.md`, `_fr.md`) or folder (`fr/`) is left alone; another locale marker (`-it.md`, `-de.md`) is not, since `ship-it.md` is an English name.
- `[AUTO 58/59-semantic-*]` With `scripts/semantic.py`: contradictions and duplicates between files, read by a model, every quote checked; never counted, never in the floor.
- `[AUTO 57-runtime-*]` With `--runtime <InstructionsLoaded log>`: path-scoped rules and nested `CLAUDE.md` never loaded over the recorded sessions, rules loaded unscoped. The log is the maintainer's hook, never the agent's.
- `[AUTO 31-overlay-*]` / `[AUTO 34-*]` Exemptions carry a reason and a date, and still excuse something (`31-overlay-unused`); the floor compares one instrument only (`34-floor`; `34-audit-sha` is its alias), and names an ERROR or WARN id it did not record.

## Required exit

1. `audit.py` exits `0`. It prints the number of check groups it ran — that line is the inventory.
2. Resolve each new WARN, or exempt it in `.claude/audit.local.json` with its `reason` and `date`.
3. Propose corrections to the user. **Never auto-apply.**
