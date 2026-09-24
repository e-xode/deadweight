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
- `[AUTO 01-claude-md-lines]` ≤ 200 lines — the documented target.
- `[AUTO 01-claude-md-size]` ≤ 12 KB — house proxy, movable per project through the overlay.
- `[AUTO 01-claude-md-import]` Every `@path` import resolves, relative to the importing file.
- `[AUTO 01-agents-md-unread]` An `AGENTS.md` beside a `CLAUDE.md` is imported (`@AGENTS.md`) or it is not read.
- `[AUTO 01-claude-local]` `CLAUDE.local.md` is ignored by the repository's git rules.
- `[AUTO 12-no-code-comments]` No `//` or `/* */` outside fenced code blocks.
- `[MANUAL]` Every line passes the deletion test: "would removing this cause Claude to make mistakes?"
- `[MANUAL]` One `IMPORTANT` at most; nothing Claude already does without being told.
- `[MANUAL]` No section duplicates a skill; nothing contradicts a rule.

## Skills

- `[AUTO 02-skill-frontmatter]` Frontmatter parses; `name` and `description` present.
- `[AUTO 02-skill-unknown-field]` No field outside the twenty documented ones — an unknown field is ignored without an error.
- `[AUTO 02-skill-md-exists]` Every skill folder has a `SKILL.md`; no folder named `synced` (reserved).
- `[AUTO 03-skill-name-matches-folder]` `name` equals the folder name.
- `[AUTO 04-skill-description-length]` Description 80–1,024 chars; description + `when_to_use` ≤ 1,536 (listing cutoff).
- `[AUTO 04-skill-description-antitrigger]` An anti-trigger clause — house convention.
- `[AUTO 04-skill-description-brackets]` No `<` or `>` (claude.ai upload and `quick_validate` reject them).
- `[AUTO 05-skill-md-size]` / `[AUTO 21-skill-md-compaction]` ≤ 50 KB hard, ≤ ~20 KB effective (compaction re-attach).
- `[AUTO 06-skill-duplicate-name]` Unique `name`.
- `[AUTO 15-skill-index]` A skill the model cannot reach by itself (`disable-model-invocation`, `skillOverrides` off) is named in the Skills index — house convention. A `paths:` skill surfaces on a matching read and is not required.
- `[AUTO 19-frontmatter-quoting]` Scalars containing `': '` are quoted.
- `[AUTO 28-skill-anchors]` Every repository path a skill names exists; paths git ignores or outside the repository are listed as unverifiable, not counted.
- `[AUTO 32-skill-name-shape]` / `[AUTO 32-skill-name-reserved]` Lowercase, digits, single hyphens, ≤ 64; no `anthropic` / `claude`.
- `[AUTO 33-description-overlap]` Close descriptions exclude each other; a one-way exclusion names the missing side.
- `[AUTO 40-skill-not-loaded]` No `SKILL.md` outside a location Claude Code loads.
- `[AUTO 27-twin-division-*]` Twin skills carry matching "Division of responsibilities" rows — house convention.
- `[MANUAL]` Description says what and when, in the third person, without shouted imperatives.
- `[MANUAL]` `SKILL.md` is method + index; `allowed-tools` of a committed skill reviewed (not gated by workspace trust).
- `[MANUAL]` A `` !`cmd` `` injection cannot fail the whole invocation (`|| true` where exit 1 is normal).

## References

- `[AUTO 16-reference-size]` > 100 lines open with a `Contents:` block; > 300 lines split — house convention (the docs ask only for a table of contents).
- `[AUTO 25-orphan-reference]` Every reference is linked from its own `SKILL.md` — one level deep.
- `[AUTO 07-skill-broken-link]` / `[AUTO 20-relative-links]` Relative links resolve.
- `[MANUAL]` One topic per file; no critical rule lives only in a reference.
- `[AUTO 46-doctrine-copy]` A project reference named like one of this plugin's, or sharing most of
  its code terms with them, restates the doctrine instead of recording the project's decisions.
  Keep the decisions and their reasons; point to this skill for how the harness works.

## Evals

- `[AUTO 26-evals-*]` Suite parses, ≥ 3 cases, at least one anti-trigger case, ids consistent; coverage per skill.
- `[AUTO 39-eval-*]` A suite can fail: a fact is graded by `tool_used`, not by a judge; not every grader is a judge; cases that measure files have a fixture.
- `[MANUAL]` The anti-trigger case is a genuine near miss; a case passes WITH the skill and fails without it.

## Agents

- `[AUTO 08-agent-frontmatter]` Frontmatter parses; `name` and `description` present; no `:` in `name`; no duplicate `name`.
- `[AUTO 08b-agent-description]` 80–900 chars with an anti-trigger clause — house convention.
- `[AUTO 09-*]` Listed in `## Agents directory` and back — house convention (WARN).
- `[AUTO 23-agent-tools]` Every tool resolves (tools-reference); `Task` is an alias (NOTICE); `Agent(<type>)` in a subagent definition is ignored (WARN); ERROR only when no entry resolves.
- `[AUTO 23-agent-model]` `sonnet`, `opus`, `haiku`, `fable`, `inherit` or a `claude-*` id.
- `[AUTO 23-agent-permission-mode]` A documented mode; `bypassPermissions` declared by a subagent is not honoured.
- `[AUTO 23-agent-skills-preload]` Preload targets exist (a `plugin:skill` target is INFO).
- `[AUTO 23-agent-frontmatter-keys]` No key outside the eighteen documented; in a plugin, no `hooks` / `mcpServers` / `permissionMode`.
- `[MANUAL]` `tools` is the minimum; `memory` re-enables Read, Write and Edit.
- `[MANUAL]` The delegation carries an objective, an output format, the tools and sources, and boundaries.

