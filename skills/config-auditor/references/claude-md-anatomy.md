<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# `CLAUDE.md` anatomy

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Every statement carries its register: **Doc** (an Anthropic page, linked), **Measured** (observed
on a running Claude Code, version given), or **House convention** (this plugin's choice, with its
reason — never a platform rule, and a project may disagree).

Pages cited: [memory](https://code.claude.com/docs/en/memory) ·
[best-practices](https://code.claude.com/docs/en/best-practices) ·
[context-window](https://code.claude.com/docs/en/context-window) ·
[large-codebases](https://code.claude.com/docs/en/large-codebases) ·
[settings](https://code.claude.com/docs/en/settings).

Contents: [How it reaches the model](#how-it-reaches-the-model) · [Where the files live and in what order](#where-the-files-live-and-in-what-order) · [AGENTS.md](#agentsmd) · [Excluding files](#excluding-files) · [Imports](#imports) · [Size](#size) · [Surviving compaction](#surviving-compaction) · [Auto memory](#auto-memory) · [What belongs in it](#what-belongs-in-it) · [Writing the lines](#writing-the-lines) · [Diagnosis](#diagnosis) · [Review cadence](#review-cadence) · [Checks](#checks)

## How it reaches the model

- **Doc** ([memory](https://code.claude.com/docs/en/memory), troubleshooting): "CLAUDE.md content
  is delivered as a user message after the system prompt, not as part of the system prompt
  itself." It is context, not enforced configuration: there is "no guarantee of strict
  compliance, especially for vague or conflicting instructions."
- **Doc** (same page): it is read at the start of every session. After `/compact`, the
  project-root `CLAUDE.md` is re-read from disk and re-injected.
- **Doc** (same page): an instruction that must run at a fixed point — before every commit,
  after every edit — belongs in a hook, which executes regardless of what Claude decides. For
  instructions at system-prompt level, the documented lever is `--append-system-prompt`.

## Where the files live and in what order

**Doc** ([memory](https://code.claude.com/docs/en/memory), "Choose where to put CLAUDE.md files"
and "How CLAUDE.md files load"). All files are concatenated, none overrides another.

| Order | Scope | Location | Note |
| --- | --- | --- | --- |
| 1 | Managed policy | `/etc/claude-code/CLAUDE.md` (Linux), OS equivalents; or `claudeMd` in `managed-settings.json` | Cannot be excluded |
| 2 | User | `~/.claude/CLAUDE.md` | All projects on the machine |
| 3 | Ancestors and project | `CLAUDE.md` **or** `.claude/CLAUDE.md` in every directory from the filesystem root down to the working directory | Closer to the cwd = read later |
| 3b | Local, per level | `CLAUDE.local.md`, appended after that level's `CLAUDE.md` | Personal; add it to `.gitignore` |
| 4 | Subdirectories | `CLAUDE.md` / `CLAUDE.local.md` below the cwd | Loaded on demand, when Claude reads a file in that subdirectory |

- The two official project locations are `./CLAUDE.md` and `./.claude/CLAUDE.md`.
- A `CLAUDE.md` inside an `--add-dir` directory loads only with
  `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`.
- Block-level HTML comments are stripped before injection (comments inside code blocks are
  kept), so a maintainer note costs no context. `01-claude-md-size`, `01-claude-md-lines` and
  `17-always-loaded-budget` measure the file as injected, comments removed.
- A gitignored `CLAUDE.local.md` exists only in the worktree that created it; to share personal
  instructions across worktrees, import a file from home: `@~/.claude/<my-instructions>.md`.

## AGENTS.md

**Doc** ([memory](https://code.claude.com/docs/en/memory), "AGENTS.md"; requires 2.1.277):

- By default Claude reads `AGENTS.md` **only when there is no** `CLAUDE.md`, `.claude/CLAUDE.md`
  or `CLAUDE.local.md` in the working directory or above it. The user and managed `CLAUDE.md`
  and `.claude/rules/` do not count for that test.
- A repository with both files and no import gets `CLAUDE.md` only. To keep one shared file,
  put `@AGENTS.md` at the top of the `CLAUDE.md` beside it.
- Adding a `CLAUDE.local.md` to a project that relies on `AGENTS.md` silently stops Claude from
  reading `AGENTS.md`.
- Some sessions cannot read `AGENTS.md` directly (third-party providers, telemetry disabled,
  first session after an upgrade); the `@AGENTS.md` import works in all of them.

## Excluding files

**Doc** ([memory](https://code.claude.com/docs/en/memory), "Exclude specific CLAUDE.md files";
[large-codebases](https://code.claude.com/docs/en/large-codebases)):

- `claudeMdExcludes` skips files by path or glob. It applies to ancestor and subdirectory
  `CLAUDE.md` files, to rules files and directories, and to `AGENTS.md`.
- Patterns are matched against **absolute** paths — hence the leading `**/` in
  `"**/shop-monorepo/CLAUDE.md"`. A relative-looking pattern matches nothing.
- Settable at every layer (user, project, local, managed); arrays merge. Managed policy files
  cannot be excluded.

## Imports

**Doc** ([memory](https://code.claude.com/docs/en/memory), "Import additional files"):

- `@path` resolves **relative to the importing file**, not to the working directory. Absolute
  paths and `@~/…` work too.
- Recursion stops at **four hops**.
- Imports inside Markdown code spans and fenced blocks are not parsed: `` `@README` `` stays
  literal.
- An import resolving **outside the working directory** triggers an approval dialog the first
  time; if declined, those imports stay disabled and the dialog does not return.
- Imports organise; they do not save context. An imported file loads at launch like the rest.

## Size

- **Doc** ([memory](https://code.claude.com/docs/en/memory), "My CLAUDE.md is too large"):
  "Files over 200 lines consume more context and may reduce adherence." Two costs: tokens on
  every session, and instructions followed less reliably. **200 lines is the only documented
  target.** Checked by `01-claude-md-lines` (WARN).
- **Doc** (same page, "How it works"): "Claude Code loads a CLAUDE.md file of up to 4 MiB in full
  and skips a larger file." Above 4 MiB the file is **ignored entirely**, not truncated.
- **House convention**: `01-claude-md-size` raises an ERROR above **12 KB**. Reason: a line count
  does not cap tokens — 150 long lines cost more than 200 short ones — and the always-loaded
  budget (`17-always-loaded-budget`) needs a byte figure. It is doctrine, not a platform limit:
  a project may move it with a reason and a date in its `.claude/audit.local.json` overlay.
- **Doc** ([best-practices](https://code.claude.com/docs/en/best-practices)): "If Claude keeps
  doing something you don't want despite having a rule against it, the file is probably too long
  and the rule is getting lost."

## Surviving compaction

**Doc** ([context-window](https://code.claude.com/docs/en/context-window), "What survives
compaction"):

| Content | After compaction |
| --- | --- |
| Project-root `CLAUDE.md`, rules without `paths:` | Re-injected from disk |
| Auto memory | Re-injected from disk |
| Nested `CLAUDE.md`, rules with `paths:` | Summarised away; reload only when Claude next reads a matching file |
| Instructions given only in conversation | Lost unless the summary kept them |

"If a rule must persist across compaction, drop the `paths:` frontmatter or move it to the
project-root CLAUDE.md."

## Auto memory

**Doc** ([memory](https://code.claude.com/docs/en/memory), "Auto memory"):

- Notes Claude writes itself, in `~/.claude/projects/<project>/memory/`, shared by all worktrees
  of one repository, machine-local.
- `MEMORY.md` is the index: **only its first 200 lines or first 25 KB**, whichever comes first,
  load at session start. Topic files load on demand.
- On by default. Toggle in `/memory` (writes `autoMemoryEnabled`), per project with
  `"autoMemoryEnabled": false`, or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. Relocate with
  `autoMemoryDirectory` (absolute or `~/` path).
- Not passed to subagents (a fork excepted). A subagent's own memory is a separate directory.
- Consequence for an audit: a behaviour with no explanation in the tree may come from auto
  memory, `~/.claude/CLAUDE.md` or `~/.claude/rules/`. Look there before blaming the project file.

## What belongs in it

**Doc** ([memory](https://code.claude.com/docs/en/memory), "When to add to CLAUDE.md"): facts
Claude should hold in every session — build commands, conventions, layout, "always do X" rules.
Add a line when Claude makes the same mistake twice, when review catches something Claude
should have known, or when the same correction is typed again. "If an entry is a multi-step
procedure or only matters for one part of the codebase, move it to a skill or a path-scoped rule."

| Belongs | Does not belong |
| --- | --- |
| Commands Claude cannot guess (`npm run shop:seed`) | What Claude can read in the code (layout, dependency list) |
| Conventions that differ from tool defaults | Standard conventions Claude already follows |
| Hard project-wide constraints (no commit without asking) | Multi-step procedures → skill |
| Environment quirks (required env vars) | Rules for one directory → path-scoped rule |
| Pointers to withheld skills | Rows for skills the harness already lists (see below) |

**Doc** ([best-practices](https://code.claude.com/docs/en/best-practices)): `/doctor` proposes
trims for a checked-in `CLAUDE.md` — it cuts what Claude can derive from the codebase and keeps
pitfalls, rationale and non-default conventions.

**House convention** (`15-skill-index`): a skills index in `CLAUDE.md` names only the skills
withheld from the harness listing (`disable-model-invocation`, `skillOverrides`, `paths:`).
Reason: the listing already carries every other skill's name and description each turn; a row
for a listed skill pays twice and rots on the next rename.

## Writing the lines

- **Doc** ([best-practices](https://code.claude.com/docs/en/best-practices)): for each line, ask
  "Would removing this cause Claude to make mistakes?" If not, cut it.
- **Doc** (same page): "If Claude already does something correctly without the instruction,
  delete it or convert it to a hook."
- **Doc** (same page): if Claude keeps skipping one instruction, add emphasis such as
  "IMPORTANT" **to that line alone**. "If you emphasize many lines, none of them stands out."
- **Doc** ([memory](https://code.claude.com/docs/en/memory), "Write effective instructions"):
  concrete enough to verify ("Use 2-space indentation", not "Format code properly"); headers and
  bullets over dense paragraphs; no contradictions — "Claude may pick one arbitrarily."
- **House convention** (`12-no-code-comments`, WARN): no `//` or `/* */` outside fenced code in
  `CLAUDE.md`. Reason: a comment-style line in prose is almost always a pasted code fragment or a
  maintainer note; the documented place for the latter is an HTML comment, which is stripped.

## Diagnosis

**Doc** ([memory](https://code.claude.com/docs/en/memory), troubleshooting;
[best-practices](https://code.claude.com/docs/en/best-practices)):

| Question | Tool |
| --- | --- |
| Did the file load? | `/context`, list under **Memory files** |
| Which files exist at which scope? | `/memory` |
| What could be trimmed? | `/doctor` |
| Why did a rule or frontmatter not apply? | `claude --debug` (shows parse errors) |
| Which instruction file loaded, when, why? | `InstructionsLoaded` hook |
| No file yet | `/init` generates one; it suggests improvements to an existing one rather than overwriting |

## Review cadence

- **Doc** ([best-practices](https://code.claude.com/docs/en/best-practices)): "Treat CLAUDE.md
  like code: review it when things go wrong, prune it regularly, and test changes by observing
  whether Claude's behavior actually shifts."
- **Doc** ([large-codebases](https://code.claude.com/docs/en/large-codebases)): review
  `CLAUDE.md` edits in pull requests, and revisit after major model releases — "instructions
  that worked around an older model's limitation may become overhead once a newer model handles
  the case on its own."

## Checks

| Id | Level | What it asserts | Register |
| --- | --- | --- | --- |
| `01-claude-md-exists` | ERROR (INFO when an `AGENTS.md` stands in) | `./CLAUDE.md` or `./.claude/CLAUDE.md` exists | Doc |
| `01-claude-md-lines` | WARN | ≤ 200 lines | Doc |
| `01-claude-md-size` | ERROR | ≤ 12 KB, overridable per project | House convention |
| `01-agents-md-unread` | WARN | An `AGENTS.md` beside a `CLAUDE.md` is imported with `@AGENTS.md` | Doc |
| `01-claude-local` | WARN | `CLAUDE.local.md` is ignored by the repository's git rules | Doc |
| `01-claude-md-import` | WARN | Each in-repo `@path` import resolves, relative to the importing file | Doc |
| `12-no-code-comments` | WARN | No `//` or `/* */` outside code fences | House convention |
| `15-skill-index` | ERROR (withheld skill not indexed) / WARN (listed skill indexed) | The skills index names withheld skills, and only them | House convention |
| `17-always-loaded-budget` | INFO / WARN / ERROR | `CLAUDE.md` + skill and agent descriptions under budget | House convention |

Path-scoped rules have their own page: [rules-anatomy.md](./rules-anatomy.md).
