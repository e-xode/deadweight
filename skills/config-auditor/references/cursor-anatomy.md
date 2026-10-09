<!-- The worked examples in this file describe one fictional project: an online shop
     whose Cursor rules live under `.cursor/rules/`: `shop-api.mdc` (backend conventions)
     and `ui-components.mdc` (frontend conventions), organized into subfolders `api/` and
     `ui/`. It is invented, and deliberately not `foo`/`bar`: a placeholder with no domain
     teaches nothing about scoping or precedence. Where only the structure matters,
     <angle-bracket> placeholders are used instead. -->

# Cursor anatomy

Contents: [Where rules live](#where-rules-live) · [Frontmatter and the four rule types](#frontmatter-and-the-four-rule-types) · [`globs` syntax](#globs-syntax) · [`.cursorrules` (legacy)](#cursorrules-legacy) · [Size guidance](#size-guidance) · [What Cursor reads from a Claude Code configuration](#what-cursor-reads-from-a-claude-code-configuration) · [What audit.py checks, and what it does not](#what-auditpy-checks-and-what-it-does-not)

Verified against the docs on 2026-09-28.

Every claim below is tagged **Doc.** (an official Cursor page says it, quoted verbatim, with a
link) or **Not documented.** (the pages read for this file say nothing explicit about it — never
filled from memory). Sources: `cursor.com/docs/rules`, `cursor.com/help/customization/rules`,
`cursor.com/docs/cli/using`, `cursor.com/help/customization/skills`, `cursor.com/docs/subagents`.
No third-party blog, forum or repository is cited.

## Where rules live

**Doc.** Project rules "live in `.cursor/rules` as `.mdc` files and are version-controlled. They
are scoped using path patterns, invoked manually, or included based on relevance."
([Rules](https://cursor.com/docs/rules))

**Doc.** The extension is mandatory; a `.md` file in the same folder is silently ignored, not an
error: "A plain `.md` file in `.cursor/rules` is ignored by the rules system because it has no
frontmatter to specify `description`, `globs`, and `alwaysApply`. If you prefer plain markdown, use
AGENTS.md instead." ([Rules](https://cursor.com/docs/rules)) — check
`55-cursor-rule-ignored`.

The docs illustrate the trap with an annotated tree ([Rules](https://cursor.com/docs/rules)): in
`.cursor/rules/`, `react-patterns.mdc` is recognized as a project rule and `api-guidelines.md` is
ignored for its wrong extension; rules also nest in subfolders such as `frontend/`.

**Doc.** Rules are identified by full path, not filename: "Cursor identifies rules by their full
file path, not their name alone. Two rules with the same filename in different folders both apply
if their conditions match. There are no conflicts or overrides based on filename."
([Rules, help center](https://cursor.com/help/customization/rules)) — `api/shop-api.mdc` and a
hypothetical `ui/shop-api.mdc` are two distinct rules, not a collision.

## Frontmatter and the four rule types

**Doc.** Three frontmatter fields govern a rule: `description`, `globs`, `alwaysApply`. The docs
name four types: "Always Apply: Apply to every chat session. Apply Intelligently: When Agent
decides it's relevant based on description. Apply to Specific Files: When file matches a specified
pattern. Apply Manually: When @-mentioned in chat" ([Rules](https://cursor.com/docs/rules)).

The truth table, as the docs give it ([Rules](https://cursor.com/docs/rules)):

| `alwaysApply` | `description` | `globs` | Behavior |
| --- | --- | --- | --- |
| true | — | — | Always included; globs and description are ignored |
| false | — | provided | Auto-attached when a matching file is in context |
| false | provided | omitted | The agent reads the description and pulls the rule in when relevant |
| false | omitted | omitted | Included only when you @-mention the rule in chat |

| `alwaysApply` | `description` | `globs` | Type | Behavior |
| --- | --- | --- | --- | --- |
| `true` | — | — | Always Apply | always included; globs and description ignored |
| `false` | — | provided | Auto Attached | included when a matching file is in context |
| `false` | provided | omitted | Agent Requested | agent decides from the description |
| `false` | omitted | omitted | Manual | included only via `@`-mention |

**Doc.** The help center names the same four types differently — "Apply Intelligently" / "Apply to
Specific Files" / "Apply Manually" — and never uses "Auto Attached" or "Agent Requested"
([Rules, help center](https://cursor.com/help/customization/rules)): two official pages, one
mechanism, two vocabularies.

**Doc.** The documented failure modes for the first two rows: "Why isn't my rule being applied?
Check the rule type. For Apply Intelligently, ensure a description is defined. For Apply to
Specific Files, ensure the file pattern matches referenced files."
([Rules](https://cursor.com/docs/rules)) → checks `55-cursor-rule-manual` and
`55-cursor-rule-glob`.

**Doc.** Rules also have a bounded surface: "Rules only apply to Agent (Chat). They do not apply
to Tab completion, Inline Edit, or Bugbot PR reviews."
([Rules, help center](https://cursor.com/help/customization/rules))

## `globs` syntax

**Doc.** "Use globs to scope a rule to specific files or directories. Separate multiple patterns
with commas." ([Rules](https://cursor.com/docs/rules)) Its pattern table gives the example `docs/**/*.md, docs/**/*.mdx` for `.md` and `.mdx` files
under `docs/`, comma-separated ([Rules](https://cursor.com/docs/rules)).

So `api/shop-api.mdc` scopes itself with something like `globs: api/**/*.ts, api/**/*.js` — one
string, comma-separated, no documented requirement to quote an individual pattern.

**Not documented.** A YAML list form (`globs: ["*.ts", "*.js"]`) for project rules. The page
describes the comma-separated string only. For *skills* — a separate mechanism, field `paths` —
a list is explicitly supported: "paths accepts a list or a comma-separated string of glob
patterns." ([Skills](https://cursor.com/help/customization/skills)). Whether a YAML list works for
a rule's `globs` is untested behavior, not a documented shortcut, and is not assumed to work.

## `.cursorrules` (legacy)

**Doc.** Absent entirely from the current rules reference page; documented only on the help
center's migration FAQ: "The `.cursorrules` file in your project root is legacy and will be
deprecated." ([Rules, help center](https://cursor.com/help/customization/rules)) Migration steps
given there: "Copy your `.cursorrules` content into the new rule file" ... "Delete the
`.cursorrules` file from your project root."
([Rules, help center](https://cursor.com/help/customization/rules))

Read literally, "will be deprecated" is a future tense, not a statement that Cursor has already
stopped reading the file. **Not documented**: the date or version at which `.cursorrules` stops
being read. → check `55-cursorrules-legacy`.

## Size guidance

**Doc.** "Keep rules under 500 lines" / "Split large rules into multiple, composable rules"
([Rules](https://cursor.com/docs/rules)).

**Not documented**: a maximum number of rules per repository, a total budget in KB or tokens for
all of `.cursor/rules/`, or a size limit for `AGENTS.md` or `CLAUDE.md`.

## What Cursor reads from a Claude Code configuration

This is the section that matters most to a Claude Code user: Cursor does not confine itself to
`.cursor/`.

**Doc.** `AGENTS.md`, root and nested, combined by specificity: "AGENTS.md is a simple markdown
file for defining agent instructions. Place it in your project root as an alternative to
`.cursor/rules` for straightforward use cases." and "Cursor supports AGENTS.md in the project root
and subdirectories." ([Rules](https://cursor.com/docs/rules)) Nested files combine rather than
override: "Nested AGENTS.md support in subdirectories is now available. ... Instructions from
nested AGENTS.md files are combined with parent directories, with more specific instructions
taking precedence." ([Rules](https://cursor.com/docs/rules))

**Doc.** `CLAUDE.md` is read the same way, automatically, at the root: "Cursor reads CLAUDE.md
files the same way it reads AGENTS.md. Place a CLAUDE.md file in your project root and Cursor
picks it up automatically." ([Rules, help center](https://cursor.com/help/customization/rules))
It carries a stronger status than an ordinary rule, ignoring `alwaysApply` entirely: "CLAUDE.md
files are always applied to every conversation, regardless of any alwaysApply frontmatter
setting. This ensures compatibility with projects that also use Claude Code. If you need
conditional rules, use project rules in .cursor/rules/ instead."
([Rules, help center](https://cursor.com/help/customization/rules))

Consequence: a `CLAUDE.md` written for Claude Code — it has no frontmatter, so it never declared
`alwaysApply` in the first place — becomes, inside Cursor, an implicit **Always Apply** rule on
every conversation in that repository. A persona, a protocol or a house style meant for one tool's
onboarding is applied by the other tool too, with no opt-out short of deleting or renaming the
file. Cursor's own fix for "I need this conditional" is to move that logic into `.cursor/rules/`
instead of `CLAUDE.md` — not to add a frontmatter field to `CLAUDE.md`, which the format does not
have.

**Doc.** The CLI reads the same three sources, explicitly combined: "The CLI agent supports the
same rules system as the editor. You can create rules in the `.cursor/rules` directory to provide
context and guidance to the agent." and "The CLI also reads AGENTS.md and CLAUDE.md at the project
root (if present) and applies them as rules alongside .cursor/rules."
([CLI](https://cursor.com/docs/cli/using))

**Not documented**: an explicit priority between `.cursor/rules`, `AGENTS.md` and `CLAUDE.md` when
all three exist at the root — only the *nested-AGENTS.md* precedence is stated, not the
cross-mechanism arbitration.

**Doc.** Skills are read from Claude Code's own folder for compatibility, alongside Cursor's:
"Skills are automatically loaded from .agents/skills/, .cursor/skills/, ~/.agents/skills/ (global
on the local machine), and ~/.cursor/skills/ (global on the local machine), including nested
project subdirectories... For compatibility, Cursor also loads skills from Claude and Codex
directories: .claude/skills/, .codex/skills/, ~/.claude/skills/, and ~/.codex/skills/."
([Skills](https://cursor.com/help/customization/skills)) A skill authored at
`.claude/skills/<name>/SKILL.md` for Claude Code is therefore also a Cursor skill, without being
copied or declared anywhere under `.cursor/`.

**Doc.** Subagents run the reverse precedence — a project's own `.cursor/` wins over the Claude
Code equivalent on a name collision: "Project subagents take precedence when names conflict. When
multiple locations contain subagents with the same name, .cursor/ takes precedence over .claude/
or .codex/." ([Subagents](https://cursor.com/docs/subagents)) A subagent named `<verifier>`
defined both at `.cursor/agents/<verifier>.md` and `.claude/agents/<verifier>.md` runs the
`.cursor/` prompt under Cursor; the same name under Claude Code alone still runs the `.claude/`
prompt — one name, two different prompts, depending on which tool is asked.

## What audit.py checks, and what it does not

Implemented in `audit.py` (0.20.0), measured on public repositories before release.

| Check | Reads | Fires on |
| --- | --- | --- |
| `55-cursor-rule-ignored` | `.cursor/rules/**` | a `.md` file present where only `.mdc` is read (WARN); a skill folder kept there, once per folder (WARN); a folder rule `<name>/RULE.md` (NOTICE: a format the current rules page does not name - it requires `.mdc` - so whether it loads depends on the Cursor version) |
| `55-cursor-rule-manual` | `.mdc` frontmatter | no `alwaysApply`, no `globs`, no `description`: never applied on its own (NOTICE) |
| `55-cursor-rule-glob` | `.mdc` `globs`, repository tree | a glob pattern matching no file in the repository (NOTICE: 79 % real on 98 public repositories, under the 90 % bar - the rest sat in repositories that distribute rules for others) |
| `55-cursorrules-legacy` | `.cursorrules` at the root | file present (NOTICE) |
| `55-cursor-reads-claude-md` | `./CLAUDE.md` only, with `.cursor/` present | `CLAUDE.md` names a Claude Code-only mechanism (a built-in slash command Cursor CLI does not document, the `Task` or `Skill` tool, `.claude/commands`) that Cursor applies to every conversation (NOTICE). Not counted, because Cursor has them: subagents, `.claude/skills/`, `.claude/agents/` (cursor.com/docs/context/subagents, Claude compatibility), `.claude/hooks/` and `.claude/settings*.json` (third-party hooks, on by default), and `/model`, `/clear`, `/resume`, `/rewind`, `/mcp`, `/plugin`, `/config` (Cursor CLI slash commands). |

**Not checked**: a `globs` value written as a YAML list rather than a comma-separated string —
its behavior is untested, so nothing is flagged as wrong either way; the content of a rule, a
skill, an `AGENTS.md` or a `CLAUDE.md` file, only their shape and presence.