## Rules

- `[AUTO 14-rule-no-paths]` A frontmatter block holds a non-empty `paths:`.
- `[AUTO 14-rule-unknown-field]` `paths` is the only field read (`globs:` is ignored).
- `[AUTO 22-rule-glob-match]` Every glob matches a file; a glob into a directory git ignores is NOTICE, not in the floor.
- `[AUTO 14-rule-size]` / `[AUTO 14-rule-code-comments]` / `[AUTO 14-rule-english-only]` House conventions.
- `[MANUAL]` A rule meant to guard file **creation** does not rely on `paths:` — rules trigger on reads.
- `[MANUAL]` Two rules never contradict each other: Claude may pick one arbitrarily.

## Hooks

- `[AUTO 35-hooks-parse]` / `[AUTO 35-hooks-shape]` Valid JSON; known handler type with its required field.
- `[AUTO 35-hooks-event]` One of the thirty-three events.
- `[AUTO 35-hooks-matcher]` No matcher on a matcherless event; no bare `mcp__<server>` (use `mcp__<server>__.*`).
- `[AUTO 35-hooks-if]` `if` only on tool events, one rule, no `&&` / `||`.
- `[AUTO 35-hooks-timeout]` An explicit timeout where the default is long; the per-event default is named.
- `[AUTO 35-hooks-command]` The script exists; no `CLAUDE_PLUGIN_ROOT` in a project hook.
- `[AUTO 35-hooks-context]` What a context-injecting event prints is paid every session.
- `[MANUAL]` A blocking policy exits 2, not 1. Hooks in skill or agent frontmatter are reviewed by hand — `audit.py` does not read them yet.

## Settings and permissions

- `[AUTO 24-settings-parse]` Valid JSON object.
- `[AUTO 24-settings-scope]` No key outside its documented scope; no opt-out `false` the shared file cannot set.
- `[AUTO 24-settings-default-mode]` No `bypassPermissions` / `auto` default mode in a project file.
- `[AUTO 24-settings-env]` No credential or request-routing variable in the shared file.
- `[AUTO 24-settings-local]` `settings.local.json` ignored by the repository's git rules.
- `[AUTO 24-settings-skill-overrides]` Keys name a project skill, or are NOTICE (bundled, user, synced).
- `[AUTO 24-settings-statusline]` / `[AUTO 24-settings-output-style]` The script exists, `refreshInterval` ≥ 1; the style name matches exactly.
- `[AUTO 42-permissions-conflict]` No rule both allowed and denied or asked.
- `[AUTO 42-permissions-rule]` Allow rules name known tools, no unanchored glob, no `mcp__…(…)`, `:*` only at the end.
- `[AUTO 24-settings-unknown-subkey]` Every field of a closed object (`attribution`, `permissions`…) is documented.
- `[MANUAL]` A rule the prose states and a setting can enforce is in the setting too — commit attribution first: a
  CLAUDE.md that forbids a co-author trailer, with no `attribution` in settings, holds only while the rule is read.
- `[MANUAL]` A Bash deny is not a security boundary; sandboxing is.

## MCP

- `[AUTO 43-mcp-shape]` `.mcp.json` parses; a `url` has a `type`; SSE is deprecated (NOTICE).
- `[AUTO 43-mcp-secret]` No literal credential — reference `${VAR}`.
- `[AUTO 43-mcp-credential-var]` No protected credential variable in a remote `url` or header (read as empty).
- `[AUTO 43-mcp-approval]` No server approval committed in the shared settings file.

## Plugins

- `[AUTO 44-plugin-layout]` No component directory inside `.claude-plugin/`.
- `[AUTO 44-plugin-path]` Component paths start with `./` and stay inside the plugin; a field that replaces a default directory lists every file in it.
- `[AUTO 44-plugin-version]` `plugin.json` and the marketplace entry agree.
- `[AUTO 30-plugin-cost]` / `[AUTO 36-foreign-skill]` The listing cost consumers cannot trim; no routing to a skill the plugin does not ship.
- `[AUTO 45-command-shadowed]` No command sharing a skill's name; no `name` / `paths` in a command file.

## Cross-cutting

- `[AUTO 17-always-loaded-budget]` / `[AUTO 29-listing-budget-derived]` House ratchet and the harness-derived ceiling.
- `[AUTO 13-no-global-scripts]` Scripts live under the skill that runs them — house convention.
- `[AUTO 18-see-skill-target]` Every `➜ See skill:` target exists.
- `[MANUAL]` Configuration disabled by renaming (`settings._json`, `*.disabled`, `*.bak` beside a live
  file) loads nothing and misleads a reader: restore it or delete it; git keeps the history.
- `[AUTO 11-english-only]` One declared language — house convention, exemptable.
- `[AUTO 31-overlay-*]` / `[AUTO 34-*]` Exemptions carry a reason and a date, and still excuse something (`31-overlay-unused`); the floor compares one instrument only.

## Required exit

1. `audit.py` exits `0`. It prints the number of check groups it ran — that line is the inventory.
2. Resolve each new WARN, or exempt it in `.claude/audit.local.json` with its `reason` and `date`.
3. Propose corrections to the user. **Never auto-apply.**
