# Deadweight

**Audit the Claude Code configuration of a project.** One skill, one Python script, no
dependencies, no network.

Deadweight is configuration you carry that does nothing. It does nothing in three ways, and only
the first is about tokens.

**It costs and returns nothing.** Every skill description is injected into the model's context on
every single turn, used or not. So is `CLAUDE.md`. So is every sub-agent description. A
configuration that grows for six months without anyone measuring it spends thousands of characters
per turn on instructions nothing reads.

**It points at nothing.** A rule whose `paths:` glob matches no file never loads. A hook whose
script was deleted still sits in your settings. A reference links to a file that is not there, and
where a human shrugs, a model goes looking — bounded cost for one, unbounded for the other. Two
descriptions close enough to steal each other's triggers are a defect neither file can show you.

**It cannot be shown wrong.** A skill that names no checkable path can only be trusted, never
refuted. A suite of evals nothing can execute is not a suite. A count with no floor is a number
people learn to scroll past.

Of the 36 check groups here, 11 are about what the configuration costs. The other 25 are about
whether it does anything at all.

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
      "severity": "INFO"          // downgrade instead of erase - the count stays visible
    }
  ],
  "thresholds": {
    "CLAUDE_MD_MAX_BYTES": { "value": 14000, "reason": "bilingual repo", "date": "2026-09-22" }
  }
}
```

`reason` and `date` are required: an exemption without a reason is a decision nobody can review,
and one without a date is a decision nobody can age out. `severity` is optional and accepts only
`WARN` or `INFO` — with it the finding stays in the report, marked `[excused by overlay]`, at a
level that does not fail CI; without it the finding is dropped outright. Prefer the downgrade:
an erased finding is one `--check-floor` can no longer watch grow.

An exemption may not silence the checks that audit the overlay, nor the ratchet itself
(`31-*`, `34-audit-sha`, `00-layout`). A release valve able to disconnect its own pressure gauge
is not a valve.

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
| What the audit reported, run by run | the git history of `.claude/audit/floor.json` | you, each time you re-set it |

Templates for the first two are in `skills/config-auditor/templates/`. All three are optional:
absent means "this project has recorded nothing", which is a valid state, not a missing file.

### A project may hold its own number — for a doctrine threshold only

```json
{ "thresholds": {
    "CLAUDE_MD_MAX_BYTES": {
      "value": 13312,
      "reason": "Ops repository: CLAUDE.md is hard rules end to end, every procedure already lives in its own skill.",
      "date": "2026-09-22" } } }
```

Thresholds come in three families, and treating them alike would be the mistake.

| Family | Examples | Overridable |
| --- | --- | --- |
| **Mechanism** — imposed by the harness | the 1,024-char spec cap on `description`, the 1,536 listing cutoff, the compaction slice, the context window | **No.** The override is refused as an error, naming why: moving the number changes what the audit says, not what the harness does |
| **Doctrine** — uniform by choice | `CLAUDE_MD_MAX_BYTES`, the always-loaded budget, reference length, the overlap threshold, eval coverage | **Yes**, with a reason and a date |
| **Derived** — computed from the project's own settings | the listing ceiling, from `skillListingBudgetFraction` | Already the project's |

Every applied override prints itself on every run:

```
[31-overlay-threshold] `CLAUDE_MD_MAX_BYTES` 12288 -> 13312, on this project's
authority (2026-09-22): Ops repository, CLAUDE.md is hard rules end to end.
```

An override nobody sees is a doctrine quietly rewritten. One that announces itself is a decision
anyone can re-open — including the person who made it, six months later.

An exemption without a `reason` is a decision nobody can review; without a `date`, one nobody can
age out. A bare list of exempt paths is amnesia — six months on nobody dares remove an entry, so the
list only ever grows. Check 31 enforces the shape, and flags an exemption whose path no longer
exists: a stale exemption is a dead anchor in the overlay.

## Two channels, two prices

The plugin ships a `SessionStart` hook (`hooks/session-audit.sh`). It runs the audit against the
consuming project and caches the result outside the repository. It prints **nothing**.

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
untracked file in every repository, forever; a measurement is not configuration.

**There is no run-history file.** An earlier version appended one line per run to
`.claude/audit/history.jsonl`. It has been removed: `git log -p .claude/audit/floor.json` is the
same trajectory, timestamped to the second, with an author and a commit message saying **why** the
floor moved. The floor now carries the check ids behind its counts — the only thing the series held
that it did not. The measure belongs to the script, the judgement to the commit message.

Commit `.claude/audit/floor.json` — a ratchet nobody else can see is a private opinion.

**A release only invalidates your floor when it changes the auditor.** The floor records the sha of
`audit.py`, not the plugin version: of the first seven releases of this plugin, two touched
`audit.py` and five did not. When one does, check 34 refuses to compare, prints both counts side by
side, and asks you to re-set deliberately.

Numbers a human glances at belong in the status line, and installing it is one command:

```bash
deadweight --setup-statusline
```

It prints `deadweight 0E 19W`, and two rules govern it.

**Colour encodes what needs an action, not the size of the count.** A repository sitting exactly at
its floor is in the accepted state — there is nothing to do — so it is dim, not yellow. A signal
that is always on teaches the eye to skip it.

| | |
| --- | --- |
| dim | at the floor: the accepted state |
| green | below the floor: `deadweight 0E 15W ▼ floor 0/19` |
| yellow | errors, even under the floor — an error is always worth seeing |
| red | above the floor: `deadweight 2E 25W ▲ floor 0/19`, the only urgent case |
| dim | superseded auditor, or a measurement the configuration has outlived |

**Freshness is measured, not guessed from age.** The audit runs once at session start, so the number
is frozen while looking live: fix five warnings and it still shows the old count. An earlier version
flagged the *age* past a threshold, but age is a proxy — a three-day-old measurement in a repository
nobody touched is still true, a two-minute-old one in a repository you just edited is already false.
So the segment compares the measurement against the newest mtime of the configuration itself, about
6 ms over 500 files against a 300 ms debounce, and says `(config changed since, run deadweight
--fresh)` when it matters.

The plugin's name leads the segment and doubles as the command that shows the detail.


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

So `.claude/audit/floor.json` **in this repository is this plugin's own floor**, not something a
consuming project receives — you set yours, in your own repository. And a floor is not a log: it
is one value, replaced only when a human runs `--set-floor`, with the reason in the commit
message. That is why it is committed while a run history is not.

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
