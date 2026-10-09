<!-- The worked examples in this file describe one fictional project: an online shop whose
     repository ships `.github/copilot-instructions.md` for project-wide guidance, plus a
     modular rule `.github/instructions/shop-api.instructions.md` scoped with
     `applyTo: "api/**"`, and a second one scoped to the `ui/` folder. It is invented, and
     deliberately not `foo`/`bar`: a placeholder with no domain teaches nothing about scope or
     naming. Where only the structure matters, <angle-bracket> placeholders are used instead. -->

# Copilot anatomy

Contents: [Files and surfaces](#files-and-surfaces) · [Instructions frontmatter](#instructions-frontmatter) · [Prompts and custom agents](#prompts-and-custom-agents) · [Precedence](#precedence) · [What Copilot reads from a Claude Code configuration](#what-copilot-reads-from-a-claude-code-configuration) · [What audit.py checks, and what it does not](#what-auditpy-checks-and-what-it-does-not)

Verified against the docs on 2026-09-28.

Sources read for this page, official domains only (docs.github.com, code.visualstudio.com,
github.blog/changelog). Each fact below names its short label in parentheses:

- **repo-instructions** — https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions
- **personal-instructions** — https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-personal-instructions
- **org-instructions** — https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-organization-instructions
- **cli-instructions** — https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions
- **create-custom-agents** — https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/create-custom-agents
- **agents-configuration** — https://docs.github.com/en/copilot/reference/custom-agents-configuration
- **code-review-tutorial** — https://docs.github.com/en/copilot/tutorials/customize-code-review
- **vscode-instructions** — https://code.visualstudio.com/docs/agent-customization/custom-instructions
- **vscode-custom-agents** — https://code.visualstudio.com/docs/copilot/customization/custom-chat-modes
- **changelog-agents-md** — https://github.blog/changelog/2025-08-28-copilot-coding-agent-now-supports-agents-md-custom-instructions/
- **changelog-exclude-agent** — https://github.blog/changelog/2025-11-12-copilot-code-review-and-coding-agent-now-support-agent-specific-instructions/
- **changelog-4000-limit** — https://github.blog/changelog/2026-06-12-copilot-code-review-new-configurations-and-controls/

The angle of this page: Copilot's configuration is split across several file types, each read by
a different subset of surfaces (Chat in an IDE, the cloud coding agent, code review, the CLI,
Copilot Chat on github.com). A file placed correctly for one surface can be silently invisible to
another, with no error anywhere.

## Files and surfaces

| File | Chat in VS Code | coding agent | code review | CLI | github.com |
| --- | --- | --- | --- | --- | --- |
| `.github/copilot-instructions.md` | yes | yes | yes | not documented | yes |
| `.github/instructions/*.instructions.md` | yes | yes | yes | yes (narrower, see below) | not documented |
| `.github/agents/*.agent.md` | yes | yes (cloud agent) | not documented | yes | yes (cloud agent) |

`.github/copilot-instructions.md`: "These are specified in a `copilot-instructions.md` file in
the `.github` directory of the repository" (repo-instructions). The VS Code page locates and
names it identically for "project-wide guidance" (vscode-instructions). The coding-agent
changelog confirms it stays read alongside newer formats: "the agent continues to support
GitHub's `.github/copilot-instructions.md` and `.github/instructions/**.instructions.md`
formats, plus `CLAUDE.md` and `GEMINI.md` files" (changelog-agents-md). Code review lists it at
the same level as `AGENTS.md` and `*.instructions.md` (code-review-tutorial). Its use by Copilot
CLI is not documented in these sources — the CLI page names `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`
and `*.instructions.md`, not `copilot-instructions.md` (cli-instructions).

`.github/instructions/*.instructions.md`: "VS Code automatically attaches files with an applyTo
pattern that matches the files being changed" (vscode-instructions). Copilot CLI reads the same
extension but narrower: "Modular repository instructions, discovered in the standard locations
but not intermediate directories" (cli-instructions) — unlike `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`,
which the CLI also discovers in intermediate directories. Whether plain Copilot Chat on github.com
reads these files is not documented in these sources.

`.github/agents/*.agent.md`: the cloud coding agent reads it from "the `.github/agents` directory
of your target repository" (create-custom-agents). Its properties apply to "agent profiles in
GitHub.com, the Copilot CLI, and supported IDEs" (agents-configuration), and custom agents are
"in public preview for JetBrains IDEs, Eclipse, and Xcode" (agents-configuration). Whether code
review reads `.agent.md` files is not documented in these sources.

## Instructions frontmatter

Example frontmatter for `.instructions.md` (vscode-instructions):

```yaml
---
name: 'Python testing'
description: 'Use when creating or updating Python unit tests.'
applyTo: '**/*.py'
---
```

- `applyTo`: "Glob pattern that automatically applies the instructions to matching files,
  relative to the workspace root. Use `**` to match all files." (vscode-instructions)
- `description`: "Describes the tasks for which the file is relevant. Include it for on-demand
  discovery." (vscode-instructions)
- `name`: appears in the example above; the sources read for this page document nothing further
  about how it is used — not documented.
- Without `applyTo` or `description`, the documented behaviour is to "attach the file manually
  when you want to use it" (vscode-instructions): no automatic discovery.
- `excludeAgent`, documented only in the changelog: "Set `excludeAgent: \"code-review\"` to hide
  your instructions file from Copilot code review. Set `excludeAgent: \"coding-agent\"` to hide
  your instructions file from Copilot coding agent." Default, when absent: "your instructions
  file will be used by all agents" (changelog-exclude-agent). Only these two string values are
  documented; nothing is said about a value for VS Code Chat or the CLI.
- Whether `applyTo` accepts a comma-separated list of several glob patterns, and how a comma
  inside a brace group such as `**/*.{css,scss}` is parsed, is **not documented** in the sources
  read for this page.

## Prompts and custom agents

Custom agents were renamed from custom chat modes: "Custom agents were previously known as custom
chat modes. The functionality remains the same" (vscode-custom-agents), and "If you have existing
`.chatmode.md` files, rename them to `.agent.md` and place them in one of the supported custom agent
locations" (vscode-custom-agents). The supported workspace locations are `.github/agents` and, in
Claude format, `.claude/agents`; `.github/chatmodes` is not among them (vscode-custom-agents), yet
it is a deprecated location rather than an unread one: the [VS Code 1.106 release notes](https://code.visualstudio.com/updates/v1_106) say existing chat
modes "continue to work and are automatically treated as custom agents" — the same host also recognizes a Claude-format
location: "Workspace (Claude format): `.claude/agents` folder" (vscode-custom-agents).

Naming and size limits for the cloud agent's `.agent.md` (create-custom-agents): "the filename may
only contain the following characters: `.`, `-`, `_`, `a-z`, `A-Z`, `0-9`," and "The prompt can be
a maximum of 30,000 characters."

Recognized frontmatter for the cloud agent (agents-configuration): `description` (required), and
optionally `name`, `target`, `tools`, `model`, `disable-model-invocation`, `user-invocable`,
`infer`, `mcp-servers`, `metadata`. Two are out of scope there: "`argument-hint` and `handoffs`
properties are currently not supported for Copilot cloud agent on GitHub.com," and `mcp-servers`
/ `metadata` are "Not used in VS Code and other IDE custom agents" (agents-configuration).

VS Code's own fields (vscode-custom-agents): `description` ("shown as placeholder text in the
chat input field"), `tools` ("A list of tool or tool set names that are available for this custom
agent"), `model` ("Specify a single model name (string) or a prioritized list of models
(array)").

## Precedence

Between personal, repository and organisation instructions: "Personal instructions take the
highest priority. Repository instructions come next, and then organization instructions are
prioritized last." This is additive, not exclusive: "all sets of relevant instructions are
provided to Copilot" (repo-instructions). A repository-wide file and a path-specific
`.instructions.md` also combine rather than override: "instructions from both files are used"
(repo-instructions).

Scope limits: personal instructions are "only supported for GitHub Copilot Chat in GitHub"
(personal-instructions) — not VS Code, not the coding agent. Organisation instructions are
"currently only supported for Copilot Chat on GitHub.com, Copilot code review on GitHub.com and
Copilot cloud agent on GitHub.com" (org-instructions).

Between several files of the same type in VS Code, no tie-break is documented: "Applicable
instruction sources are additive. Do not depend on a file order or precedence rule to resolve
conflicts because discovery and merge behavior can differ by harness" (vscode-instructions). One
documented exception: several `AGENTS.md` files do resolve by nearest match — "the nearest
`AGENTS.md` file in the directory tree will take precedence" (vscode-instructions).

## What Copilot reads from a Claude Code configuration

| File | coding agent | CLI | code review | VS Code (Local agent) |
| --- | --- | --- | --- | --- |
| `AGENTS.md` | yes, incl. nested | yes, incl. intermediate dirs | yes | gated, nested off by default |
| `CLAUDE.md` | yes | yes | not documented | gated |
| `GEMINI.md` | yes | yes | not documented | not documented |

Coding agent: "Alongside `AGENTS.md`, the agent continues to support GitHub's
`.github/copilot-instructions.md` and `.github/instructions/**.instructions.md` formats, plus
`CLAUDE.md` and `GEMINI.md` files," and nested files are supported: "You can also create nested
`AGENTS.md` files which apply to specific parts of your project" (changelog-agents-md).

Copilot CLI: each of `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` is "Agent instructions, discovered in
the standard locations" — "the repository root, the current working directory, intermediate
directories between them, and any directories nested in the path of a file it is working on"
(cli-instructions). An include mechanism spans formats: "In `.github/copilot-instructions.md`,
`AGENTS.md`, or `CLAUDE.md`, use `@` followed by a relative path to include another file"
(cli-instructions).

Code review: `AGENTS.md` is listed — "`AGENTS.md`: Repository-level agent-specific instructions"
(code-review-tutorial). Whether it reads `CLAUDE.md` or `GEMINI.md` is not documented.

VS Code Local agent: "For the Local agent, configure the `chat.useAgentsMdFile` setting to enable
or disable support for `AGENTS.md` files." For nested files, "The setting is disabled by default"
(`chat.useNestedAgentsMdFiles`). For `CLAUDE.md`: "configure the `chat.useClaudeMdFile` setting"
(vscode-instructions). Whether `chat.useAgentsMdFile` and `chat.useClaudeMdFile` default to on or
off is **not documented** on the page read. `GEMINI.md` is not mentioned on that page at all —
silence, not a confirmed absence. The same page separately recognizes Claude Code's own rule
files: "For `.claude/rules` instructions files, use a `paths` property instead of `applyTo` for
glob patterns" (vscode-instructions).

**Consequence for a Claude Code user** (reading, not a quote): a repository's `CLAUDE.md` reaches
Copilot's cloud coding agent and Copilot CLI without any change on the repository's part — both
list it as a supported format next to `AGENTS.md`. Inside VS Code, the same file only reaches
Copilot Chat's Local agent if `chat.useClaudeMdFile` is turned on, and whether that ships on or
off is not documented here, so a Claude Code user cannot assume that opening the same repository
in VS Code gives Copilot Chat the instructions Claude Code uses. Directory-scoped guidance fares
worse: nested `AGENTS.md` files are off by default in VS Code, and no equivalent nested toggle for
`CLAUDE.md` is documented in these sources — so instructions that Claude Code picks up from a
subdirectory may not reach VS Code's Copilot agent at all.

## What audit.py checks, and what it does not

These ids are implemented in `audit.py` (0.20.0), measured on public repositories before release.

| Check | Reads | Fires on |
| --- | --- | --- |
| `56-copilot-chatmode` | `.github/chatmodes/*.chatmode.md` | file present in the deprecated location — NOTICE. The workspace location is now `.github/agents` (vscode-custom-agents); VS Code still loads a chat mode as a custom agent (VS Code 1.106 release notes). |
| `56-copilot-instructions-name` | files under `.github/instructions/` | a file not ending `.instructions.md` — WARN. The extension is part of the documented discovery contract (vscode-instructions); anything else is not read, without an error. |
| `56-copilot-apply-to` | frontmatter of `.github/instructions/*.instructions.md` | `applyTo` glob matching no file in the repository — NOTICE, measured 4 of 18 real on 98 public repositories, most of the rest in toolkits that distribute instruction files (**House**: evaluated against the working tree, not documented behaviour, a design heuristic only); neither `applyTo` nor `description` present — NOTICE, since the file then requires manual attachment (vscode-instructions). |
| `56-copilot-reads-claude-md` | `./CLAUDE.md` only, with Copilot files present | `CLAUDE.md` names a Claude Code-only mechanism (`/memory`, `/hooks`, `/doctor`, the `Task` or `Skill` tool, `.claude/commands`, `.claude/hooks`, `.claude/settings.json`) that Copilot's agent, CLI and code review read as instructions they cannot follow (NOTICE). Not counted: subagents and `.claude/rules/` (Copilot has custom agents, VS Code reads `.claude/rules/`), `.claude/agents` (VS Code: "Workspace (Claude format)"), the 13 slash commands the Copilot CLI reference documents, and `.claude/hooks` / `.claude/settings.json` when `.vscode/settings.json` sets `"chat.useClaudeHooks": true` (comments removed first: settings.json is JSON with Comments; VS Code hooks, off by default; a user-level setting is not visible from the repository). |

**Not checked** (read it by hand, or ask the surface directly):

- Presence or absence of `.github/copilot-instructions.md` relative to `AGENTS.md` — a coverage
  question depending on which surfaces a project targets, not an error condition.
- `.agent.md` frontmatter field validity (`tools`, `model`, `mcp-servers`, …) or the
  30,000-character body limit.
- `excludeAgent` values outside the two documented strings.
- Personal- or organisation-level instructions: both live outside the repository.
- Whether the VS Code settings that gate `AGENTS.md`/`CLAUDE.md` reading
  (`chat.useAgentsMdFile`, `chat.useClaudeMdFile`, `chat.useNestedAgentsMdFiles`) are turned on —
  user- or workspace-level settings, not repository files.
- `applyTo` comma-in-brace parsing — not documented, so nothing is asserted about it.
- The historical 4,000-character truncation in Copilot code review, removed per
  changelog-4000-limit: a check for it would test a condition no longer live.
