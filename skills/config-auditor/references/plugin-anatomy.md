<!-- The worked examples in this file describe one fictional project: an online shop
     whose tooling team publishes a plugin `shop-kit` (skills `shop-release` and
     `shop-review`, an agent `order-auditor`, a bundled MCP server `search`) through
     a marketplace `shop-tools`, plus a bundle plugin `shop-standard` and a shared
     dependency `shop-secrets`. It is invented, and deliberately not `foo`/`bar`: a
     placeholder with no domain teaches nothing about naming or scope. Where only the
     structure matters, <angle-bracket> placeholders are used instead. -->

# Plugin anatomy

Contents: [Layout](#layout) · [Manifest](#manifest) · [Path fields: replace or add](#path-fields-replace-or-add) · [Path variables](#path-variables) · [Plugin agents](#plugin-agents) · [userConfig and sensitive values](#userconfig-and-sensitive-values) · [Version and updates](#version-and-updates) · [Marketplace](#marketplace) · [Dependencies](#dependencies) · [Output styles](#output-styles) · [Commands vs skills](#commands-vs-skills) · [What `claude plugin validate` already checks](#what-claude-plugin-validate-already-checks) · [What audit.py adds](#what-auditpy-adds)

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Sources, read raw (`curl -sL https://code.claude.com/docs/en/<page>.md`): **plugins**,
**plugins-reference**, **plugin-marketplaces**, **plugin-dependencies**, **output-styles**,
**skills** (Command files; name resolution), **mcp** (plugin-provided servers). Every fact names
its page in parentheses. Lines marked **House** are this plugin's convention or measurement.

The angle of this page: a plugin that is wrong usually *loads*. It loads without a component,
without an agent's hooks, at an old version. Each section says what disappears silently and
where it shows.

## Layout

```
shop-kit/
├── .claude-plugin/
│   ├── plugin.json          # manifest, optional
│   └── marketplace.json     # only when this repository is also the marketplace
├── skills/<name>/SKILL.md
├── commands/*.md            # legacy flat skills
├── agents/*.md              # subfolders become part of the name
├── hooks/hooks.json
├── output-styles/*.md
├── .mcp.json   .lsp.json   settings.json   bin/
```

(plugins-reference, Standard plugin layout; plugins, Plugin structure overview)

- **`.claude-plugin/` holds the manifests and nothing else.** `skills/`, `agents/`, `hooks/`, `commands/` placed inside it are not loaded; the plugin loads without them (plugins, Warning "Common mistake"; plugins-reference, Directory structure mistakes). → `44-plugin-layout` ERROR.
- The manifest is optional: without it, components are auto-discovered and the name comes from the directory (plugins-reference, Plugin manifest schema).
- A `CLAUDE.md` at the plugin root **is not loaded** as context; ship instructions as a skill (plugins-reference, Standard plugin layout). `claude plugin validate` warns on it (plugin-marketplaces, Read the validation results).
- Plugin `settings.json` honours only `agent` and `subagentStatusLine`; other keys are silently ignored (plugins, Ship default settings).
- A single-skill plugin may put `SKILL.md` at its root (no `skills/`, no `skills` field). Set frontmatter `name`: otherwise the skill is named after the install directory, which for a cached plugin is **a version string that changes on every update** (plugins-reference, Skills).
- Skills sitting where no loader looks (a `skills/` in a project instead of `.claude/skills/`, or the reverse) → `40-skill-not-loaded`.

## Manifest

`name` is the only required field: kebab-case, no spaces, no control or bidi characters (plugins-reference, Required fields). It namespaces everything: skill `shop-release` is invoked `/shop-kit:shop-release`, agent `order-auditor` is `shop-kit:order-auditor`. If a marketplace entry lists the plugin under another name, **the entry name** is what `enabledPlugins` and `/plugin` use.

- Unrecognised top-level fields are ignored; `validate` warns, `--strict` fails (plugins-reference, Unrecognized fields).
- A recognised field with the wrong type **fails the whole plugin** (e.g. `keywords` as a string); `experimental` and `metadata` are the exceptions (ignored, warned).
- `displayName` is cosmetic; renaming `name` breaks every install unless the marketplace carries a `renames` entry (plugin-marketplaces, Rename or remove a plugin).
- `defaultEnabled: false` installs disabled; once a user has an `enabledPlugins` entry, a later change of default does not flip it; a marketplace entry's value wins over `plugin.json` (plugins-reference, Default enablement).

## Path fields: replace or add

(plugins-reference, Path behavior rules — the table to check before any audit claim)

| Field | Effect on the default directory |
| --- | --- |
| `skills` | **adds** — `skills/` is always scanned too (exception: a marketplace entry whose `source` is the marketplace root) |
| `commands`, `agents`, `workflows`, `outputStyles`, `experimental.themes`, `experimental.monitors` | **replaces** — the default directory is no longer scanned |
| `hooks`, `mcpServers`, `lspServers` | own merge rules (see each section) |

- Replacing fields: files left in the default folder and not listed **do not load**. Claude Code warns in `claude plugin list` and `/plugin`, not at session start. To keep the default, list it: `"agents": ["./agents/", "./extra-agents/"]`. → `44-plugin-path` WARN (**House:** the check covers `agents` and `commands` only).
- Every path is relative and starts with `./` (`skills` also accepts `"."`, 2.1.221+) → `44-plugin-path` ERROR.
- A path resolving outside the plugin root (`../shared`, or a symlink out of the marketplace) is rejected with `path escapes plugin directory`; **the plugin loads without that component** (plugins-reference, Path traversal limitations) → `44-plugin-path` ERROR. On macOS/Linux a backslash anywhere in a path rejects it too.
- Files above the plugin root are not copied into the cache, so a script reading `../` finds nothing after install (same section).

## Path variables

(plugins-reference, Environment variables)

| Variable | Resolves to |
| --- | --- |
| `${CLAUDE_PLUGIN_ROOT}` | the install directory — **changes on each update** for a cached plugin; never write state there |
| `${CLAUDE_PLUGIN_DATA}` | `~/.claude/plugins/data/<id>/`, survives updates, deleted on last uninstall |
| `${CLAUDE_PROJECT_DIR}` | the project root |

- Substituted inline in skill and agent content, hook and monitor commands, MCP (`command`/`args`/`env`; `url`/`headers`/`headersHelper`) and LSP fields.
- Exported to hook, MCP and LSP processes — **not** to commands Claude runs through Bash. A skill telling Claude to run `$CLAUDE_PLUGIN_ROOT/scripts/x.sh` in Bash relies on inline substitution of the `${…}` form in the skill text.
- In shell-form hooks, **quote** the variable: `"\"${CLAUDE_PLUGIN_ROOT}\"/scripts/check.sh"` — an install path with a space otherwise splits. Exec form with `args` needs no quoting. **House:** `35-hooks-command` checks that the script a hook runs exists and is executable, not the quoting — read that by hand.
- After a mid-session update, hooks/MCP/LSP keep the old path until `/reload-plugins`; monitors until restart.

## Plugin agents

(plugins-reference, Plugin agent frontmatter)

- **Ignored on a plugin agent, for security:** `hooks`, `mcpServers`, `permissionMode`. Not supported: `initialPrompt`. No warning at load. → `23-agent-frontmatter-keys` WARN on the first three. To use them, the agent must be copied into `.claude/agents/`.
- Supported: `name`, `description`, `model`, `effort`, `maxTurns`, `tools`, `disallowedTools`, `skills`, `memory`, `background`, `omitClaudeMd`, `isolation` (only `"worktree"`), `color`, `experimental`.
- Unlike project agents, a plugin agent with no `name` **or unparsable frontmatter still loads**: named after the file, description `Agent from <plugin> plugin`, every field ignored. `claude plugin validate` finds the parse error.
- Subfolders join the name: `agents/review/security.md` → `shop-kit:review:security`; listing it in the manifest `agents` field drops the subfolder.
- Tools of the plugin's own MCP server are `mcp__plugin_shop-kit_search__<tool>` in an agent's `tools` and in hook matchers; the bare key never matches (mcp, Plugin-provided MCP servers). See `mcp-anatomy.md`.

## userConfig and sensitive values

(plugins-reference, User configuration)

- Prompted at enable time; `type`, `title`, `description` required. `sensitive: true` masks input and stores in the keychain (≈2 KB shared) or `~/.claude/.credentials.json`.
- Substitution: `${user_config.KEY}` in MCP/LSP configs and hook commands; **non-sensitive only** in skill and agent content. Every value is exported to hook processes as `CLAUDE_PLUGIN_OPTION_<KEY>` (key uppercased).
- **Shell-parsed fields reject `${user_config.*}`** (since 2.1.207): shell-form hook commands, monitor commands, MCP `headersHelper`. The component fails with an error. Use exec-form hooks with `args`, or read `CLAUDE_PLUGIN_OPTION_<KEY>` from the environment; for `headersHelper`, read a file or put the value in `headers`.
- Values are read only from user settings, `--settings` and managed settings; `pluginConfigs` in a project's `.claude/settings*.json` is **ignored** (a clone could otherwise inject values).
- `options` on a field requires 2.1.271+: older clients cannot load the plugin at all.

## Version and updates

(plugins-reference, Version management; plugin-marketplaces, Version resolution)

Resolution order (all sources except `command`): `plugin.json` `version` → marketplace-entry `version` → git commit SHA → archive digest → `unknown`.

- **`plugin.json` wins over the marketplace entry, without warning.** A stale manifest version masks the one in `marketplace.json` → `44-plugin-version` WARN. **Note:** `claude plugin validate` on the marketplace directory already warns on this mismatch for local-path entries; the audit check is for repositories whose CI does not run it.
- **An explicit `version` pins the plugin: users receive an update only when the string changes.** Pushed commits without a bump do nothing; `/plugin update` says "already at the latest version". Exceptions: `command` sources (version includes a content hash) and plugins loaded in place from a local-directory marketplace (always current).
- No `version` anywhere → every commit is an update (commit-SHA versioning). Choose one; do not half-set it.
- **House:** bump `version` in the same change as any shipped file, and keep `plugin.json` the single place it is written.

## Marketplace

(plugin-marketplaces, Marketplace schema, Plugin entries, Relative paths, Strict mode)

```json
{
  "name": "shop-tools",
  "owner": { "name": "<maintainer or team>" },
  "plugins": [ { "name": "shop-kit", "source": "./plugins/shop-kit" } ]
}
```

- Required: `name` (kebab-case), `owner.name`, `plugins[]` with `name` and `source`.
- **Reserved names** are refused, and re-checked at every load: the official Anthropic set (e.g. `claude-plugins-official`, `anthropic-plugins`, `agent-skills`, …), look-alikes such as `official-claude-plugins`, and since 2.1.275 `npm`, `pip`, `uv`, `cargo`, `github`, `gh`. Claude Desktop also rejects `org`, `org-provisioned`, `unknown`.
- One marketplace per name per user: adding a second with the same name **replaces** the first.
- Relative `source` must start with `./` (or be a bare name under `metadata.pluginRoot`, 2.1.239+) and resolves against the **marketplace root**, not `.claude-plugin/`. No `..` segments.
- Relative sources **fail in a marketplace added by URL** to `marketplace.json`: only that file is downloaded.
- `strict` (default `true`): `plugin.json` is authoritative, the entry may add components. `strict: false`: the entry is the whole definition; a `plugin.json` that also declares components is a conflict and **the plugin fails to load**.
- Display fields set on the entry override `plugin.json` in listings.

## Dependencies

(plugin-dependencies)

```json
"dependencies": [ "shop-secrets", { "name": "shop-search", "version": "~2.1.0" } ]
```

- A bare string tracks whatever the marketplace serves; an object takes a semver range (`~2.1.0`, `^2.0`, `>=1.4`). Pre-releases need an opt-in range (`^2.0.0-0`).
- Ranges resolve against git tags named **`<plugin>--v<version>`** (`claude plugin tag --push`). No matching tag → `no-matching-tag`; for relative-path plugins the current copy is installed and checked at load.
- Cross-marketplace dependencies are blocked unless the **root** marketplace lists the target in `allowCrossMarketplaceDependenciesOn`; trust does not chain.
- Errors (`dependency-unsatisfied`, `range-conflict`, `dependency-version-unsatisfied`, `no-matching-tag`) **disable the dependent plugin**; visible in `claude plugin list --json` (`errors` field) and the `/plugin` Errors tab, not in the session.
- A manifest of only `name` + `dependencies` is a documented bundle (`shop-standard`).

## Output styles

(output-styles, Frontmatter reference)

- Plugins ship styles in `output-styles/` (or the replacing `outputStyles` field).
- `force-for-plugin: true` applies the style whenever the plugin is enabled and **overrides the user's `outputStyle`**; with several such plugins, the first loaded wins. **House:** a public plugin should not set it — it takes a user-level decision away from every consumer.
- A custom style drops Claude Code's software-engineering instructions unless `keep-coding-instructions: true`. Misspelled fields are ignored; unparsable YAML loads the style with no fields.

## Commands vs skills

(skills, Where skills live, Resolve skills that share a name)

- `commands/*.md` (plugin) and `.claude/commands/*.md` (project) are the older format and still load. They take the skill frontmatter **except `name` and `paths`**, which are ignored. → `45-command-shadowed` WARN.
- A skill and a command file with the same name: **the skill wins; the command never runs** → `45-command-shadowed` WARN.
- Plugin skills are namespaced, so they never collide with a project skill; both load.

## What `claude plugin validate` already checks

Do not reimplement it; run it (`--strict` in CI, `--json` for tooling, exit 0/1/2) (plugins-reference, plugin validate; plugin-marketplaces, Marketplace validation errors, Validate a plugin…):

- `plugin.json` syntax and schema, wrong-typed fields, unrecognised fields (warnings);
- `hooks/hooks.json` JSON syntax; YAML frontmatter of files in the **default** `skills/`, `agents/`, `commands/`;
- that each manifest component path **exists** — but not the files behind it;
- marketplace: schema, duplicate plugin names, `..` in sources, control/bidi characters, non-kebab names, Desktop-reserved names, entry-vs-manifest version mismatch for local sources, `renames` cycles;
- a root `CLAUDE.md` (warning).

Blind spots it documents itself: a root `SKILL.md` of a plugin not sitting in a `skills/` directory; files behind symlinks; files under custom paths.

## What audit.py adds

| Check | Fires on |
| --- | --- |
| `44-plugin-layout` | component directories inside `.claude-plugin/` |
| `44-plugin-path` | path without `./`; path escaping the root; files in `agents/` or `commands/` not loaded because the field replaces the folder |
| `44-plugin-version` | `version` differing between `plugin.json` and `marketplace.json` |
| `23-agent-frontmatter-keys` | `hooks`, `mcpServers`, `permissionMode` on a plugin agent |
| `45-command-shadowed` | command/skill name clash; `name`/`paths` in a command file |
| `40-skill-not-loaded` | skills outside any loaded location |
| `35-hooks-*` | `hooks/hooks.json`: parse, shape, event, matcher, `if`, timeout, command |
| `36-foreign-skill` | routing text naming a skill the plugin does not ship — absent in a consumer's project |
| `30-plugin-cost` | always-loaded characters every consumer pays per turn |

**`30-plugin-cost`, why it matters more for a plugin.** Every enabled plugin's skill and agent descriptions enter each consumer's listing, plus the `<plugin>:` prefix. **House, measured 2026-09-22:** `skillOverrides` does not reach a plugin skill, so a consumer can only disable the whole plugin — the cost is not negotiable downstream (the skills page documents `skillOverrides` for personal, project and bundled skills and says nothing of plugin skills).
