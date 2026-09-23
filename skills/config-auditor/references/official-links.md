<!-- The worked examples in these references (skill names like `shop-ssr`, `api-socket`,
     `ui-scss`) describe one fictional project: an online shop, Node SSR, with a
     design system, a socket API and a content team. It is invented, and it is
     deliberately not `foo`/`bar`: a model learns from the SHAPE of an example. -->

# Official Anthropic documentation

Contents: [How to read this list](#how-to-read-this-list) · [Agent Skills](#agent-skills-the-spec) · [Claude Code — configuration](#claude-code--configuration) · [Claude Code — execution surfaces](#claude-code--execution-surfaces) · [Claude Code — plugins](#claude-code--plugins) · [Measurement and diagnostics](#measurement-and-diagnostics) · [Orchestration](#orchestration) · [Engineering posts](#engineering-posts) · [Upstream source](#upstream-source)

Verified against the docs on 2026-09-23 (Claude Code 2.1.280): every URL below answered 200,
and each description was checked against the page's raw Markdown.

## How to read this list

- **Read the raw page.** Every `code.claude.com/docs/en/<page>` has a Markdown twin at
  `<page>.md`. A summarising fetch paraphrases, and a paraphrase cannot be diffed: an earlier
  version of this list quoted a telemetry event that no page contained.
- **Two hosts.** `platform.claude.com` documents **Agent Skills**, the runtime-independent spec
  and the claude.ai / API constraints; `code.claude.com` documents **Claude Code**, which
  implements it and adds mechanisms of its own. Older `docs.anthropic.com` links redirect.
- **Vocabulary pages are the ones that rot.** Tools, frontmatter fields, hook events, settings
  keys and model aliases are listed in `audit.py`; every addition upstream becomes a false
  positive downstream until the list is updated. Re-check them before every release.

## Agent Skills (the spec)

- **[Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)** — three-level progressive disclosure; auditing third-party skills before use.
- **[Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)** — 64-char name, 1,024-char description, third person, no XML tags, reserved words `anthropic` / `claude` in `name` (claude.ai and the API), one level of references, a table of contents past 100 lines, "build evaluations first", at least three.
- **[AgentSkills.io](https://agentskills.io)** · **[the specification](https://agentskills.io/specification)** — the open standard and its six portable fields; no reserved words at this level.

## Claude Code — configuration

- **[Memory and CLAUDE.md](https://code.claude.com/docs/en/memory)** — `./CLAUDE.md` or `./.claude/CLAUDE.md`; ancestors, subdirectories on demand, `CLAUDE.local.md`, `AGENTS.md`; `@` imports (four hops); up to 4 MiB loaded, larger skipped; "under 200 lines"; auto memory; `.claude/rules/` with `paths:`, triggered on **read**.
- **[Explore the context window](https://code.claude.com/docs/en/context-window)** — what survives compaction: CLAUDE.md and unscoped rules re-injected, path-scoped rules and subdirectory CLAUDE.md summarised away, 5,000 tokens per skill / 25,000 combined re-attached.
- **[Skills](https://code.claude.com/docs/en/skills)** — locations and precedence, twenty frontmatter fields, `skillOverrides` (including bundled skills), `paths:`, `context: fork`, substitutions, the listing budget and its least-invoked-first degradation, command files.
- **[Sub-agents](https://code.claude.com/docs/en/sub-agents)** — eighteen frontmatter fields, `permissionMode` values, model resolution, foreground and background, the `Agent(<type>)` restriction (main-thread only), `Task` as an alias.
- **[Tools reference](https://code.claude.com/docs/en/tools-reference)** — the tool vocabulary: every name valid in `tools`, `allowed-tools` and permission rules.
- **[Settings](https://code.claude.com/docs/en/settings)** · **[Settings reference](https://code.claude.com/docs/en/settings-reference)** — files and precedence; the **Scope** column, which says which file each of the 231 keys may be set in. A key outside its scope is ignored without a word.
- **[Permissions](https://code.claude.com/docs/en/permissions)** · **[Permission modes](https://code.claude.com/docs/en/permission-modes)** — deny, then ask, then allow; rule syntax per tool; allow rules skipped silently; modes that do not apply from project files.
- **[Monorepos and large repos](https://code.claude.com/docs/en/large-codebases)** — layered CLAUDE.md, `claudeMdExcludes`, path-scoped skills, review after a major model release.
- **[The .claude directory](https://code.claude.com/docs/en/claude-directory)** · **[Environment variables](https://code.claude.com/docs/en/env-vars)** — where each file lives; variables that change loading.

## Claude Code — execution surfaces

- **[Hooks](https://code.claude.com/docs/en/hooks)** · **[Hooks guide](https://code.claude.com/docs/en/hooks-guide)** — thirty-three events, five handler types and their fields, `if` (tool events only), matchers (`mcp__<server>__.*`), timeouts per event, exit codes, stdout that enters the context, hooks in skill and agent frontmatter.
- **[MCP](https://code.claude.com/docs/en/mcp)** · **[Managed MCP](https://code.claude.com/docs/en/managed-mcp)** — scopes, transports, `${VAR}` expansion, credential variables read as empty, project approvals and workspace trust.
- **[Output styles](https://code.claude.com/docs/en/output-styles)** — built-ins, exact-match names (a case mismatch gives Default), frontmatter fields.
- **[Status line](https://code.claude.com/docs/en/statusline)** — a local script, zero API tokens, 300 ms debounce, `refreshInterval` minimum 1.
- **[Sandboxing](https://code.claude.com/docs/en/sandboxing)** — why a Bash deny rule is not a security boundary.

## Claude Code — plugins

- **[Plugins](https://code.claude.com/docs/en/plugins)** · **[Plugins reference](https://code.claude.com/docs/en/plugins-reference)** — manifest schema, component paths (relative, `./`, never inside `.claude-plugin/`), fields that replace a default directory, agent fields ignored in a plugin, `userConfig`, `claude plugin validate [--strict]`.
- **[Plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)** · **[Plugin dependencies](https://code.claude.com/docs/en/plugin-dependencies)** — catalogue schema, reserved names, `strict`, version ranges.
- **[Plugin evals](https://code.claude.com/docs/en/plugin-evals)** — `claude plugin eval`, case layout, graders, the baseline arm.

## Measurement and diagnostics

- **[Commands](https://code.claude.com/docs/en/commands)** — `/context`, `/doctor`, `/skills`, `/skill-doctor`, `/memory`, `/hooks`.
- **[Debug your config](https://code.claude.com/docs/en/debug-your-config)** — `--safe-mode` (the no-configuration baseline arm) and `--debug`. It documents no telemetry event.
- **[Monitoring usage](https://code.claude.com/docs/en/monitoring-usage)** — OpenTelemetry: `CLAUDE_CODE_ENABLE_TELEMETRY=1`, the `claude_code.*` events, the `skill.name` attribute.
- **[Costs](https://code.claude.com/docs/en/costs)** · **[Prompt caching](https://code.claude.com/docs/en/prompt-caching)** · **[Headless](https://code.claude.com/docs/en/headless)** — what a turn costs; `claude -p` and its `stream-json` init event, which lists the skills and plugins a session actually loaded.

## Orchestration

- **[Agent teams](https://code.claude.com/docs/en/agent-teams)** — experimental; a teammate ignores `skills:` but loads project and user skills.
- **[Dynamic workflows](https://code.claude.com/docs/en/workflows)** — the Workflow tool and its caps.

## Engineering posts

- **[Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)** — orchestrator-workers, parallelisation, when a workflow beats an agent.
- **[Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)** — context as a finite budget.
- **[The new rules of context engineering for Claude 5](https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)** — over 80 % of Claude Code's system prompt removed with no eval regression: fewer prose clauses, not more.
- **[How Claude Code works in large codebases](https://claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start)** — the "review every three to six months" cadence.
- **[Improving skill-creator](https://claude.com/blog/improving-skill-creator-test-measure-and-refine-agent-skills)** — benchmark and description-tuning modes; a skill the base model passes without is a skill to retire.
- **[Best practices](https://code.claude.com/docs/en/best-practices)** — verification loops, the "would removing this cause mistakes?" test for CLAUDE.md.

## Upstream source

- **[anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/skill-creator)** — `skill-creator` and its `quick_validate.py`.
- **[anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)** — the official marketplace.
- **[Claude Code changelog](https://code.claude.com/docs/en/changelog)** — runtime behaviour changes; read the raw file.
