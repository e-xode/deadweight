<!-- The worked examples in this file describe one fictional project: an online shop
     repository whose root carries an `AGENTS.md` next to a `CLAUDE.md`, and whose
     `api/` package carries its own nested `api/AGENTS.md`. It is invented, and
     deliberately not `foo`/`bar`: a placeholder with no domain teaches nothing about
     precedence or nesting. Where only the structure matters, <angle-bracket>
     placeholders are used instead. -->

# AGENTS.md anatomy

Contents: [The format](#the-format) · [How each tool reads it](#how-each-tool-reads-it) · [Claude Code in detail](#claude-code-in-detail) · [One file for several tools](#one-file-for-several-tools) · [What audit.py checks, and what it does not](#what-auditpy-checks-and-what-it-does-not)

Verified against the docs on 2026-09-28.

## The format

- **Doc.** (https://agents.md/): "AGENTS.md is just standard Markdown. Use any headings you
  like; the agent simply parses the text you provide." No required structure, no field schema.
- No frontmatter is documented for `AGENTS.md` by any of the seven sources read for this page
  (the agents.md spec itself, Codex, Copilot, Copilot CLI, Cursor, Cursor CLI, Gemini CLI, Claude
  Code): not documented, for every one of them — do not fill this from a general Markdown
  frontmatter convention.
- The spec's own precedence rule, before any single tool adds its own: "Place another AGENTS.md
  inside each package. Agents automatically read the nearest file in the directory tree, so the
  closest one takes precedence" (https://agents.md/) — the `api/AGENTS.md` of the shop repository
  is that inner file.

## How each tool reads it

| Tool | Reads by default? | Nested rule | Size cap | Override file |
| --- | --- | --- | --- | --- |
| OpenAI Codex | Yes | Concatenates root → cwd; the closer file appears later, so it has the last word | `project_doc_max_bytes`, 32 KiB by default | `AGENTS.override.md`, at each level |
| GitHub Copilot (cloud coding agent) | Yes | Nearest file in the directory tree wins | Not documented | Not documented |
| GitHub Copilot CLI | Yes | Root, cwd, intermediate and nested directories are combined; no defined precedence | Not documented | Not documented |
| Cursor (editor) | Yes | Nested files combine with parent directories, most specific wins | Not documented | Not documented |
| Cursor CLI | Yes, root only | No precedence stated between `AGENTS.md` and the `CLAUDE.md` it also reads at the root | Not documented | Not documented |
| Gemini CLI | No, unless configured | Workspace file plus its parents, then just-in-time files as tools touch other directories | Not documented | Not documented |
| Claude Code | Only when no `CLAUDE.md`/`.claude/CLAUDE.md`/`CLAUDE.local.md` is on the path — see below | See below | Not documented specifically for `AGENTS.md` | None: `AGENTS.override.md` is on the documented "Not read" list |

The load-bearing quotes behind the surprising cells:

- **Doc.** (https://learn.chatgpt.com/docs/agent-configuration/agents-md): "Codex concatenates
  files from the root down, joining them with blank lines. Files closer to your current directory
  override earlier guidance because they appear later in the combined prompt." And: "Codex skips
  empty files and stops adding files once the combined size reaches the limit defined by
  `project_doc_max_bytes` (32 KiB by default)." The override file: "Use
  `~/.codex/AGENTS.override.md` when you need a temporary global override without deleting the
  base file."
- **Doc.** (https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot):
  "You can create one or more `AGENTS.md` files, stored anywhere within the repository", and "When
  Copilot is working, the nearest `AGENTS.md` file in the directory tree will take precedence."
- **Doc.** (https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions):
  Copilot CLI reads "the repository root, the current working directory, intermediate directories
  between them, and any directories nested in the path of a file it is working on", and "combines"
  them but "does not define a general precedence order between these files."
- **Doc.** (https://cursor.com/docs/rules): "Cursor supports AGENTS.md in the project root and
  subdirectories", and "Instructions from nested AGENTS.md files are combined with parent
  directories, with more specific instructions taking precedence."
- **Doc.** (https://cursor.com/docs/cli/using): "The CLI also reads AGENTS.md and CLAUDE.md at the
  project root (if present) and applies them as rules alongside .cursor/rules" — root only in this
  page, and no order given between the two files.
- **Doc.** (https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md): "While
  `GEMINI.md` is the default filename, you can configure this in your `settings.json` file. To
  specify a different name or a list of names, use the `context.fileName` property." A repository that ships an `AGENTS.md` without setting that
  property is never read by Gemini CLI, silently.

## Claude Code in detail

**Doc.** (https://code.claude.com/docs/en/memory), which files decide there is already a
`CLAUDE.md` in play:

- "Count, so Claude reads them instead of `AGENTS.md`: a `CLAUDE.md`, `.claude/CLAUDE.md`, or
  `CLAUDE.local.md` in your working directory or any directory above it."
- "Don't count, and keep loading alongside `AGENTS.md`: your `~/.claude/CLAUDE.md`, your
  organization's managed `CLAUDE.md`, and `.claude/rules/` files."

When none of the three counting files exist:

- "At session start: every `AGENTS.md` and `.claude/AGENTS.md` in your working directory and the
  directories above it. In an interactive session you see a line such as `no CLAUDE.md found;
  AGENTS.md loaded: /home/you/repo/AGENTS.md`."
- "As Claude works in subdirectories: a subdirectory's `AGENTS.md`, when Claude opens a file there
  with the Read tool and that subdirectory has none of the three `CLAUDE.md` files of its own" —
  in the shop repository this is how `api/AGENTS.md` is picked up once Claude reads a file under
  `api/`.
- "Inside each `AGENTS.md`: `@path` imports are expanded, `claudeMdExcludes` patterns apply, and
  subagents that skip project instructions skip these files too."
- "Not read: `AGENTS.local.md`, `AGENTS.override.md`, or anything under a `.agents/` directory" —
  an `AGENTS.override.md` copied from a Codex habit into the shop repository is invisible here.

**Note**, verbatim, on the most common silent failure: "Because `CLAUDE.local.md` counts, adding
one to keep your own uncommitted instructions in a project that relies on `AGENTS.md` stops Claude
from reading `AGENTS.md` for you."

**Project instructions**, the four documented values, set with `/config` or in a settings file:

| Value | What Claude reads |
| --- | --- |
| `claude-md-or-agents-md` | "Your `CLAUDE.md` files, or your `AGENTS.md` files when you have no `CLAUDE.md` or `CLAUDE.local.md` in your working directory or above it. This is the default." |
| `claude-md-and-agents-md` | "Your `CLAUDE.md` and `AGENTS.md` files together, each directory's `CLAUDE.md` files first and its `AGENTS.md` after them." |
| `claude-md` | "Your `CLAUDE.md` files only." |
| `managed-only` | "Only your organization's managed `CLAUDE.md` and auto memory at launch. Your project, local, and user `CLAUDE.md` files, your `.claude/rules/` files, and every `AGENTS.md` are left out." |

In a settings file, the value sits under the built-in plugin's ID:

```json settings.json
{
  "pluginConfigs": {
    "cc-plugin-agents-md@builtin": {
      "options": { "instructionFiles": "claude-md-and-agents-md" }
    }
  }
}
```

"Add it to `pluginConfigs` under `cc-plugin-agents-md@builtin`, the ID of the built-in plugin that
reads `AGENTS.md`. Claude Code reads the entry from `~/.claude/settings.json`, a `--settings` file,
or managed settings, and ignores it in project and local settings files." — the shop repository's
own shared `.claude/settings.json` or an untracked `.claude/settings.local.json` cannot set this
key; only user or managed settings can. The ID changed: "Before v2.1.285, the plugin's ID was
`agents-md@builtin`, and Claude Code ignored an entry under `cc-plugin-agents-md@builtin`... Claude
Code v2.1.285 and later reads an entry under either ID." A shop repository's old entry under
`agents-md@builtin` is therefore still read by recent versions and ignored in a project file all
the same.

Reading `AGENTS.md` directly "requires Claude Code v2.1.277 or later." Where that support is
unavailable — an older version, the built-in `agents-md` plugin disabled, or "some cases" of the
first session after an upgrade — Claude reads `CLAUDE.md` files only and the setting does not
appear in `/config`. "Before v2.1.281, some sessions, such as those on Amazon Bedrock or with
telemetry disabled, read `CLAUDE.md` files only."

## One file for several tools

- **Doc.** (https://code.claude.com/docs/en/memory): "When Claude isn't reading your `AGENTS.md`
  directly, you can still keep it as the one file every tool shares by putting an `@AGENTS.md`
  import in a `CLAUDE.md` next to it... Claude reads the imported file first, then the rest":

  ```markdown CLAUDE.md
  @AGENTS.md

  ## Claude Code

  Use plan mode for changes under `src/billing/`.
  ```

- "Keeping the import never makes Claude read `AGENTS.md` twice, whichever **Project
  instructions** value you use." A `CLAUDE.md` holding only that import may be removed once
  `AGENTS.md` is read directly, or kept for sessions that cannot load it directly.
- A symlink is the alternative when no Claude-specific content is needed: "If you don't need
  Claude-specific content, a symlink also works: `ln -s AGENTS.md CLAUDE.md`." Two documented
  constraints before choosing it: the Edit and Write tools "refuse to write through a symlink"
  and redirect edits to `AGENTS.md` itself; on Windows, "Git checks a committed symlink out as a
  plain text file unless `core.symlinks` is enabled", which leaves that clone with a one-line
  `CLAUDE.md` instead of real instructions.
- No other tool read for this page (Codex, Copilot, Copilot CLI, Cursor, Cursor CLI, Gemini CLI)
  documents an import or symlink convention of its own for pairing `AGENTS.md` with its native
  file name — not documented for those six.

## What audit.py checks, and what it does not

| Check | Reads | Fires on |
| --- | --- | --- |
| `01-agents-md-unread` | root `AGENTS.md` and `CLAUDE.md` | WARN — an `AGENTS.md` sits beside a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` that does not import it; the import path resolves from the importing file, imports are followed four hops, an `@` inside code does not count |
| `54-agents-md-variant` | file names on the repository path | NOTICE — an `AGENTS.override.md` (read by Codex, never by Claude Code) or an `AGENTS.local.md` (read by Claude Code never, and no agent documents reading it) is present. Silent when a `CLAUDE.md` or `CLAUDE.local.md` imports the file with `@` (followed four hops, inside the repository), unless the `AGENTS.md` of the same folder is imported too: Codex then reads only the override, Claude Code both (NOTICE) |
| `24-settings-scope` | shared `.claude/settings.json`, `.claude/settings.local.json` | ERROR — a `pluginConfigs` entry (under `cc-plugin-agents-md@builtin` or the older `agents-md@builtin`) is set in a project or local settings file, a scope Claude Code ignores for that key |

**Not checked** (read it by hand): content divergence between a `CLAUDE.md` and an `AGENTS.md`
that coexist for other tools' sake — no diff of what each one instructs; Codex's cumulative 32 KiB
`project_doc_max_bytes` cap across the root-to-cwd chain, which needs the Codex-side file list, not
just the repository's own.
