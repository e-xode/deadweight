<!-- The worked example in this file is one fictional project: an online shop with a
     root `GEMINI.md`, a nested `api/GEMINI.md`, a project `.gemini/settings.json`,
     and a namespaced custom command `.gemini/commands/shop/release.toml`. It is
     invented, and deliberately not `foo`/`bar`: a placeholder with no domain teaches
     nothing about discovery order or namespacing. Where only the structure matters,
     <angle-bracket> placeholders are used instead. -->

# Gemini CLI anatomy

Contents: [Context files and discovery order](#context-files-and-discovery-order) · [`@path` imports](#path-imports) · [Settings files and the `context.*` keys](#settings-files-and-the-context-keys) · [Custom commands](#custom-commands) · [What Gemini CLI reads from a Claude Code configuration](#what-gemini-cli-reads-from-a-claude-code-configuration) · [What audit.py checks, and what it does not](#what-auditpy-checks-and-what-it-does-not)

Verified against the docs on 2026-09-28.

Sources (`https://github.com/google-gemini/gemini-cli/blob/main/docs/<page>.md`):
**cli/gemini-md**, **cli/gemini-ignore**, **cli/custom-commands**, **reference/memport**,
**cli/settings**, **reference/configuration**, **cli/enterprise**, **cli/trusted-folders**.
Every fact below names its page in parentheses. This reference cites only these pages of
the official `google-gemini/gemini-cli` repository — nothing from the issue tracker, a
blog, or a forum.

## Context files and discovery order

Three strata, loaded then concatenated (cli/gemini-md; reference/configuration, "Context
files"):

1. **Global** — `~/.gemini/<configured-name>` (default `GEMINI.md`): *"Location:
   ~/.gemini/GEMINI.md (in your user home directory). Scope: Provides default
   instructions for all your projects."* (cli/gemini-md)
2. **Project root and ancestors** — walked up from the current directory: *"The CLI
   searches for the configured context file in the current working directory and then
   in each parent directory up to either the project root (identified by a `.git`
   folder) or your home directory."* (reference/configuration). In the shop example,
   `api/GEMINI.md` and the root `GEMINI.md` are both on this path.
3. **Subdirectories, just-in-time** — when a tool touches a file or directory: *"the
   CLI automatically scans for GEMINI.md files in that directory and its ancestors up
   to a trusted root."* (cli/gemini-md). This sub-directory scan is capped: *"The
   breadth of this search is limited to 200 directories by default, but can be
   configured with the `context.discoveryMaxDirs` setting."* (reference/configuration)

Everything found is merged: *"It loads various context files from several locations,
concatenates the contents of all found files, and sends them to the model with every
prompt."* (cli/gemini-md)

**Upward-traversal boundary** — `context.memoryBoundaryMarkers`, default `[".git"]`:
*"File or directory names that mark the boundary for GEMINI.md discovery. The upward
traversal stops at the first directory containing any of these markers. An empty array
disables parent traversal."* (reference/configuration). No total-file-count limit is
documented for strata 1 and 2; only stratum 3 has a documented cap
(`discoveryMaxDirs`, default 200).

## `@path` imports

Documented in cli/gemini-md ("Modularize context with imports") and in detail in
reference/memport.

- **Syntax**: `@path` inside a Markdown context file. Relative (`@./file.md`,
  `@../file.md`, `@./sub/file.md`) and absolute (`@/absolute/path/to/file.md`) forms
  are both supported (reference/memport).
- **Relative to what**: the directory of the file that contains the import, not the
  cwd and not the project root — the documented resolver takes a `basePath` described
  as *"the directory path where the current file is located."* (reference/memport)
- **Maximum depth**: *"To prevent infinite recursion, there's a configurable maximum
  import depth (default: 5 levels)."* (reference/memport)
- **Circular imports**: *"The processor automatically detects and prevents circular
  imports."* (reference/memport)
- **Missing file**: *"If a referenced file doesn't exist, the import will fail
  gracefully with an error comment in the output."* (reference/memport) — nothing
  stops: loading continues, and an error comment is inserted where the imported
  content would have gone.
- **Scope**: *"The `validateImportPath` function ensures that imports are only
  allowed from specified directories, preventing access to sensitive files outside
  the allowed scope."* (reference/memport)
- Imports are ignored inside Markdown code blocks and inline code (reference/memport).

## Settings files and the `context.*` keys

**Files and precedence** (reference/configuration, "Settings files"): *"Configuration
is applied in the following order of precedence (lower numbers are overridden by
higher numbers): 1. Default values... 7. Command-line arguments."* The seven levels:
default values, the system-defaults file, the user settings file
(`~/.gemini/settings.json`), the project settings file (`.gemini/settings.json` — the
shop example's file), the system settings file (which *"override[s] all other
settings files"*), environment variables, then command-line arguments.
User/project/system precedence is confirmed again in cli/settings ("Workspace
settings override user settings.") and in cli/enterprise, whose four-level example
gives the system settings file *"the final say."*

**`context.*` keys** (reference/configuration, "context"):

- `context.fileName` (`string | string[]`, default `undefined`) — *"The name of the
  context file or files to load into memory. Accepts either a single string or an
  array of strings."* This **replaces** the searched name list, it does not add to
  it: the docs' own example for reading extra names lists all of them explicitly,
  `{ "context": { "fileName": ["AGENTS.md", "CONTEXT.md", "GEMINI.md"] } }`
  (cli/gemini-md). A shop `settings.json` that sets `context.fileName: ["AGENTS.md"]`
  without re-listing `"GEMINI.md"` stops loading the shop's own `GEMINI.md` files.
- `context.includeDirectories` (`array`, default `[]`) — *"Additional directories to
  include in the workspace context. Missing directories will be skipped with a
  warning."* (reference/configuration)
- `context.loadMemoryFromIncludeDirectories` — the reference table names this key,
  described as: *"Controls how /memory reload loads GEMINI.md files. When true,
  include directories are scanned; when false, only the current directory is used."*
  **The same page's own settings.json example writes it differently**: further down
  reference/configuration, the sample file spells the key `"loadFromIncludeDirectories":
  true` (no "Memory"). Both spellings come from the same page. This is an
  inconsistency inside the official docs themselves, reported here as such: neither
  spelling is preferred over the other in this reference. The docs do not state what
  happens to a misspelled key, but the same page requires: *"All settings should be
  placed within their corresponding top-level category object in your `settings.json`
  file."* — a key outside its category object, or misnamed, falls outside the
  documented schema with no documented error.

## Custom commands

Documented in cli/custom-commands. In the shop example,
`.gemini/commands/shop/release.toml` defines `/shop:release`.

- **Locations and precedence**: *"User commands (global): Located in
  `~/.gemini/commands/`... Project commands (local): Located in
  `<your-project-root>/.gemini/commands/`... If a command in the project directory has
  the same name as a command in the user directory, the project command will always
  be used."* (cli/custom-commands)
- **Format**: a `.toml` file.
  - **Required**: `prompt` (string) — *"The prompt that will be sent to the Gemini
    model when the command is executed."* (cli/custom-commands)
  - **Optional**: `description` — *"If you omit this field, a generic description
    will be generated from the filename."* (cli/custom-commands)
- **Namespacing**: *"The name of a command is determined by its file path relative to
  its commands directory. Subdirectories are used to create namespaced commands, with
  the path separator (`/` or `\`) being converted to a colon (`:`)."*
  (cli/custom-commands) — `.gemini/commands/shop/release.toml` becomes
  `/shop:release`.
- Command files are not reloaded automatically: `/commands reload`, or a CLI restart,
  is required (cli/custom-commands).
- The docs do not state what happens to a malformed TOML file or a command file
  missing `prompt`; only the omission of `description` has a documented fallback.

## What Gemini CLI reads from a Claude Code configuration

Nothing, by default. The docs state it without ambiguity: *"While `GEMINI.md` is the
default filename, you can configure this in your `settings.json` file. To specify a
different name or a list of names, use the `context.fileName` property."*
(cli/gemini-md). The docs' own example of reading more than `GEMINI.md` lists
`AGENTS.md` explicitly:

```json
{ "context": { "fileName": ["AGENTS.md", "CONTEXT.md", "GEMINI.md"] } }
```

`CLAUDE.md` is not named in any example in these pages. **Consequence**: a shop
repository whose root carries a `CLAUDE.md` alongside `GEMINI.md` has that
`CLAUDE.md` invisible to Gemini CLI unless a `settings.json` sets `context.fileName`
to include it — and because `context.fileName` replaces rather than adds (see above),
that same setting must re-list `GEMINI.md` too, or the shop's existing `GEMINI.md`
files stop being read the moment `CLAUDE.md` is added to the list.

## What audit.py checks, and what it does not

**No check is implemented for Gemini CLI in this release.** This reference is
doctrine only: it documents how Gemini CLI's context and configuration mechanisms
work, for the person or agent reading it, but `audit.py` runs no Gemini CLI check
today.

Candidate defects for a later release, once measured against real configurations,
with ids planned under the `57-gemini-` prefix:

| Planned id | Candidate defect | Basis |
| --- | --- | --- |
| `57-gemini-filename-excludes-gemini-md` | `context.fileName` set without `"GEMINI.md"`, while `GEMINI.md` files exist in the tree | `context.fileName` replaces the searched list (reference/configuration; cli/gemini-md) |
| `57-gemini-command-no-prompt` | a `.gemini/commands/*.toml` file missing `prompt` | `prompt` is the only required field (cli/custom-commands) |
| `57-gemini-import-missing` | an `@path` import pointing at a file that does not exist | fails gracefully with an inserted error comment, not a load failure (reference/memport) |
| `57-gemini-key-uncategorized` | a `context.*` (or other) key written at the top level of `settings.json` instead of inside its category object | *"All settings should be placed within their corresponding top-level category object"* (reference/configuration) |

**Not checked, because no check exists**: everything else in this document — the
`context.loadMemoryFromIncludeDirectories` / `loadFromIncludeDirectories` spelling
inconsistency, `discoveryMaxDirs`, `memoryBoundaryMarkers`, import depth and
circularity, command namespacing collisions, and settings precedence across the
user/project/system files.
