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
| Negative clause in a **skill** description (`04-skill-description-antitrigger`) | Documented **as a remedy** for a skill that triggers too often ("Add negative triggers" — *The Complete Guide to Building Skills for Claude*); the docs say "make the description more specific"; `skill-creator` favours "pushy" descriptions | Confusable pair: triggering 1/10 → 10/10 with crossed clauses (`two-skills-compete`). **Isolated skill: no effect** — true triggers 60/60 with and without the clause, false triggers on near misses naming the excluded topics 0/40 with and without (Haiku, 2026-09-23). So: a WARN on confusable pairs (check 33), an INFO elsewhere | 2026-09-23 | next model |
| Negative clause in an **agent** description (`08b-agent-description`) | **Recommended** by Anthropic's `plugin-dev`: "Be specific about when NOT to use the agent" | not measured here | — | when an agent routing case exists |
| Agent description 80–900 chars (`08b-agent-description`) | Anthropic: 10–5,000, best 200–1,000; the docs cap the **total** at 15,000 tokens | none | — | retire or align |
| Split a reference over 300 lines (`16-reference-size`) | **Contradicted**: a table of contents past 100 lines (docs) or 300 (`skill-creator`) | none | — | align on the table of contents |
| `## Agents directory` table in CLAUDE.md (`09-*`) | No source. The harness already lists agents, so the table is paid twice | none | — | measure or retire |
| CLAUDE.md ≤ 12 KB (`01-claude-md-size`) | Docs: under 200 lines (`01-claude-md-lines`). "25 KB" is MEMORY.md's; Claude Code's own warning scales with the context window | an external study found no effect of CLAUDE.md length (25–500 lines) on adherence | — | align on lines |
| Always-loaded budget 43,000 chars (`17-always-loaded-budget`) | No global budget; per-mechanism budgets only (skill listing: 1 % of context) | none | — | retire or derive from context |
| Rule ≤ 2 KB (`14-rule-size`) | "One topic per file" | none | — | — |
| No `.claude/scripts/` (`13-no-global-scripts`) | Scripts under the skill is Anthropic's anatomy; nothing forbids a project folder | none | — | — |
| English only (`11-english-only`, `14-rule-english-only`) | The multilingual page says to **set the language explicitly**, not to write in English | none | — | — |
| "Division of responsibilities" tables (`27-*`), description ≥ 80 chars (`04`) | No source | none | — | — |
