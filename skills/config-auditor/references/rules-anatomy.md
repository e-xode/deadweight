<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Rules anatomy (`.claude/rules/`)

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Registers: **Doc** (an Anthropic page, linked), **Measured** (observed on a running Claude Code,
version given), **House convention** (this plugin's choice, with its reason — a project may
disagree). Unless stated otherwise, "Doc" means
[memory § Organize rules with `.claude/rules/`](https://code.claude.com/docs/en/memory).

Contents: [What a rule is](#what-a-rule-is) · [When a rule loads](#when-a-rule-loads) · [Compaction](#compaction) · [File format](#file-format) · [Globs and their silent failures](#globs-and-their-silent-failures) · [Discovery, user rules, symlinks](#discovery-user-rules-symlinks) · [Conflicts](#conflicts) · [Rules, skills or CLAUDE.md](#rules-skills-or-claudemd) · [House conventions](#house-conventions) · [Proving a rule loaded](#proving-a-rule-loaded) · [Checks](#checks)

## What a rule is

A Markdown file under `.claude/rules/`, one topic per file. **Doc**: it is context, like
`CLAUDE.md`, not enforced configuration. Two kinds:

- **Without `paths:`** — loaded at launch "with the same priority as `.claude/CLAUDE.md`". This
  is a documented, legitimate way to split a large `CLAUDE.md` into modules; it costs exactly
  what the same lines would cost in `CLAUDE.md`.
- **With `paths:`** — loaded only when a matching file is read.

## When a rule loads

- **Doc**: "Path-scoped rules trigger when Claude reads files matching the pattern, not on every
  tool use."
- **Reported upstream, not measured here** (`anthropics/claude-code#93248`, open): writing or
  **creating** a matching file does not load the rule. A rule meant to guard how new
  `src/api/<name>.ts` files are written would then never fire for a file created without a
  matching file having been read first. *Inference, not verified:* an edit usually loads it,
  since the Edit tool requires a prior Read of the file.
- So a path-scoped rule is **not** a "100 % hit, set and forget" guardrail. It reaches Claude
  when a matching file is read, and only until the next compaction.
- **Doc** ([context-window](https://code.claude.com/docs/en/context-window)): the rule lands in
  message history as a one-line "Loaded" notice for the user; the content goes to the model.
- **Doc** ([skills](https://code.claude.com/docs/en/skills), frontmatter reference): skills accept
  `paths:` too, same format. **Measured** (2.1.280): a skill with `paths:` is withheld from the
  initial listing and becomes available once a matching file is read — the skill-side
  equivalent, with a description and on-demand body.

## Compaction

**Doc** ([context-window § What survives compaction](https://code.claude.com/docs/en/context-window)):

- Rules without `paths:` are re-injected from disk after compaction.
- Rules with `paths:` "load into message history when their trigger file is read, so compaction
  summarizes them away". They return only when Claude next reads a matching file.
- "If a rule must persist across compaction, drop the `paths:` frontmatter or move it to the
  project-root CLAUDE.md."

## File format

```markdown
---
paths:
  - "src/api/**/*.ts"
  - "tests/api/**/*.test.ts"
---

# API handlers

- Validate every request body with the shared schema in `src/api/schema/`.
- Return errors in the `{ code, message }` shape.
```

**Doc** (rule frontmatter reference):

- `paths` is **the only field a rule reads**. Any other field is ignored without an error —
  `globs:` (Cursor's name for it), `description:`, `alwaysApply:` do nothing.
- `paths` accepts a YAML list **or** a comma-separated string.
- If the YAML between the markers does not parse, the frontmatter is ignored and **the rule loads
  as if it had no `paths`** — it becomes global, silently. `claude --debug` shows the parse error.
- The frontmatter is stripped before the rule enters context.

## Globs and their silent failures

**Doc** (path-specific rules):

- A rule's whole `paths` list shares one budget of **1,000 expanded patterns and 4 MiB**. Brace
  groups multiply: `{ui,api}/**/*.{ts,tsx}` is four patterns; patterns without braces do not
  count. A pattern that would exceed the budget is used unexpanded, and its literal braces match
  nothing.
- `[` opens a bracket expression. Only a `[` that **cannot** form one — `photos [2024/**` — makes
  the pattern invalid; it then matches nothing while the rule's other patterns keep working.
  `data/[ab]*.csv` is a valid class, not an error. Escape a literal bracket: `\[`.
- Matching also works through a symlinked path to the project (2.1.198).

None of these failures produces a runtime error, which is why `22-rule-glob-match` expands every
glob, brace branches included, and reports one matching no file in the repository.

**House convention** (`22-rule-glob-match`, NOTICE): a glob rooted in a directory the repository's
git ignores (`dist/**`, `data-exports/**`) can only be checked on machines that hold those
untracked files. The auditor reports it as NOTICE and keeps it out of the floor, so the same commit gives
the same result everywhere. For every git-dependent judgement the auditor uses **the
repository's own ignore rules only**, never the user's global `core.excludesFile`.

## Discovery, user rules, symlinks

**Doc**:

- Discovery is **recursive**: `.claude/rules/ui/`, `.claude/rules/api/` are found. A flat layout
  is a choice, not a constraint.
- **User rules** in `~/.claude/rules/` apply to every project and load **before** project rules.
  A machine-local rule can shape behaviour without appearing anywhere in the repository — look
  there when a behaviour has no explanation in the tree.
- Symlinks work; cycles are handled. A symlink whose target lies **outside the working
  directory** is treated like an external import: nothing loads until external imports are
  approved for the project, and after that **only the rules without `paths:`** load.
- `claudeMdExcludes` applies to rules files and directories (patterns against absolute paths).

## Conflicts

**Doc**: "if two rules contradict each other, Claude may pick one arbitrarily." The same holds
between a user rule and a project rule — neither overrides the other. Review `CLAUDE.md`, nested
`CLAUDE.md` files and `.claude/rules/` together, periodically, for contradictions.

## Rules, skills or CLAUDE.md

| Criterion | Rule with `paths:` | Rule without `paths:` | Skill | `CLAUDE.md` |
| --- | --- | --- | --- | --- |
| Loads | When a matching file is **read** | At launch | When invoked or judged relevant | At launch |
| After compaction | Gone until next matching read | Re-injected | Body re-injected, capped at 5,000 tokens | Re-injected (project root) |
| Carries | A short constraint tied to files | A project-wide constraint, modularised | Procedure, knowledge, scripts | Project-wide facts and constraints |

Sources: [memory](https://code.claude.com/docs/en/memory),
[context-window](https://code.claude.com/docs/en/context-window). The **Doc** note on the memory
page: "For task-specific instructions that don't need to be in context all the time, use skills."

A rule and a skill can share a domain: the rule states the constraint
("never import `api-*` modules from `ui-*` code"), the skill `shop-ssr` teaches the approach.
Keep the rule short enough that duplicating the skill is impossible.

## House conventions

Each is this plugin's choice. A project can decline it; the auditor says which checks are doctrine.

- **Size ≤ 2 KB** (`14-rule-size`, WARN). Reason: a rule loads whole on every matching read with
  no description to decide by; past ~2 KB it is usually a skill's body wearing a rule's clothes.
- **A frontmatter block carries `paths:`** (`14-rule-no-paths`, WARN). Reason: a rule with
  frontmatter but no `paths:` is almost always a scoping attempt that failed (wrong field name,
  empty value); a rule meant to be global needs no frontmatter at all.
- **No `//` comment lines outside code fences** (`14-rule-code-comments`, WARN). Reason: same as
  `12-no-code-comments` for `CLAUDE.md`.
- **Language** (`14-rule-english-only`, WARN, heuristic). Reason: a rule is read by a model and by
  every contributor; the check detects one language only and a project writing in another
  language should exempt it in its overlay. It is not a platform requirement.
- **Naming**: `kebab-case.md`, named for what it guards (`api-error-shape.md`).
- **Where the inventory lives**: the globs in each file's `paths:` are the source of truth. A table
  of rules, if a project wants one, belongs in that project's own files, never in a shared plugin.

## Proving a rule loaded

The auditor proves a rule is well-formed and that its globs reach real files. It cannot prove the
harness loaded it. **Doc**: `/context` lists the loaded memory files; `claude --debug` shows
frontmatter parse errors; the
[`InstructionsLoaded` hook](https://code.claude.com/docs/en/hooks#instructionsloaded) logs which
`CLAUDE.md` and rules files loaded, when, and why — observability only, it enforces nothing.

## Checks

| Id | Level | What it asserts | Register |
| --- | --- | --- | --- |
| `14-rule-unknown-field` | WARN | No frontmatter field other than `paths` | Doc |
| `22-rule-glob-match` | WARN / NOTICE | Each glob matches a file in the repository (NOTICE, not in the floor, when rooted in a git-ignored path) | Doc + House convention |
| `14-rule-size` | WARN | ≤ 2 KB | House convention |
| `14-rule-no-paths` | WARN | Frontmatter present ⇒ `paths:` present | House convention |
| `14-rule-code-comments` | WARN | No `//` lines outside fences | House convention |
| `14-rule-english-only` | WARN | No French-language content (heuristic) | House convention |

Anti-patterns for rules: [antipatterns.md § F](./antipatterns.md#f-rules-clauderules).
