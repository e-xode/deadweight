# Deadweight

[![audit](https://github.com/e-xode/deadweight/actions/workflows/audit.yml/badge.svg?branch=main)](https://github.com/e-xode/deadweight/actions/workflows/audit.yml)
[![portability: Linux, macOS, Windows](https://github.com/e-xode/deadweight/actions/workflows/portability.yml/badge.svg?branch=main)](https://github.com/e-xode/deadweight/actions/workflows/portability.yml)
[![release](https://img.shields.io/github/v/tag/e-xode/deadweight?filter=deadweight--v*&label=release)](CHANGELOG.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Your coding agent ignores part of its configuration, and it doesn't tell you.

A deny rule that is never checked. A sub-agent that never loads. A Cursor rule that Cursor skips. A
`CLAUDE.md` that grows on every turn while half of it points at files that are gone. Claude Code,
Copilot and Cursor accept all of these without an error. Deadweight reads the configuration of a
repository and lists what the agents ignore, with the reason and the fix.

## What it finds

Three files that look fine, from a real run:

```
=== ERROR (1) ===
  [08-agent-frontmatter] Agent 'reviewer' missing required keys: name

=== WARN (2) ===
  [55-cursor-rule-ignored] '.cursor/rules/style.md' is a plain .md in .cursor/rules/: "ignored by
      the rules system because it has no frontmatter" (Cursor rules). Rename it .mdc with a
      frontmatter, or move it to AGENTS.md.
  [42-permissions-rule] deny rule 'Bash(git:* push --force)' in 'settings.json': `:*` is recognised
      only at the end of a pattern; here the colon is literal and the rule matches nothing it seems
      to (permissions).
```

- The `reviewer` agent is dropped at load. Calling it gives "Agent type not found", nothing else.
- Cursor never applies the style rule.
- The deny rule blocks nothing: `git push --force` runs as if the rule did not exist.

## Install

Claude Code:

```bash
claude plugin marketplace add e-xode/deadweight --scope project
claude plugin install deadweight@e-xode --scope project
```

GitHub Copilot CLI:

```bash
copilot plugin marketplace add e-xode/deadweight
copilot plugin install deadweight@e-xode
```

Then open a new session in the project. Requires `python3` 3.9 or later, nothing else: no pip, no
Node, no network.

With Claude Code, `--scope project` records the plugin in the project's settings, so everyone who
clones the repository gets it. Leave it out to install it for yourself only. Copilot CLI installs
plugins for your user, in every project.

## Use

- In Claude Code the audit runs in the background when a session opens. It prints nothing into
  the conversation.
- Ask "run deadweight" to see the findings for this project, errors first.
- Ask "check my agent configuration" for a review: the auditor explains each finding and its fix.
- Run `deadweight --setup-statusline` once to see the count in your status line.

All commands and options: [All commands](#all-commands).

## What it checks

- permission rules that never apply, settings in the wrong file, agents and skills that never load;
- hooks that never fire: unknown events, matchers that match nothing, scripts that are gone;
- dead links, and rule globs that match no file;
- text loaded on every turn that nothing uses;
- two skills close enough to steal each other's requests;
- tokens and credentials in files that every clone receives;
- Cursor, Copilot and `AGENTS.md` files placed where their tool doesn't look.

The full list is in [The checks in detail](#the-checks-in-detail).

## Maintainer

Built and maintained by Christophe Bragard at [E-XODE](https://www.e-xode.net/en/products/deadweight),
who audits coding agent configurations and sets up coding agents for teams. To talk about yours:
[e-xode.net/en/contact](https://www.e-xode.net/en/contact).

---

# How it works

Everything below is for those who want the detail. None of it is needed to use the plugin.

## Two layers: rules, then a model

The audit itself is deterministic. It parses files and compares them to what the official
documentation of each tool says: no model, no network, the same result on every run. That is what
the status line counts.

A second layer is opt-in: `deadweight --semantic` sends the configuration to a model, through your
own session, to find what no parser sees, such as two instructions that cannot both be followed, or
one rule copied into two files that have drifted apart. Every quote it returns is checked against
the files, nothing it finds is counted, and each run has a cost. What it sends and what it is worth,
measured: [semantic layer](skills/config-auditor/references/semantic-layer.md).

## The checks in detail

Each report ends with the number of check groups it ran. Check ids are stable (see
[Check ids are a public API](#check-ids-are-a-public-api)).

| Family | What goes wrong | Examples of checks |
| --- | --- | --- |
| **What it costs** | text injected on every turn that nothing uses | `CLAUDE.md` size, always-loaded budget, skill listing budget, description length |
| **What it points at** | references to things that do not exist | dead links, dead path anchors in skills, rule globs matching no file, hooks calling missing scripts |
| **Whether it loads** | configuration Claude Code never reads | skills outside a loaded location (`40`), withheld skills nothing points at (`15`), `name` not matching its folder |
| **Whether skills compete** | two descriptions close enough to steal each other's triggers | description overlap, missing anti-triggers |
| **Whether it can be shown wrong** | claims nothing can refute | skills naming no checkable path, eval suites that cannot fail or cannot run |
| **What executes** | hooks that never fire, or fire with the wrong budget | unknown events, `if` on a non-tool event, bare `mcp__<server>` matchers, per-event timeouts |
| **What is silently ignored** | settings and permissions that look active and do nothing | keys outside their scope (most with no documented warning), allow rules naming no tool, a rule both allowed and denied |
| **What leaks** | credentials in files every clone receives | literal tokens in `.mcp.json`, credential variables read as empty, committed MCP approvals, routing `env` |
| **Plugin packaging** | a plugin that ships what does not load | components inside `.claude-plugin/`, paths without `./`, fields replacing a default directory, version drift |
| **What other agents read** | Cursor, Copilot and the `AGENTS.md` family skip misplaced files without a word, and read Claude Code's own | a `.md` in `.cursor/rules/` (only `.mdc` is read), an instructions file without the `.instructions.md` suffix, `AGENTS.override.md` that Claude Code never reads, `CLAUDE.md` lines only Claude Code can follow - Cursor applies that file to every conversation; and, still loaded but deprecated, a chat mode in `.github/chatmodes/` |

| **What a reader sees** (opt-in) | two instructions that cannot both be followed; one rule copied into two files that drift apart | `scripts/semantic.py` asks a model, through your Claude Code session, with every quote checked and nothing counted ([what it is worth, measured, and what it sends](skills/config-auditor/references/semantic-layer.md)) |
| **What actually loads** (opt-in) | a rule or a nested `CLAUDE.md` that no session needed; a `paths:` the harness did not honour | `--runtime <log>` reads an `InstructionsLoaded` hook log you record yourself ([how](skills/config-auditor/references/runtime-data.md)) |

It recognises the container before judging it: a **project** (`.claude/`), a **plugin** (manifest,
or `skills/` at the root without one), a **marketplace**, a **library** of skills kept at the root,
or **none** — a repository with no Claude Code configuration, which gets no finding rather than
"CLAUDE.md not found". A repository whose only configuration is a root `.mcp.json` is a project.

## All commands

| You want | Do |
| --- | --- |
| Claude to review the configuration | ask for it — the `deadweight:config-auditor` skill loads when the task is about configuration |
| the findings for this project | ask Claude to run `deadweight`, or run it yourself (see below) |
| errors only | `deadweight --errors` |
| the measurements too (INFO) | `deadweight --info` |
| to measure again after editing | `deadweight --fresh` — measures, updates the status line, shows the result |
| the raw report | `deadweight --json` |
| contradictions and duplicates a model reads (sends the files, costs per run) | `deadweight --semantic`; `deadweight --both` for the findings then this |
| what your account, plugins, mods and MCP servers add to every session, beyond the project | `deadweight --environment` (estimate from file sizes); `--measure` adds a measurement (four `claude -p` runs on Haiku, a few cents; runs the project's hooks, MCP servers and mods) — see below |
| the counts in your status line | `deadweight --setup-statusline` from the project's root — Claude Code, Copilot CLI or both — then a new session |
| to stop the configuration from getting worse | `--set-floor` once, `--check-floor` in CI — see [The ratchet](#the-ratchet) |
| to turn it off in one project | `claude plugin disable deadweight --scope project` |

`deadweight` is on the Bash tool's `PATH` while the plugin is enabled, so Claude can run it. To run
it from your own shell, define it once:

```bash
# ~/.bashrc or ~/.zshrc
deadweight() {
  local p
  p=$(claude plugin list --json | python3 -c 'import json,sys
rows=[r for r in json.load(sys.stdin) if r["id"].startswith("deadweight@")]
print(sorted(rows, key=lambda r: r["version"])[-1]["installPath"])')
  python3 "$p/bin/deadweight" "$@"
}
```

### What your environment adds: `deadweight --environment`

The audit counts what the repository loads. A session also loads your account's skills (synced ones
included), the plugins you enabled and the MCP servers you connected — the same in every project, and
different on every machine. `deadweight --environment` reports them by origin (project, account,
plugins, MCP): how many skills, agents and servers, how many characters of description, and a rough
token estimate (characters / 2.85, measured on this plugin's own text). It is information, not a
finding: nothing is counted, nothing reaches a floor, the auditor's sha does not change.

It reads files only, and refuses to open the credentials file and `~/.claude.json` — by name, by the
real path a symbolic link resolves to, and by file identity (a hard link) — so MCP servers added with
`claude mcp add` are not counted (it says so). A copy of their content under another name is not
detected. Mods are listed with the events they listen to
and sorted, from a static reading of their source (nothing is run), into what they may do: add to the
model's context, only draw, block or change a tool call, reach files, processes or the network, wait
outside a hook's time limit, or "unclassified" when the reading cannot conclude; their time and token
cost is not measured. `--measure` adds a measurement below the estimate: four `claude -p` runs on Haiku
(a few cents, your own login; one run per condition, so noisy), and prints what the project, your
settings and MCP add. **It is opening a Claude Code session in that folder without the workspace
trust dialog**: the hooks of the project's settings run, the servers of its `.mcp.json` connect and
the mods of your enabled plugins load ("Without `--bare`, a `-p` session runs the hooks in a project's
`.claude/settings.json` and connects the servers in its `.mcp.json`, even in a folder you've never
trusted", headless docs). It asks on the terminal, saying how many of each will run, or needs `--yes`
(always with `--json`). Use it on a folder you trust. Another model: `environment.py --model`, run
directly.
Details: [references/environment.md](skills/config-auditor/references/environment.md).

### Four severities, and which ones are counted

| Severity | Means | Status line | Floor | Report |
| --- | --- | --- | --- | --- |
| ERROR | the harness rejects the thing, or ignores it without a word | `2E` | counted | always |
| WARN | a probable defect | `19W` | counted | always |
| NOTICE | names a file, is not a defect: a house convention, what the repository cannot prove | `4n` | not counted | always |
| INFO | a measurement every run emits: layout, budget, coverage | — | not counted | on request |

A notice does not move the floor, and it is never left out of a report: "0 errors, 0 warnings" is
not the whole answer while notices exist. INFO never reaches zero, so no counter shows it; Claude
gives its count and offers to show the lines, and `deadweight --info` prints them.

### Reading the status line

Run `deadweight --setup-statusline` from the root of the project. It installs into every host it
finds on the machine, because the two keep the setting at different levels:

| Host | Where the line is set | Covers |
| --- | --- | --- |
| Claude Code | `.claude/statusline.py`, and `statusLine` in the project's `.claude/settings.json` | this project |
| Copilot CLI | `~/.copilot/deadweight-statusline.py`, and `statusLine` in `~/.copilot/settings.json` | every project: a repository's `.github/copilot/settings.json` ignores the key |

A plugin cannot ship a `statusLine` itself, in either host, so this one command is the shortest
honest path. The line shows up on the next session.

The file it writes is a launcher, not the status line: it finds the plugin installed for the
project and runs its template, so an update reaches the line at the next session without running
the setup again. Until 0.13.1 it was a copy, and a copy stays at the version it was taken from —
run the setup once more to replace one.

**Already have a status line?** The setup leaves it untouched. Add the audit to it instead: load
`skills/config-auditor/templates/statusline.py` from the plugin's install path and call
`segment(project_dir)`, which returns the segment as a string, or `""` where no audit has run. The
install path is the `installPath` of the plugin's entry in `~/.claude/plugins/installed_plugins.json`;
`deadweight --where` prints it. Copying the template instead works until the next release.

| Shown | Means | Do |
| --- | --- | --- |
| `deadweight 19W` dim | at the floor — the accepted state | nothing |
| `deadweight 15W ▼ floor 0/19` green | below the floor | re-set the floor to lock the gain |
| `deadweight 2E 19W` yellow | errors, even under the floor | `deadweight --errors` |
| `deadweight 2E 25W ▲ floor 0/19` red | above the floor — a regression | `deadweight` |
| `deadweight 4n` dim | no error or warning, four notices | `deadweight` — each names a file |
| `deadweight ✓` | no error, warning or notice | nothing |
| `↻` | the number is not comparable: the configuration changed since it was measured, or the floor was set by another auditor | `deadweight` says which, and what clears it |
| `↑0.9.0` | a newer release is known | `claude plugin update deadweight@e-xode`, then a new session |

**Colour encodes what needs an action, not the size of the count.** A repository at its floor has
nothing to do, so it is dim — a signal that is always on teaches the eye to skip it. Zero counts
are not shown, and the version appears only when it differs from the newest one known: on its own
a version names a state, and a difference names an action.

`↻` carries no remedy on purpose. The line compares two auditor fingerprints and cannot tell which
one is older; when the floor is the older side, measuring again changes nothing. `deadweight`
knows, and says either `deadweight --fresh` or `--set-floor`.

Everything is read from files on disk — the cached measurement, Claude Code's own record of
installed plugins and the local copy of the marketplace. The status line never measures and never
touches the network: it re-runs on every message, and a script still running when the next update
arrives is cancelled.

### Running the audit directly

```bash
PLUGIN=$(deadweight --where)                                          # the plugin's root
python3 "$PLUGIN/skills/config-auditor/scripts/audit.py" --root .          # text
python3 "$PLUGIN/skills/config-auditor/scripts/audit.py" --root . --json   # JSON
```

## Per-project exceptions

One file, in **your** project, never in the plugin:

```jsonc
// .claude/audit.local.json
{
  "exemptions": [
    {
      "check": "11-english-only",
      "path": "translate/references/glossary.md",
      "reason": "a glossary of source-language terms; translating it removes its subject",
      "date": "2026-09-22"
    },
    {
      "check": "22-rule-glob-match",
      "path": ".claude/rules/admin-api-guard.md",
      "reason": "guards a route that ships next quarter; the rule lands before the code",
      "date": "2026-09-22",
      "severity": "NOTICE"        // downgrade instead of erase - the finding stays visible
    }
  ],
  "thresholds": {
    "CLAUDE_MD_MAX_BYTES": { "value": 14000, "reason": "bilingual repo", "date": "2026-09-22" }
  }
}
```

**House conventions.** Some checks encode this plugin's own conventions rather than Anthropic's
documentation — each is listed, with its source and its evidence, in
[`evals/CONVENTIONS.md`](evals/CONVENTIONS.md). By default they report as NOTICE, naming what
Anthropic documents instead. `"profile": "house"` in the overlay turns them into warnings.

`reason` and `date` are required: an exemption without a reason is a decision nobody can review,
and one without a date is a decision nobody can age out. An exemption that no longer excuses anything is reported
(`31-overlay-unused`, NOTICE): after an update that fixed a false positive, drop it, or it will hide
the next real finding of that check under that path. `severity` is optional and accepts only
`WARN`, `NOTICE` or `INFO` — the finding stays in the report, marked `[excused by overlay]`, at a level that
does not fail CI. Prefer it to erasing: an erased finding is one `--check-floor` can no longer
watch grow.

An exemption may not silence the checks that audit the overlay, nor the ratchet itself
(`31-*`, `34-floor`, `00-layout`; the old id `34-audit-sha` is an alias of `34-floor`). A release valve able to disconnect its own pressure gauge
is not a valve.

### Thresholds: which ones a project may move

| Family | Examples | Overridable |
| --- | --- | --- |
| **Mechanism** — imposed by the harness | the 1,024-char spec cap on `description`, the 1,536 listing cutoff, the context window | **No.** Moving the number changes what the audit says, not what the harness does |
| **Doctrine** — uniform by choice | `CLAUDE_MD_MAX_BYTES`, the always-loaded budget, the overlap threshold, eval coverage | **Yes**, with a reason and a date |
| **Derived** — computed from the project's own settings | the listing ceiling, from `skillListingBudgetFraction` | Already the project's |

Every applied override prints itself on every run, so a doctrine is never rewritten quietly.

---

## The ratchet

```bash
python3 skills/config-auditor/scripts/audit.py --root . --set-floor    # freeze today's counts
python3 skills/config-auditor/scripts/audit.py --root . --check-floor  # fail if they rose
```

A measurement with no floor is one people learn to ignore: the numbers move, nobody owns the
direction, and a year later every step looked reasonable. The floor is the number the configuration
may not rise above. Commit `.claude/audit/floor.json` — a ratchet nobody else can see is a private
opinion — and let its git history be the run history, each move with a commit message saying why.

The floor records the **fingerprint of the auditor** — `audit.py` and every module of its package
`deadweight_audit/` — and `--check-floor` refuses to compare across two of them. A count taken with a different auditor is not a better or worse state — it is a
different measurement, and comparing the two silently is how a change of instrument gets read as
progress. The refusal is a warning, not a failure, so it does not break CI; it prints both counts
side by side and asks you to re-set deliberately. With the same auditor, a check id at ERROR or
WARN that the floor did not record is named in a `34-floor` warning even when the counts did not
rise; that warning does not fail CI either.

This repository runs its own ratchet in CI (`.github/workflows/audit.yml`): a repository that ships
an auditor and does not run it on itself has the exact defect it exists to catch.

## Versions and your floor

| Release | The auditor | Your floor |
| --- | --- | --- |
| **patch** (`0.9.x`) | unchanged | still valid |
| **minor** (`0.x.0`) | may have changed | re-set it after reading both counts |

While the plugin is `0.x`, a minor release is the breaking one. Even a fix that removes a false
positive changes the counts, so it ships as a minor. The CHANGELOG opens with a warning whenever
the auditor changed.

**After a minor update**, in this order:

1. Open a new session (a plugin loads at session start), then run `--check-floor`. No
   `34-floor` warning means the auditor did not change: nothing else to do.
2. Compare the floor's `warning_ids` with the new run's: gone ids are the auditor's fixes, new ids
   are what to read. Read every ERROR.
3. `--set-floor` on the configuration as it is, and commit `floor.json` alone — the commit records a
   change of instrument, not an improvement.
4. Fix, or exempt with a reason; drop the exemptions reported unused; `--set-floor` again, committed
   with the fixes. Two commits keep `git log -p .claude/audit/floor.json` able to tell the
   auditor's changes from yours.

`--set-floor` writes whatever this run measured, higher or lower, without asking: the commit is
where the judgement goes. `--fresh` only re-measures for the status line; it touches neither the
floor nor the overlay.

## Two channels, two prices

The `SessionStart` hook runs the audit and caches the result in
`${XDG_CACHE_HOME:-~/.cache}/claude-audit/`, **outside** the repository. It prints **nothing**.

That silence rests on a measurement: a plugin hook's stdout **enters the model's context** — a
probe plugin printing marker lines had them read back verbatim by a fresh session. Whatever a hook
prints is paid for in every session of every project that installs the plugin.

| Channel | Who reads it | What it costs |
| --- | --- | --- |
| Hook stdout | the model | tokens, every session, every project |
| Status line | you | nothing — it "runs locally and does not consume API tokens" |

Numbers a human glances at belong in the status line. The hook runs on `startup` and `resume` only;
opting out is per project and covers the whole plugin, not the hook alone.

## The doctrine behind the checks

The skill carries reference files — skill anatomy, sub-agent anatomy, rules, `CLAUDE.md`, runtime
mechanisms, anti-patterns, the audit checklist, and a curated list of official sources. Most of
these rules are not obvious and several are documented nowhere:

- a skill `description` is capped at **1,024 characters by the Agent Skills spec**; the **1,536**
  figure is a different thing — the listing cutoff for `description` + `when_to_use` combined;
- past roughly **20 KB**, a `SKILL.md` loses its tail after the first auto-compaction, silently;
- `paths:` on a skill **withholds** it — it does not scope it;
- Claude Code finds skills **by location, not by content**: `<name>/SKILL.md` at a repository root
  loads nowhere, `skills/<name>/SKILL.md` loads as a plugin even without a manifest.

Every factual claim carries its source and the date it was verified; where a measurement was taken
rather than read, the protocol to reproduce it is given.

## What belongs to the project, not to this plugin

A plugin is the same bytes in every project that installs it, so it holds no project's state:

| What | Where | Written by |
| --- | --- | --- |
| Exemptions and threshold overrides, each with reason and date | `.claude/audit.local.json` | you |
| Decisions that attach to no single check | `.claude/audit/decisions.md` | you |
| What the audit reported over time | the git history of `.claude/audit/floor.json` | you, each time you re-set it |

Templates are in `skills/config-auditor/templates/`. All three are optional: absent means "this
project has recorded nothing", a valid state.

## Check ids are a public API

A consuming project names check ids in its `.claude/audit.local.json`, so ids are **never renamed**.
An id that must change goes into `CHECK_ID_ALIASES` in `deadweight_audit/catalog.py`, old to new; the old id keeps
working for good, and the audit says once that a newer name exists.

## Inside the auditor

`scripts/audit.py` is the entry point every command above calls; the auditor is the package beside
it, standard library only:

```
skills/config-auditor/scripts/
  audit.py                 entry point
  deadweight_audit/
    cli.py                 arguments, the passes over a dual-role repository, output
    registry.py            which check runs on which container, and the dispatcher
    context.py             AuditContext: the state of one audit, passed to every check
    catalog.py             check inventory and id aliases (the public API above)
    report.py  layout.py  overlay.py  floor.py  identity.py  limits.py  repo.py
    parsing/               frontmatter, markdown spans and links, globs
    vocabulary/            lists copied from the documentation: tools, keys, hook events
    checks/                one module per family: skills, agents, hooks, settings, security…
  semantic.py              a separate command: never counted, outside the auditor's sha
  deadweight_semantic/     its package
```

A check is a function `check_<what>(ctx, report, ...)` in the module of its family. It reads the
repository through `ctx` (root, layout, where skills and agents live, thresholds) and adds findings
to `report`; it never keeps state of its own, so two audits in one process cannot leak into each
other. To add one: write it, call it from `registry.run_checks`, name its containers in the
registry's lists if it does not apply everywhere, and add its line to `catalog.CHECKS`.

```bash
python3 -m unittest discover -s tests    # labelled cases + the auditor's assumptions about itself
```

`tests/cases.json` holds fictional repositories with the exact findings each must produce, checked
by hand; most began as a false positive on a real repository. It is generated from the maintainer's
labelled source — to propose a case, describe the repository and the verdict in an issue or a PR.
A published case checks the current auditor's counts; it does not prove the case discriminates.
That proof — the case fails on the version that had the defect — is run outside the plugin before
each release, because the earlier auditors it needs are kept outside the plugin by design.

## Where the examples come from

The examples describe one fictional online shop whose skills are named `shop-*`, `ui-*`, `api-*`
and `data-*` — deliberately not `foo`/`bar`, because a model learns from the *shape* of an example.
The measurements are real, taken on a private fleet and on public repositories, each dated. Only the
names are not. The status line image is generated from the real template on that fictional project
by `docs/render_statusline.py`.

## Install: details and special cases

The two identifiers read alike and are not the same thing. `e-xode/deadweight` is the
**repository**, in the `owner/repo` shorthand that `marketplace add` reads as GitHub; the full URL
`https://github.com/e-xode/deadweight` works too, and is recorded as a different kind of source.
`deadweight@e-xode` is the **plugin**: `deadweight`, from the marketplace named `e-xode`.
`plugin install e-xode/deadweight` fails - it is not a plugin name.

`--scope project` on **both** writes the marketplace and the plugin into the project's
`.claude/settings.json`, so anyone who clones the repository gets them too — the plugin alone would
name a marketplace their machine does not know. Leave both out to install it for yourself only, in
every project.

A project that already declares the marketplace in its settings needs no `marketplace add`. If you
run one anyway, spell the source the way the settings do: a name declared with `e-xode/deadweight`
refuses `https://github.com/e-xode/deadweight` - *"its network source differs from the one declared
for it in settings"* - because the two spellings are two sources to Claude Code, even though they
reach the same repository.

**Installed before 0.16.0?** The marketplace was called `deadweight` then, and your copy keeps that
name: a marketplace is named on your machine when you add it, and renaming it upstream renames
nothing downstream. `deadweight@deadweight` goes on working and updating. To move to the new name,
replace `deadweight@deadweight` and the `extraKnownMarketplaces.deadweight` key with
`deadweight@e-xode` and `e-xode` in the project's `.claude/settings.json`, then, in this order:

```bash
claude plugin marketplace remove deadweight      # first: the same source cannot be added under a second name
claude plugin marketplace add e-xode/deadweight
claude plugin install deadweight@e-xode --scope project
```

**Then open a new session in that project.** Plugins are read when a session starts: on the first
one after installing, the skill is loaded and the audit runs silently in the background.

**Check that it is active:** in that new session, ask Claude to run `deadweight`. It prints this
project's findings. (`claude plugin list` shows the installs of every project on the machine, not
only this one.)

## Status

Pre-1.0. The doctrine comes from one private fleet, and has since been measured against samples
of public repositories the auditor had never seen — each drawn after the previous one, so they could
not overlap. Each sample found defects in the auditor itself, recorded in the CHANGELOG. Issues and
counter-examples are the point.

## License

MIT.
