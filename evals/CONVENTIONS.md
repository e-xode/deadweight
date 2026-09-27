# Conventions register — what this plugin asks for that Anthropic does not

Some checks enforce a **house convention**: a choice this plugin makes, not a rule Anthropic
documents. Each one is listed here with where it stands against Anthropic's own guidance, the
evidence that it helps, and when that evidence is re-measured. A convention whose effect is not
re-measured is a belief with a date on it; models change, and what helped one release may cost the
next.

**Rules of this register**

- A row is **re-measured on every new Claude model** the plugin targets, and at least quarterly.
- A convention is **retired** when its measured effect is ≈ 0 on every targeted model, on two
  consecutive measurements.
- A convention **contradicted by Anthropic** stays only while a measurement shows it beats the
  documented practice; its finding says so, and names the documented alternative.
- Numbers come from this plugin's eval suite and its A/B runs — see `PROVENANCE.md`. Sources were
  checked on 2026-09-23 against the raw documentation pages, Anthropic's public repositories and
  guides, archived versions of the pages, and specialised sites.

## Register

| Convention (check) | Anthropic's position | Evidence it helps | Last measured | Next |
| --- | --- | --- | --- | --- |
| Negative clause in a **skill** description (`04-skill-description-antitrigger`) | Documented **as a remedy** for a skill that triggers too often ("Add negative triggers" — *The Complete Guide to Building Skills for Claude*); the docs say "make the description more specific"; `skill-creator` favours "pushy" descriptions | Confusable pair: triggering 1/10 → 10/10 with crossed clauses (`two-skills-compete`). **Isolated skill: no effect** — true triggers 60/60 with and without the clause, false triggers on near misses naming the excluded topics 0/40 with and without (Haiku, 2026-09-23). **Real pairs, smaller**: on 8 real twin pairs whose positive clauses already told them apart, removing the crossed clause moved "right skill loaded" by only +1.7 pts on Opus 5.5 (95% CI −1.4..+5.2) and +2.7 pts on Haiku 4.5 (−2.7..+8.4), both containing zero (2026-09-27, 1,152 runs per model). The 1/10 → 10/10 holds for a pair built to collide, not as a general effect size. So: a WARN on confusable pairs (check 33), a NOTICE elsewhere | 2026-09-27 | next model |
| Negative clause in an **agent** description (`08b-agent-description`) | **Recommended** by Anthropic's `plugin-dev`: "Be specific about when NOT to use the agent"; the sub-agents docs require nothing. "Doc" means the Claude Code docs: a recommendation is quoted in the message and does not set the grade, so a NOTICE (WARN under `profile: house`), as for skills (04) | not measured here; on skills, no effect on real pairs (row above) | 2026-09-27 | when an agent routing case exists |
| Agent description 80–900 chars (`08b-agent-description`) | Anthropic: 10–5,000, best 200–1,000; the docs cap the **total** at 15,000 tokens | none | — | retire or align |
| Split a reference over 300 lines (`16-reference-size`) | **Contradicted**: a table of contents past 100 lines (docs) or 300 (`skill-creator`) | none | — | align on the table of contents |
| `## Agents directory` table in CLAUDE.md (`09-*`) | No source. The harness already lists agents, so the table is paid twice | none | — | measure or retire |
| CLAUDE.md ≤ 12 KB (`01-claude-md-size`) | Docs: under 200 lines (`01-claude-md-lines`). "25 KB" is MEMORY.md's; Claude Code's own warning scales with the context window | an external study found no effect of CLAUDE.md length (25–500 lines) on adherence | — | align on lines |
| Always-loaded budget 43,000 chars (`17-always-loaded-budget`) | No global budget; per-mechanism budgets only (skill listing: 1 % of context) | none | — | retire or derive from context |
| Rule ≤ 2 KB (`14-rule-size`) | "One topic per file" | none | — | — |
| No `.claude/scripts/` (`13-no-global-scripts`) | Scripts under the skill is Anthropic's anatomy; nothing forbids a project folder | none | — | — |
| English only (`11-english-only`, `14-rule-english-only`) | The multilingual page says to **set the language explicitly**, not to write in English | none | — | — |
| "Division of responsibilities" tables (`27-*`) | No source | **None measured.** 8 real twin pairs (6 confusable by `33`, 2 not), 4 arms (anti-trigger × table), 96 requests written from the bodies with descriptions hidden, blind second labeller, adversarial review by four fresh model reviewers (2 of 96 replaced; no human review), 3 repetitions, `Skill` the only tool: the table moved "right skill loaded" by −0.3 pts on Opus 5.5 (95% CI −3.8..+3.1) and +0.4 pts on Haiku 4.5 (−3.8..+4.6). Its ceiling — a wrong first pick never repaired — was 3.5 % and 8.8 %. Downgraded to NOTICE; retired at the next null measurement | 2026-09-27 | next model |
| Description ≥ 80 chars (`04`) | No source | none | — | — |
