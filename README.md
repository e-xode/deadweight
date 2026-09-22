# Deadweight

**Audit the Claude Code configuration of a project.** One skill, one Python script, no
dependencies, no network.

Every skill description you write is injected into the model's context **on every single turn**,
whether the skill is used or not. So is `CLAUDE.md`. So is every sub-agent description. A
configuration that grows for six months without anyone measuring it ends up spending thousands of
characters per turn on instructions nothing reads.

That is the deadweight. This plugin measures it.

## What it checks

35 groups of mechanical checks over `CLAUDE.md` and everything under `.claude/`. The script
prints the count it actually ran; that line is the inventory, not this one:

| Surface | Examples of what is checked |
| --- | --- |
| `CLAUDE.md` | size and line count, code comments outside fences, agents listed, skills index |
| Skills | frontmatter validity, name matches folder, description length against the **1,024-char spec cap**, anti-trigger clause, `SKILL.md` against the ~20 KB compaction slice, broken relative links, orphan references, twin-skill division tables |
| References | size, table of contents past 100 lines, reachability from `SKILL.md` |
| Sub-agents | frontmatter fields, tool names that actually exist, description budget, cross-references with `CLAUDE.md` |
| Rules | size, `paths:` globs that match no file — a rule that never loads |
| Settings | scope semantics, including keys that are silently ignored at project scope |
| Evals | schema and coverage |
| Hooks | event names that exist, commands whose script is there, missing timeouts, `${CLAUDE_PLUGIN_ROOT}` in a project hook, and which hooks put their stdout in the model's context |
| **Budget** | the always-loaded total, and the listing ceiling **derived from this project's own `skillListingBudgetFraction`** |

It reports `OK` / `INFO` / `WARN` / `ERROR` and exits 1 on any error.

## Install

The marketplace and the plugin are both called `deadweight`, hence `deadweight@deadweight`.

```bash
claude plugin marketplace add e-xode/deadweight
claude plugin install deadweight@deadweight
```

That is the whole installation. Add `--scope project` to both commands to declare it in the
project's `.claude/settings.json` instead of your user settings, so a clone gets it too.

**Requirements: `python3` (3.9+, standard library only).** Nothing else — no `jq`, no Node, no pip
install. If `python3` runs, the plugin runs.

### What works immediately, with no further setup

