<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Audit checklist

Contents: [How to run](#how-to-run) · [`CLAUDE.md`](#claudemd) · [Skills](#skills-each-skillmd) · [References](#references-each-referencesmd) · [Evals](#evals-each-evalsevalsjson) · [Agents](#agents-each-claudeagentsnamemd) · [Settings](#settings-claudesettingsjson) · [Cross-cutting](#cross-cutting-whole-claude) · [Rules](#rules-clauderulesmd) · [Required exit](#after-making-changes--required-exit)

Each item is tagged `[AUTO]` (covered by `scripts/audit.py` — run it first) or `[MANUAL]` (qualitative — read carefully).

## How to run

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py
```

Then, in a fresh session, confirm what the harness actually loaded — `audit.py` reads files on disk
and cannot see the applied listing budget:

- `[MANUAL]` `/doctor` — the skill listing's real context cost and its biggest contributors.
- `[MANUAL]` `/context` — the Skills row, reported after the budget is applied.

## `CLAUDE.md`

- `[AUTO]` File size ≤ 12 KB.
- `[MANUAL]` Line count ≤ 200 (Anthropic's own guideline; the byte ceiling is the stricter proxy).
- `[AUTO]` No `//` or `/* */` comments outside fenced code blocks.
- `[MANUAL]` Every section is a **hard rule**, not a best practice, tutorial, or example.
- `[MANUAL]` Each agent in `## Agents directory` has a discriminating one-line trigger.
- `[MANUAL]` Skills index names the withheld skills only — never one the harness already lists.
- `[MANUAL]` No section duplicates content available in a skill.
- `[MANUAL]` "Task completion protocol" still names `hooks` as the validator and forbids self-validation.

## Skills (each `SKILL.md`)

- `[AUTO]` Valid YAML frontmatter with `name` and `description`.
- `[AUTO]` `name` in frontmatter matches the folder name.
- `[AUTO]` `description` is 80–1,024 characters. 1,024 is the Agent Skills spec's hard cap on the
  field; the 1,536 figure is the listing cutoff for `description` + `when_to_use` combined.
- `[AUTO]` `description` contains an anti-trigger clause (`Don't use`, `Anti-trigger`).
- `[AUTO]` Skill name is unique across `.claude/skills/`.
- `[AUTO]` `SKILL.md` ≤ 50 KB — an ERROR above it. Vendored skills (those shipping a `LICENSE.txt`)
  report INFO instead.
- `[AUTO]` `SKILL.md` ≤ 20 KB (≈ 5,000 tokens). Above it, everything past the first ~5,000 tokens is
  dropped when the skill is re-attached after the first auto-compaction: the body silently loses its
  tail mid-session. Move detail to `references/`. Vendored skills report INFO instead.
- `[AUTO]` Frontmatter scalars containing `': '` are quoted — an unquoted `Don't use for: …` is invalid strict YAML.
- `[AUTO]` A skill withheld from the listing (`disable-model-invocation`, or `skillOverrides` ≠ `on`) is named in the CLAUDE.md 'Skills index'.
- `[MANUAL]` A description that is hard to trim is a candidate for withholding, not a third diet — is the skill ever selected semantically, or only through an explicit pointer?
- `[AUTO]` All relative links (`./...`) resolve to existing files.
- `[AUTO]` No `//` comments outside fenced code blocks.
- `[MANUAL]` Description is **discriminating** — a different skill cannot match the same query equally well.
- `[MANUAL]` Description is **pushy** — encourages triggering on indirect phrasings.
- `[MANUAL]` Anti-triggers point to the **correct alternative** (skill / agent / framework concept).
- `[MANUAL]` `SKILL.md` is method + index, not encyclopedia (detail lives in `references/`).
- `[AUTO]` Twin skills — a mutually anti-triggering pair, A's description pointing `→ B` and B's
  pointing back `→ A` — both carry a `Division of responsibilities` heading.
- `[AUTO]` Each of those two tables has a row owned by the twin, and the concern text of the row
  naming the pair reads identically on both sides (whitespace, backticks, bold and `(this skill)`
  ignored). The tables are family-wide, so their other rows may legitimately differ.
- `[MANUAL]` The shared row says who owns what for the prompts that actually confuse the pair —
  a row that is identical but vague still routes nothing.
- `[MANUAL]` Routing table covers all `references/` files (and vice versa).

## References (each `references/*.md`)

- `[AUTO]` Files > 100 lines open with a `Contents:` block (Claude previews long files with partial reads).
- `[AUTO]` Files > 300 lines are split — a TOC does not buy exemption. Vendored skills excepted.
- `[AUTO]` Every `references/*.md` is linked or named from its own `SKILL.md`. A reference reachable
  only from a sibling reference is two hops from the body, and the second hop is the one Claude
  skips — it gets read partially, or not at all. Vendored skills are **not** exempt; non-markdown
  assets (images, JSON, code samples) are.
- `[MANUAL]` One topic per file.
- `[MANUAL]` No frontmatter (only skills have frontmatter).
- `[MANUAL]` Headings start at `#` (top-level).
- `[MANUAL]` No critical rule lives only here — it must also appear in `SKILL.md`, with a pointer.

## Evals (each `evals/evals.json`)

- `[AUTO]` The file parses and carries `skill_name` and `evals`.
- `[AUTO]` `skill_name` matches the skill folder.
- `[AUTO]` Every entry has `id`, `prompt`, `expected_output` and a non-empty `expectations` list of
  strings. `name` is an accepted optional slug.
- `[AUTO]` `id` is an integer or a slug string, unique within the file, and of a single type across
  it (mixed types warn; an all-slug file is accepted with an INFO, since the documented schema says
  integer).
- `[AUTO]` At least 3 evals (the official minimum).
- `[AUTO]` At least one anti-trigger case. Heuristic: an `id`/`name` containing `anti-trigger`,
  `not-trigger`, `should-not`, `defer`, `negative` or `near-miss`, or an expectation containing
  `defer`, `does not trigger` or `should not`. A suite that only tests triggering never tests the
  boundary.
- `[MANUAL]` The anti-trigger case is a genuine **near miss** — a prompt the neighbouring skill would
  plausibly win — not a distant subject the skill would never match anyway.
- `[MANUAL]` Prompts read like something the user would actually type, and name concrete repo paths
  where the skill's value depends on them.

## Agents (each `.claude/agents/<name>.md`)

- `[AUTO]` Frontmatter has `name`, `description`, `tools` (block scalars `>`/`|` parse correctly).
- `[AUTO]` Agent is listed in `## Agents directory` of `CLAUDE.md` (and vice versa).
- `[AUTO]` `description` is 80–900 characters and contains an anti-trigger clause.
- `[MANUAL]` Description follows the same discriminating + pushy + anti-trigger rules as skills.
- `[AUTO]` Every entry in `tools` is a real tool name — bare (`Read`), parameterised (`Agent(review)`,
  `Bash(git diff:*)`), an `mcp__*` name, or the `*` wildcard. The fan-out tool is `Agent`; there is no
  `Task`. (The environment does expose `TaskStop`/`TaskOutput`, but those manage background tasks —
  `Bash run_in_background`, named background agents/monitors — not sub-agent fan-out.)
- `[AUTO]` Every `skills:` preload target exists as `.claude/skills/<name>/SKILL.md`, and none of them
  carries `disable-model-invocation: true` — such a skill cannot be preloaded and must be read by path.
- `[AUTO]` `model`, when present, is `haiku`, `sonnet`, `opus`, `inherit`, or a `claude-*` id.
- `[AUTO]` Frontmatter keys beyond `name`/`description`/`tools`/`model`/`skills` are reported as INFO
  so upstream drift stays visible.
- `[MANUAL]` `tools` is the **minimum** required — every grant must be justified by something in the body. An unused grant is an unenforced boundary.
- `[MANUAL]` A `tools` grant that could escape its own contract is narrowed by parameter, not by prose
  (a read-only agent spawning sub-agents grants `Agent(<read-only type>)`, not bare `Agent`).
- `[MANUAL]` `model` matches the judgement the work needs, not its perceived importance. Consider `effort` before promoting a whole tier.
- `[MANUAL]` Domain knowledge comes from `skills:` preload, not from restating the skill in the body.
- `[MANUAL]` A background-capable agent depends only on tools that survive the background filter.
- `[MANUAL]` Body restates the sub-agent contract: scoped, no validation (except `hooks`), structured return.
- `[MANUAL]` Agent is actually used by the orchestrator — not "kept in case".

## Settings (`.claude/settings.json`)

- `[AUTO]` The file parses, and its top-level keys are reported as INFO on every run.
- `[AUTO]` `permissions.defaultMode` is not `bypassPermissions` or `auto`. Since Claude Code 2.1.257
  both are ignored at project scope — set them in user or managed settings, or pass
  `--permission-mode`. A project-scope entry reads as active but does nothing.
- `[AUTO]` Every `skillOverrides` key names a skill folder that exists.
- `[AUTO]` `.claude/settings.local.json` gets the same treatment when present.
- `[MANUAL]` Every key is one the installed Claude Code version still reads — a setting silently
  dropped upstream looks identical to one that works.

## Cross-cutting (whole `.claude/`)

- `[AUTO]` No skill folder lacks a `SKILL.md`.
- `[AUTO]` English-only heuristic (warns on common French function words in skills/references).
- `[AUTO]` No script in top-level `.claude/scripts/` (must live under the owning skill's `scripts/` folder).
- `[AUTO]` Rules in `.claude/rules/` have valid structure (see Rules section below).
- `[AUTO]` Always-loaded budget (CLAUDE.md bytes + **listed** skill descriptions + all agent descriptions) ≤ 43,000 chars (WARN) / 47,000 chars (ERROR); the effective total prints as INFO on every run, alongside how much is withheld.
- `[AUTO]` Every `➜ See skill: <name>` cross-reference resolves to an existing skill.
- `[MANUAL]` No two skills overlap silently. The mechanical check only catches pairs that already
  point at each other; an overlap neither description acknowledges is invisible to it.
- `[MANUAL]` `Skills index` in `CLAUDE.md` names every withheld skill and nothing else — it is not a copy of the harness listing.
- `[MANUAL]` Skills follow the project's own domain-prefix convention (worked example: `shop-*`, `ui-*`, `api-*`, `data-*`).

## Rules (`.claude/rules/*.md`)

- `[AUTO]` Each rule file is valid markdown (parseable).
- `[AUTO]` If `paths:` frontmatter is present, it contains at least one non-empty glob pattern.
- `[AUTO]` Every `paths:` glob expands to at least one real file. Build output and dependency trees
  (`node_modules/`, `dist/`, …) are pruned before matching, so a glob whose only hits are vendored
  still counts as zero. A glob that matches nothing makes the rule permanently inert — the worst
  failure mode for a path-scoped guardrail, because the file itself looks fine. `{a,b}` alternatives
  and `**` recursion are expanded; an unescaped `[` in a zero-match glob is called out, since it
  opens a character class instead of matching a literal bracket.
- `[AUTO]` Rule file size ≤ 2 KB (warn — should probably be a skill if larger).
- `[AUTO]` No `//` comments outside fenced code blocks.
- `[AUTO]` English-only heuristic (same as skills).
- `[MANUAL]` Content is a **constraint/guardrail**, not knowledge/procedure.
- `[MANUAL]` Rule does not duplicate content already in a skill body.
- `[MANUAL]` Unconditional rules (no `paths:`) have a justified reason.
- `[MANUAL]` The glob set covers the files the rule's body is actually about — a matching glob is not
  the same as the right glob.

## After making changes — required exit

1. Run `python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py`. Exit code must be `0` (no errors). It prints the number of check groups it ran — that line,
   and the `CHECKS` tuple it comes from, are the inventory. A count copied into prose here was wrong by eight groups for two weeks and broke nothing, which is exactly why it drifted.
2. Resolve any new `WARN` introduced by the change, or grant it an exemption in the project's
   `.claude/audit.local.json` — with the `reason` and the `date`, which check 31 requires. An
   exemption carrying its reason is the decision record for that warning; no separate document.
3. Propose any corrections to the user. **Never auto-apply.**
