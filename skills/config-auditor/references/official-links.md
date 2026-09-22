<!-- The worked examples in this file (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example, and a
     placeholder with no domain teaches nothing about naming, scoping or overlap.
     Where only the structure matters, the examples use <angle-bracket> placeholders
     instead, which cannot rot into dead references. -->

# Official Anthropic documentation

Contents: [Agent Skills (the spec)](#agent-skills-the-spec) · [Claude Code — core mechanisms](#claude-code--core-mechanisms) · [Claude Code — measurement and diagnostics](#claude-code--measurement-and-diagnostics) · [Claude Code — orchestration at scale](#claude-code--orchestration-at-scale) · [Doctrine and engineering posts](#doctrine-and-engineering-posts) · [Upstream source](#upstream-source) · [How to use this list](#how-to-use-this-list)

Curated entry points behind the rules in this skill. **Verified 2026-09-03 against Claude Code
2.1.259.** Every URL below was fetched live on that date, in this audit or in its two research
sweeps; none is quoted from memory.

Two hosts, and the split matters: `platform.claude.com` documents **Agent Skills**, the
runtime-independent spec; `code.claude.com` documents **Claude Code**, which implements it and adds
mechanisms of its own (`skillOverrides`, `context: fork`, sub-agent frontmatter). Older
`docs.anthropic.com/en/docs/claude-code/*` and `docs.claude.com/en/docs/claude-code/*` links still
301-redirect but are no longer canonical — link to `code.claude.com`.

## Agent Skills (the spec)

- **[Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)** — the three-level progressive-disclosure model, skill structure, how metadata is preloaded and bodies are read on demand.
- **[Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)** — conciseness, degrees of freedom, naming, description writing, the 64-char name and 1,024-char description caps, the reference-file TOC threshold (100 lines), the "at least three evaluations" rule, and the authoring checklist.
- **[AgentSkills.io](https://agentskills.io)** · **[the specification](https://agentskills.io/specification)** — the open standard Claude Code skills follow, and the six-field portable frontmatter subset.
- **[Evaluating skill output quality](https://agentskills.io/skill-creation/evaluating-skills)** — the eval file format, baseline comparison, assertion grading, and the iteration loop the vendored `skill-creator` automates.

## Claude Code — core mechanisms

- **[Skills in Claude Code](https://code.claude.com/docs/en/skills)** — where skills live and their precedence (including the bundled-alias carve-out), the twenty-field frontmatter reference, `disable-model-invocation` / `user-invocable`, `paths:`, `context: fork`, `$ARGUMENTS`, the skill content lifecycle, and the "descriptions are cut short" entry that documents the listing budget and its least-invoked-first degradation.
- **[Sub-agents](https://code.claude.com/docs/en/sub-agents)** — the seventeen supported frontmatter fields, model resolution order, the tool filters applied to every sub-agent and to background ones, `skills:` preload, `memory:`, `maxTurns`, resume via `SendMessage`, and what a sub-agent's initial context actually contains.
- **[Memory and CLAUDE.md](https://code.claude.com/docs/en/memory)** — the CLAUDE.md hierarchy, `@path` imports, the 4 MiB hard skip, **the "under 200 lines" figure** (it lives here, not in best-practices), and `.claude/rules/` path-specific instructions with their glob budget.
- **[Explore the context window](https://code.claude.com/docs/en/context-window)** — startup load order and, critically, **what survives compaction**: the 5,000-token-per-skill / 25,000-token combined re-attach budget.
- **[Extend Claude Code (features overview)](https://code.claude.com/docs/en/features-overview)** — the canonical "which mechanism for which goal" tables: CLAUDE.md vs rules vs skills vs hooks vs subagents.
- **[Settings](https://code.claude.com/docs/en/settings)** · **[Settings reference](https://code.claude.com/docs/en/settings-reference)** — every key and the precedence chain across managed / CLI / local / project / user scopes. The reference page is an index: it lists keys without types or defaults, so read defaults from the feature pages.
- **[Commands reference](https://code.claude.com/docs/en/commands)** — the built-in and bundled command surface. Note that `/skill-doctor`, `/skills`, `/schedule` and `/run` are **absent** from it; they are early-access or undocumented.
- **[Hooks](https://code.claude.com/docs/en/hooks)** — the event catalogue (31–33 depending on how aliases are counted), the five handler types, `if:` conditions, `permissionDecision`, hooks in skill and agent frontmatter, and the `agent_type` payload field. An observation hook on `SessionStart` is the safe shape; hooks that lengthen the work loop are still refused — core rule 10, amended 2026-09-20, and case study CS-8 as amended.
- **[Output styles](https://code.claude.com/docs/en/output-styles)** — not deprecated; five built-ins, fixed at session start, and the only instruction surface that survives compaction untouched. Worth adopting: one `outputStyle` per repository family, set in `.claude/settings.json`.
- **[Checkpointing](https://code.claude.com/docs/en/checkpointing)** — `/rewind`, the 100-snapshot window, and the caveat that matters here: **background sub-agent edits are not restored**.
- **[Plugins](https://code.claude.com/docs/en/plugins)** · **[Plugins reference](https://code.claude.com/docs/en/plugins-reference)** — manifest schema, the `claude plugin` CLI (`validate --strict --json`, manifest-free on a bare `.claude/skills` since 2.1.233), and how plugin skills are namespaced. Relevant when a project **vendors** a skill rather than installing it.

## Claude Code — measurement and diagnostics

- **Corrected 2026-09-20 — the telemetry half of the line below is not in the documentation.**
  Both pages were read at source that day. `skill_activated` and `invocation_trigger` appear on
  **neither** [debug-your-config](https://code.claude.com/docs/en/debug-your-config) — which
  documents no telemetry at all — **nor**
  [monitoring-usage](https://code.claude.com/docs/en/monitoring-usage). What monitoring-usage does
  document: telemetry is switched on with `CLAUDE_CODE_ENABLE_TELEMETRY=1` plus
  `OTEL_METRICS_EXPORTER` / `OTEL_LOGS_EXPORTER` (`console` for a local look); the events are
  `claude_code.user_prompt`, `claude_code.assistant_response`, `claude_code.tool_result` and
  `claude_code.tool_decision`, with `api_request` / `api_error` named among the correlation
  attributes; and there is a **`skill.name`** attribute — *"Skill active for the request, set by
  the Skill tool, a `/` command, or inherited by a spawned subagent"* — alongside `query_source`
  (`"main"` / `"subagent"` / `"auxiliary"`). `skill_activated` / `invocation_trigger`: **not
  found 2026-09-20** — either removed from an earlier version of the docs, or written here by
  inference. The original line is kept below, unedited.
  Whether `skill.name` on the cost and token metrics is enough to answer "which skills actually
  fire?" is an experiment to run, not a configuration to lay down. **No telemetry is enabled by
  this correction.**
- **[Debug your config](https://code.claude.com/docs/en/debug-your-config)** — `--safe-mode` (the no-config baseline arm), `--debug`, and the OpenTelemetry `skill_activated` event with its `invocation_trigger` attribute.
- **[Monorepos and large repos](https://code.claude.com/docs/en/large-codebases)** — layered CLAUDE.md, nested config, `claudeMdExcludes`, path-scoped skills at scale.
- **[Statusline](https://code.claude.com/docs/en/statusline)** — a local script, zero API tokens, receiving `context_window.used_percentage`, `effort.level` and cost fields. The cheapest live readout for a project whose doctrine is a context ratchet.

## Claude Code — orchestration at scale

- **[Agent teams](https://code.claude.com/docs/en/agent-teams)** — experimental, off by default. Read it for the two hazards that would break this fleet: named subagents launch as teammates, and teammates ignore `skills:`. ➜ See [agent-anatomy.md](./agent-anatomy.md) § Agent teams.
- **[Dynamic workflows](https://code.claude.com/docs/en/workflows)** — the Workflow tool, its size guidelines and runtime caps. Relevant only if a job outgrows a handful of subagents.

## Doctrine and engineering posts

- **[Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)** — orchestrator-workers, parallelisation, model routing, and when a deterministic workflow beats an agent.
- **[The new rules of context engineering for Claude 5](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)** (2026-07-24) — 80 % of Claude Code's system prompt deleted with no eval regression. The argument that Claude-5-class models need _fewer_ prose clauses, not more; read it before adding another exception to a rule.
- **[Steering Claude Code: CLAUDE.md, skills, hooks, rules, subagents](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more)** (2026-06-18) — the decision framework for choosing a mechanism, and four named anti-patterns.
- **[How Claude Code works in large codebases](https://claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start)** (2026-05-14) — layered CLAUDE.md, path-scoped skills, and the source of the **"review your config every three to six months"** cadence this skill's audit method now carries.
- **[Improving skill-creator](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)** (2026-03-03) — the benchmark / blind-A-B / description-tuning modes of the vendored skill.
- **[Best practices](https://code.claude.com/docs/en/best-practices)** — permissions, verification loops, named failure patterns. Its CLAUDE.md advice is **qualitative**; the 200-line number is on the memory page, not here.

## Upstream source

- **[anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/skill-creator)** — the source of the vendored `skill-creator`. The deltas to re-apply are listed in that skill's `references/project-conventions.md`.
- **[anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)** — the official marketplace. **Prefer `plugins/skill-creator/skills/skill-creator/` as the re-vendor source**: byte-identical to `anthropics/skills` today, but the production-blessed one — the `anthropics/skills` README disclaims production use. Also home to the `claude-md-management` plugin's 100-point CLAUDE.md rubric.
- **[Claude Code changelog](https://code.claude.com/docs/en/changelog)** — track for skill and sub-agent runtime behaviour changes. Read the raw file: page summarisers have returned wrong dates for it.

## How to use this list

1. "Why is the project organised like this?" — answer from here, then from the consuming
   project's own record (`.claude/audit/decisions.md`). That file is the project's, not this
   skill's: if it is absent, the project has no recorded decision — do not go looking for one.
2. Before changing a convention, check whether upstream guidance moved. Doctrine that cites no source is doctrine nobody can re-verify.
3. If a URL 404s, mark it `[broken]` and find the new location before deleting it.
4. Re-verify the whole list on the official cadence — every three to six months, and after any major model release.
