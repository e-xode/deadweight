<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# `CLAUDE.md` anatomy

Contents: [Token budget](#token-budget) · [Loading hierarchy](#loading-hierarchy) · [Path-scoped rules (`.claude/rules/`)](#path-scoped-rules-clauderules) · [Mechanisms available but not adopted](#mechanisms-available-but-not-adopted) · [What belongs in `CLAUDE.md`](#what-belongs-in-claudemd) · [Required sections (current project)](#required-sections-current-project) · [Writing rules](#writing-rules) · [Anti-patterns specific to `CLAUDE.md`](#anti-patterns-specific-to-claudemd) · [When in doubt](#when-in-doubt)

`CLAUDE.md` is loaded **every turn** into the agent's system context. Every byte costs tokens on every request. This is the single hardest constraint on the file. Verified 2026-09-03 against Claude Code 2.1.259.

Partially re-verified 2026-09-20, at the source, on these points only: the 1,024-character cap on `description` (agent-skills/best-practices), the 1,536-character listing truncation of `description` + `when_to_use` (skills), the hook event catalogue and the semantics of `SessionStart` (hooks), and the behaviour of `disable-model-invocation` (skills). **Everything else on this page still carries the 2026-09-03 date** — it was not re-checked.


## Token budget

- **Target: ≤ 12 KB / ~3000 tokens.** Enforced as an `ERROR` by `scripts/audit.py` (project convention). Raised from 10 KB on 2026-08-12: the original figure was set while the harness skill-listing budget was the binding constraint on always-loaded context, which `skillListingBudgetFraction: 0.025` has since relieved.
- **Official Anthropic guideline: target under 200 lines per CLAUDE.md file.** This is the real ceiling and it is expressed in lines, not bytes. Its motive is **adherence**, not context cost — the docs are explicit that CLAUDE.md loads in full regardless of length, and that longer files are simply followed less reliably. The byte budget above is a stricter proxy that also caps the token cost.
- **Hard skip above 4 MiB.** A `CLAUDE.md` larger than that is not truncated — it is not loaded at all. The only upstream _limit_; everything else is guidance.
- The runtime "CLAUDE.md is too long" warning **scales with the model's context window** (2.1.169), so it fires later on a large window and is not a substitute for the 200-line target.
- If a section grows beyond ~30 lines, it almost always belongs in a skill.

## Loading hierarchy

_(Official — [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory))_

All levels are **merged** (not overridden) and presented to the model in this order:

1. **Managed policy** — org/enterprise-level, including inline `claudeMd` text in `managed-settings.json`.
2. **User instructions** — `~/.claude/CLAUDE.md` (personal, all projects).
3. **Project instructions** — `./CLAUDE.md` or `./.claude/CLAUDE.md` (team-shared, checked into git).
4. **Local instructions** — `./CLAUDE.local.md` (personal project-specific, **gitignored**).

`CLAUDE.local.md` is for preferences that don't belong in the shared file (sandbox URLs, personal test data). Add it to `.gitignore`.

`@path` imports resolve up to 4 hops deep and skip code spans and fences, but they **do not save context** — an imported file loads at launch like the rest. Use them for organisation only. A `CLAUDE.md` inside an `--add-dir` directory is not loaded unless `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` is set.

## Path-scoped rules (`.claude/rules/`)

_(Official — [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory) § path-specific rules)_

An alternative to putting everything in CLAUDE.md. Each `.md` file in `.claude/rules/` covers one topic. Rules **without** `paths:` frontmatter load unconditionally (same priority as `.claude/CLAUDE.md`). Rules **with** `paths:` frontmatter load only when Claude works on matching files.

```yaml
---
paths:
  - 'src/**/*.vue'
---
```

Use path-scoped rules to reduce context noise — instructions load only when relevant. Full anatomy and the discovery/glob mechanics: [rules-anatomy.md](./rules-anatomy.md).

## Mechanisms available but not adopted

Three upstream levers exist for this file. None is in use here; each is recorded so the decision is deliberate rather than forgotten.

| Mechanism                     | What it does                                                                                                                                                                  | Position here                                                                                                                                                        |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Block-level HTML comments     | Stripped **before** injection, so a maintainer note costs zero context while staying visible to anyone reading the file.                                                      | Available, not adopted. The project's no-comments-in-prose rule covers `CLAUDE.md` too, and a free note is still a note that drifts. Reach for a case study instead. |
| `claudeMdExcludes`            | Glob-excludes ancestor `CLAUDE.md` files and rules directories; arrays merge across settings layers.                                                                          | Not needed — single-package repo, no ancestor config.                                                                                                                |
| `claude-md-management` plugin | Anthropic's official 100-point rubric (commands 20 · architecture 20 · non-obvious patterns 15 · conciseness 15 · currency 15 · actionability 15) with a named red-flag list. | Optional **second opinion** at audit time, alongside `/doctor`'s trim proposals. Never auto-apply: it does not know which terseness here is deliberate.              |

## What belongs in `CLAUDE.md`

Only **hard rules** — operational, project-wide, non-negotiable, that the agent must apply without prior context loading.

| Belongs                                            | Does NOT belong                             |
| -------------------------------------------------- | ------------------------------------------- |
| Task completion protocol (validation gate)         | How a feature works                         |
| No auto-commit / no auto-validation rules          | Architecture explanations                   |
| Code-style hard limits (no comments, English only) | Tutorial content / long explanations        |
| Bash commands Claude can't guess                   | Anything Claude can infer from reading code |
| Agent fleet directory (1-line trigger per agent)   | Detailed agent prompts                      |
| Skills index (withheld skills only)                | Skill bodies                                |
| Sub-agent orchestration rules                      | Examples / case studies                     |
| Repo etiquette (branch naming, PR conventions)     | File-by-file codebase descriptions          |
| Dev env quirks (required env vars, gotchas)        | Info that changes frequently                |
| The "Golden Rule" (regression = audit)             | Standard conventions Claude already knows   |

Anything that needs more than 3 lines to explain → move to a skill and reference it from the index.

## Required sections (current project)

1. **Visual gate** — construction-vs-verification split for rendered game output; the request-gated `visual-qa` pass.
2. **Task completion protocol** — the validation gate (delegated to `hooks` agent).
3. **Hard rules** — no auto-commit, no code comments, English only, design-system-first, SSR-safe.
4. **Path-scoped rules** — instruction to read `.claude/rules/` on file edits.
5. **Agents directory** — the current agent-fleet table with one-line triggers (count changes as agents are added/removed — don't hardcode a number here or in CLAUDE.md's own heading without keeping both in sync).
6. **Sub-agent orchestration** — non-negotiable rules: validation is centralised, sub-agents return structured summaries, no out-of-scope work, every incoming request gets tracked.
7. **Golden Rule** — regression handling (audit, not patch).
8. **Meta** — load behaviour, budget reminder, link to `skill-creator`.
9. **Skills index** — the skills deliberately **withheld** from the harness listing, and nothing else. The harness injects every listed skill's name and description each turn, so a row for a listed skill is a duplicate that rots; a withheld skill nothing points at is unreachable.

## Writing rules

- **Imperative voice.** "Do X" / "Never Y" / "Delegate to Z". Not "should" / "may".
- **No prose explanations.** A rule is enforceable or it does not belong.
- **No code comments.** Inside fenced code blocks is fine; in prose, never.
- **Tables over bullets** for any structured enumeration (agents, skills, file-type matrices).
- **Cross-reference skills by name** (`see skill-creator`, `→ git-workflow`), never paste their content.

## Anti-patterns specific to `CLAUDE.md`

- Pasting a skill's introduction directly in `CLAUDE.md` "so the agent always sees it".
- Adding a "Tips" or "FAQ" section.
- Embedding procedural steps that change frequently (they will rot; a skill can be updated in isolation).
- Adding decorative emojis throughout prose (the `🚨` for the task-completion protocol is intentional and exceptional — it marks the single most-violated rule).

## When in doubt

If you're about to add content to `CLAUDE.md`, ask:

1. Will the agent need this on **every** turn? If no → skill.
2. Is it a **hard rule** or a **best practice**? Best practices → skill.
3. Is it more than **3 lines**? → skill.
4. Does it require **examples** to be understood? → skill.

Three "no" → it belongs in `CLAUDE.md`. Otherwise, write a skill (or extend an existing one).
