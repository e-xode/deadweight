<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Rules anatomy (`.claude/rules/`)

Contents: [What rules are](#what-rules-are) · [Loading behaviour (official Anthropic)](#loading-behaviour-official-anthropic) · [Glob budget and silent-failure modes](#glob-budget-and-silent-failure-modes) · [File format](#file-format) · [When to use rules vs skills vs CLAUDE.md](#when-to-use-rules-vs-skills-vs-claudemd) · [Conventions worth adopting](#conventions-worth-adopting) · [Keeping the set legible](#keeping-the-set-legible) · [Proving a rule actually loaded](#proving-a-rule-actually-loaded) · [Anti-patterns (rules-specific)](#anti-patterns-rules-specific)

Verified 2026-09-03 against Claude Code 2.1.259.

Partially re-verified 2026-09-20, at the source, on these points only: the 1,024-character cap on `description` (agent-skills/best-practices), the 1,536-character listing truncation of `description` + `when_to_use` (skills), the hook event catalogue and the semantics of `SessionStart` (hooks), and the behaviour of `disable-model-invocation` (skills). **Everything else on this page still carries the 2026-09-03 date** — it was not re-checked.


## What rules are

Rules are lightweight, path-scoped instruction files that load **automatically** when Claude works on files matching their glob pattern. They live in `.claude/rules/` and complement skills and `CLAUDE.md`.

## Loading behaviour (official Anthropic)

- Rules **without** `paths:` frontmatter load unconditionally (same priority as `.claude/CLAUDE.md`).
- Rules **with** `paths:` frontmatter load ONLY when Claude reads or edits files matching the glob.
- Multiple rules can load simultaneously if several globs match the active file.
- Rules are merged into the system prompt alongside `CLAUDE.md` content — they do not override it.
- **User-level rules exist too**: `~/.claude/rules/` loads **before** project rules. A machine-local rule can therefore shape behaviour in this repo without appearing anywhere in it — check there first when a behaviour has no explanation in the tree.
- **Discovery is recursive.** Subdirectories under `.claude/rules/` are found, and symlinked directories and files work (cycles are handled). The flat layout below is a project choice, not a platform constraint.

## Glob budget and silent-failure modes

A rule's whole `paths:` list shares a budget of **1,000 expanded patterns / 4 MiB**. Brace expansion counts against it, so `src/**/*.{vue,js,mjs,scss,css,json}` is six patterns, not one.

Two failures are silent — the rule keeps loading, its glob simply never matches anything:

- **Over-budget patterns are used unexpanded**, so a pattern that only makes sense expanded matches nothing.
- **An unescaped `[`** makes that pattern match nothing. The rest of the rule still works, which is what makes it hard to spot.

Neither produces an error at runtime — which is why `audit.py` carries the static substitute: one check validates that a `paths:` glob is present and well-formed, and another **expands every glob, brace branches included, and reports one that matches no real file** as a silently inert guardrail. That is as far as static analysis reaches; proving a rule _loaded_ is the next section.

## File format

```yaml
---
paths:
  - 'src/**/*.vue'
---
# Title (optional but recommended)

Instruction text in markdown. Short, imperative, guardrail-style.
```

### Frontmatter fields

| Field   | Required             | Description                                                         |
| ------- | -------------------- | ------------------------------------------------------------------- |
| `paths` | No (but recommended) | YAML list of glob patterns. Without it, rule loads unconditionally. |

No other frontmatter fields are used. Rules are intentionally minimal.

## When to use rules vs skills vs CLAUDE.md

| Criterion        | `.claude/rules/`                                         | `.claude/skills/`                         | `CLAUDE.md`                          |
| ---------------- | -------------------------------------------------------- | ----------------------------------------- | ------------------------------------ |
| **Content type** | Guardrails, constraints, hard DON'Ts                     | Knowledge, procedures, how-to             | Global hard rules                    |
| **Loading**      | Deterministic by file path (100% hit)                    | Semantic/description matching (may miss)  | Every turn                           |
| **Size**         | Short (< 2 KB recommended)                               | Rich (up to 50 KB + references)           | Minimal (< 12 KB)                    |
| **Structure**    | Flat markdown, no references                             | SKILL.md + references/ + scripts/         | Sections with tables                 |
| **Maintenance**  | Near-zero (set and forget)                               | Active (needs audit, evals)               | Careful (token budget)               |
| **Use when…**    | You need a constraint to fire reliably on specific files | You need to teach Claude domain knowledge | You need a rule on every single turn |

### Decision flowchart

1. Is this needed on **every turn**, regardless of file context? → `CLAUDE.md`
2. Is this tied to a **specific file path or pattern**? → Rule
3. Does it require **more than ~20 lines** to explain? → Skill
4. Is it a **constraint** ("don't do X") rather than knowledge ("here's how to do X")? → Rule
5. Does Claude need **examples, references, or procedures**? → Skill

### Complementary use (rule + skill)

A rule and a skill can cover the same domain at different levels:

- **Rule** = lightweight guardrail that always fires (e.g., "never import server modules from client code")
- **Skill** = deep knowledge loaded on demand (e.g., full SSR architecture and browser API patterns)

The rule prevents mistakes. The skill teaches the right approach.

## Conventions worth adopting

### Naming

- `kebab-case.md` (e.g., `testing-conventions.md`, `locale-delegation.md`)
- Descriptive — the filename should indicate what the rule guards

### Content style

- **Imperative voice** — "Do X", "Never Y", "Always Z"
- **No code comments** in prose (same rule as skills and CLAUDE.md)
- **English only** (same rule as all persisted artefacts)
- **Concise** — aim for < 2 KB. If growing beyond that, consider a skill instead.

### Placement

All rules live in `.claude/rules/`, **flat — no subdirectories. This is a project choice, not a platform limit**: discovery is recursive and symlinks work. A few dozen files stay legible flat, and a flat directory makes the inventory table below verifiable at a glance. Revisit only if the count roughly doubles.

## Keeping the set legible

Globs live in each file's `paths:` frontmatter — the authoritative source. A project that keeps a
table of its rules keeps it in its own `CLAUDE.md` or `.claude/audit/decisions.md`, never in this
skill: an inventory is project state, and state shipped inside a plugin is wrong in every project
but the one it was copied from.

## Proving a rule actually loaded

`audit.py` proves a rule is _well-formed_. It cannot prove the harness ever loaded it — that is the
one question static analysis structurally cannot answer, and with eighteen path-scoped rules it is
worth asking.

The upstream answer is the **`InstructionsLoaded` hook** (2.1.69): it fires whenever a `CLAUDE.md`
or `.claude/rules/*.md` loads, with the reason as its matcher (`session_start`, `path_glob_match`,
`nested_traversal`, `include`, `compact`). It enforces nothing — pure observability, which is why it
is the one hook worth naming.

**Reviewed 2026-09-03 and declined; re-examined 2026-09-20 and still declined.**
_Amended 2026-09-20: the premise below — "the project runs zero native hooks" — stopped being true
that day, when a `SessionStart` audit hook was wired here and in 14 other fleet repositories.
`InstructionsLoaded` stays declined on its own merits: it is a second, runtime-only path to a
question `audit.py` already answers statically, and the current line is "observation hooks are
allowed", not "every observation hook is worth its wiring". The sentence is kept as the record of
the decision this amendment replaces._ **Reviewed 2026-09-03 and declined.** The project runs zero
native hooks (core rule 10), and an observability-only hook is not enough to reopen that. The substitutes stand: `audit.py` for
structure and glob reach, and `--debug` for a one-off runtime look when a rule seems not to fire.

## Anti-patterns (rules-specific)

- **F1.** Rule that duplicates a skill's body (bloats context on every matching file)
- **F2.** Rule without `paths:` that could be a line in `CLAUDE.md` (unconditional rule = same cost)
- **F3.** Rule > 2 KB (should probably be a skill with proper structure)