| | |
| --- | --- |
| `SessionStart` hook | audits the project when a session opens, and **prints nothing** — see [Two channels](#two-channels-two-prices) |
| skill `deadweight:config-auditor` | Claude loads it when the task is about configuration |
| command `deadweight` | on the Bash tool's `PATH`: ask Claude for the audit detail and it runs this |

Check it: open a session in any project and ask Claude to run `deadweight`.

### Status line — one command

```bash
deadweight --setup-statusline
```

It writes `.claude/statusline.py` and sets `statusLine` in the project's `.claude/settings.json`.
It refuses to overwrite a `statusLine` you already have, and tells you where the segment is so you
can splice it into yours. The line appears on the next session:

```
audit 0E 27W · 4m ago · deadweight
```

A plugin cannot ship a `statusLine` itself — a plugin's own `settings.json` only honours `agent`
and `subagentStatusLine` — so this one command is the shortest honest path.

Ask Claude to run it, or call it from your own shell after defining it once:

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

### Running the audit directly

```bash
deadweight --fresh            # audit this project now, human-readable
deadweight --fresh --json     # same, as JSON (adds layout and audit_sha)
deadweight --where            # the plugin's root, if you want the script path
```

## Per-project exceptions

One file, in **your** project, never in the plugin:

```jsonc
// .claude/audit.local.json
{
  "english_only_exempt": [
    "translate/references/glossary.md"
  ]
}
```

Shared logic and thresholds, locally declared exceptions. That seam is the whole point: a project
that needs a real exception declares it, instead of forking the auditor.

## The doctrine behind the checks

The skill carries eight reference files — skill anatomy, sub-agent anatomy, rules, `CLAUDE.md`,
runtime mechanisms, anti-patterns, the audit checklist, and a curated list of official sources.
They exist because most of these rules are not obvious and several are not documented anywhere:

- a skill `description` is capped at **1,024 characters by the Agent Skills spec**, while the
  **1,536** figure is a different thing — the listing cutoff for `description` + `when_to_use`
  combined. Authoring against the wrong one is a hard upload failure;
- past roughly **20 KB**, a `SKILL.md` loses its tail after the first auto-compaction, silently,
  mid-session, while the file on disk still looks intact;
- `paths:` on a skill **withholds** it — it does not scope or disambiguate it (measured twice,
  headless and interactive);
- `permissions.defaultMode` is **ignored at project scope** since Claude Code 2.1.257.

Every factual claim carries its source and the date it was verified. Where a measurement was taken
rather than read, the protocol to reproduce it is given. Where something was tried and abandoned,
the negative result is kept rather than deleted.

## Where the examples come from

The worked examples describe one fictional project — an online shop with a design system, a socket
API and a content team, whose skills are named `shop-*`, `ui-*`, `api-*` and `data-*`. It is
invented, and it is deliberately not `foo`/`bar`: a model learns from the *shape* of an example, so
a placeholder with no domain teaches nothing about naming, scoping or overlap. Where only the
structure matters, the examples use `<angle-bracket>` placeholders instead, which cannot rot into
dead references.

The measurements are real — taken on a private fleet, each with its date. Only the names are not.

## What belongs to the project, not to this plugin

A plugin is the same bytes in every project that installs it, so it can hold no project's state.
What it holds is the schema and the detector; the content lives in the consuming project:

| What | Where | Written by |
| --- | --- | --- |
| Exemptions, each with its reason and date | `.claude/audit.local.json` | you |
| Decisions that attach to no single check | `.claude/audit/decisions.md` | you |
| What the audit reported, run by run | `.claude/audit/history.jsonl` | `audit.py --record` |

Templates for the first two are in `skills/config-auditor/templates/`. All three are optional:
absent means "this project has recorded nothing", which is a valid state, not a missing file.

An exemption without a `reason` is a decision nobody can review; without a `date`, one nobody can
age out. A bare list of exempt paths is amnesia — six months on nobody dares remove an entry, so the
list only ever grows. Check 31 enforces the shape, and flags an exemption whose path no longer
exists: a stale exemption is a dead anchor in the overlay.

## Two channels, two prices

The plugin ships a `SessionStart` hook (`hooks/session-audit.sh`). It runs the audit against the
consuming project and appends one line to `.claude/audit/history.jsonl`. It prints **nothing**.

That silence is deliberate, and it rests on a measurement rather than on taste. A plugin-declared
`SessionStart` hook does fire, `${CLAUDE_PROJECT_DIR}` is defined inside it and points at the
consuming project, and **its stdout enters the model's context** — a probe plugin printing marker
lines had them read back verbatim by a fresh session. `claude plugin details` describes a hook as
`harness-only — no model context cost`: true of the *declaration*, false of the *output*. Whatever
the hook prints is paid for in every session of every project that installs the plugin.

So there are two channels, and they are not two ways of showing the same thing:

| Channel | Who reads it | What it costs |
| --- | --- | --- |
| Hook stdout | the model | tokens, every session, every project |
| Status line | you | nothing — it "runs locally and does not consume API tokens" |

The hook writes its measurement to `${XDG_CACHE_HOME:-~/.cache}/claude-audit/`, **outside** the
repository. A hook that runs at every session start and writes inside the project leaves one more
untracked file in every repository, forever; a measurement is not configuration. The series that is
worth keeping — `audit.py --record` appending to `.claude/audit/history.jsonl` — is therefore
opt-in: the hook writes it only where `.claude/audit/` already exists, which is how a project says
it wants to keep the record and commit it.

Numbers a human glances at belong in the status line, and installing it is one command:

```bash
deadweight --setup-statusline
```

It prints `audit 0E 27W · 4m ago · deadweight` — red on errors, yellow on warnings, green at zero,
dimmed once the number is a day old — and nothing at all where no audit has ever run. The template
it installs is `skills/config-auditor/templates/statusline.py`, readable and yours to edit.


### Seeing the detail behind the count

A status line that says `3W` and offers no way to see which three warnings is a number without a
referent: it can only be believed or ignored, and a number that can only be believed is not a
measurement. So the hook caches the findings alongside the counts — the audit has just run, the
detail is already in hand — and the plugin ships `bin/deadweight`, which is on the Bash tool's
`PATH` while the plugin is enabled:

```bash
deadweight            # the cached findings for this project, errors first
deadweight --errors   # errors only
deadweight --fresh    # re-run the audit now instead of reading the cache
deadweight --json     # the raw report
```

Ask Claude for the detail and it runs this; the status line names the command whenever there is
something to see. To run it from your own shell, define the function in [Install](#install) once.

Two properties of that template are load-bearing. It **does not run the audit**: the status line
re-runs on every assistant message, and an in-flight script is cancelled when the next update
arrives, so a status line that measured would be killed mid-measurement exactly when you are working
hardest. And it **always prints the age of the number**, because the audit runs once at session
start and nothing the session changes afterwards is reflected. A count shown without its age reads
as current, and a stale green light is worse than no light.

Opting out is per project: `claude plugin disable deadweight --scope project` writes
`{"enabledPlugins": {"deadweight@deadweight": false}}` into `.claude/settings.json`, and the hook
stops firing there. The granularity is the whole plugin, not the hook alone — a project cannot keep
the skill and refuse the hook.

## The ratchet

`audit.py` reports; `--set-floor` and `--check-floor` make it a ratchet.

```bash
python3 skills/config-auditor/scripts/audit.py --root . --set-floor    # freeze today's counts
python3 skills/config-auditor/scripts/audit.py --root . --check-floor  # fail if they rose
python3 skills/config-auditor/scripts/audit.py --root . --record       # append the run to history
```

A measurement with no floor is a measurement people learn to ignore: the numbers move, nobody owns
the direction, and a year later every individual step looked reasonable. The floor is the number the
configuration may not rise above.

The floor records the **sha of `audit.py`**, and `--check-floor` refuses to compare across two
different shas. A count taken with a different auditor is not a better or worse state — it is a
different measurement, and comparing the two silently is how a change of instrument gets read as
progress. Same reason the run history carries the sha on every line.

This repository runs its own ratchet in CI (`.github/workflows/audit.yml`), because a repository that
ships an auditor and does not run it on itself has the exact defect it exists to catch.

## Check ids are a public API

A consuming project names check ids in its `.claude/audit.local.json`. Renaming one would silently
turn that project's exemption inert — and the audit would then report "unknown check", which reads
as the project's fault for a rename it did not make.

So ids are **never renamed**. An id that must change is added to `CHECK_ID_ALIASES` in `audit.py`,
old → new; the old id keeps working, for good, and the audit says once that a newer name exists.
Entries are never removed. Treat the id vocabulary as a compatibility surface, not an internal
detail.

## Status

**v0.1.0 — first extraction.** The doctrine comes from a single private fleet of 19 repositories.
It has not yet been tested against anyone else's project, and the checks encode opinions that are
house doctrine rather than mechanism — those are marked as such in the reference files. Issues
and counter-examples are the point.

## License

MIT.
