# Changelog

## 0.5.0 — 2026-09-22

**This release changes `audit.py`, so a floor set with an earlier version stops comparing.**

- **Check 37 — a flag the documentation shows must exist in the script.** Removing a feature and
  leaving its documentation is the same defect as renaming a skill and leaving its mentions: the
  code is right, the reader is wrong, and nothing fails. Found by a reader, not by the audit:
  `--record` was removed in 0.3.0 and **six live references survived**, two of them inside command
  blocks someone would copy and run, and a README that contradicted itself — one section said the
  feature was gone while two others described it as present. Thirty-six checks saw none of it.
  Only flags on a line that invokes the audit script are read; the CHANGELOG is exempt, since
  naming what was removed is its job.
- The orphaned `.claude/audit/history.jsonl` is deleted and ignored, and its six mentions are
  rewritten to point at the git history of the committed floor.
- The README now says plainly that `.claude/audit/floor.json` **in this repository** is this
  plugin's own floor, not something a consuming project receives — and that a floor is one value a
  human replaces, which is why it is committed while a run history is not. The author of this
  plugin misread it; a stranger would too.
- `evals/README.md` records how to run the suite (`--allow-tools Bash` is not optional) and that
  `max_turns` and `allowed_tools` are the author's choices, not measurements: a first run had four
  of five failures reporting `Reached maximum number of turns`.

## 0.4.0 — 2026-09-22

**This release changes `audit.py`, so a floor set with an earlier version stops comparing.
Re-set it with `--set-floor` after reading the two counts side by side.**

- **A project may hold its own number for a doctrine threshold**, declared in
  `.claude/audit.local.json` under `thresholds`, each with a `reason` and a `date` — the same
  discipline exemptions already carry, for the same cause: a bare number is amnesia, and a dial
  nobody dares turn back only ever turns one way.
- **Mechanism thresholds are refused, loudly.** The 1,024-char spec cap, the 1,536 listing cutoff,
  the compaction slice and the context window are not the project's to move: overriding them
  changes what the audit says, not what the harness does. The error names which one and why.
- **Unknown overlay keys are reported.** They were ignored in silence, so a project writing
  `thresholds` against an older release got no signal and wondered why nothing moved. A
  configuration file that accepts everything and applies part of it is worse than one that refuses.

The case that forced this: an ops repository whose `CLAUDE.md` is 12,858 bytes against a 12,288
ceiling, and whose largest section states that every procedure already lives in its own skill.
There was nothing left to move out — the ceiling would have been paid by deleting a rule. Check 57
of the doctrine says it plainly: uniformise the rule, not the number.

## 0.3.0 — 2026-09-22

**This release changes `audit.py`, so every floor set with an earlier version stops comparing.
Re-set it with `--set-floor` after reading the two counts side by side.**

- **The run-history file is gone.** `--record` and `.claude/audit/history.jsonl` are removed.
  `git log -p .claude/audit/floor.json` is the same trajectory with a timestamp, an author and a
  reason. The floor now carries `error_ids` and `warning_ids`, the only thing the series held that
  it did not.
- **Token figures are floors, and say so.** Measured with `claude plugin details`: four plugins
  varying only description length give `tokens = 18.2 + chars / 3.38` (r² = 0.99992) — a slope and
  a fixed ~18 tokens per listed skill. Two controls at identical length (627 chars) give 174 tokens
  for ordinary prose and 238 for this plugin's own description: **a factor of 1.4 at the same
  length**. The ratio belongs to the text, not to the language. `CHARS_PER_TOKEN = 4` is kept
  because it is the most optimistic ratio observed, which makes every derived figure a lower bound.
- **Check 26 recognises the official eval layout.** It knew only `<skill>/evals/evals.json` and
  reported 0% coverage on a suite that `claude plugin eval` runs — it punished the migration it had
  provoked.
- Check 34 prints both counts and names the command instead of only refusing.

## 0.2.0 — 2026-09-22

- **Check 36 — a plugin must not route to skills it does not ship.** Six routing arrows pointed at
  `skill-creator`, `git-workflow`, `hooks`, `translate`, `claude-api` and `code-review`. In a
  consuming project most of those do not exist, and a dangling reference costs a model more than a
  human: a human shrugs, a model goes looking, and the cost of looking is unbounded. Rewritten to
  the example domain or to "where installed", and the check keeps them from coming back.
- The check reads **routing contexts only** (`➜ See skill:` and `→ \`name\``). A first version
  matched any backticked kebab-case token and returned 21 findings, three quarters of which were
  frontmatter keys and eval vocabulary. A detector wrong seven times in ten is one people skip.
- `skill-creator` is now named as optional in the division-of-responsibilities section, with the
  reason. **No `dependencies` entry**: this plugin needs nothing from it, a dependency would double
  the always-on cost every consumer cannot refuse, and enabling or disabling the two would become
  coupled.

## 0.1.5 — 2026-09-22

- **The hook no longer writes the history series at all.** `history.jsonl` is dated to the day and
  never deduplicated; a session-start hook driving it turns twenty sessions into twenty
  near-identical lines. `--record` is a deliberate act, for CI or by hand. Two earlier attempts —
  writing it unconditionally, then gating on a directory `--set-floor` creates — were fixes to the
  condition when the write itself was the mistake.

## 0.1.4 — 2026-09-22

- **The opt-in for the in-repository history was not an opt-in.** The hook wrote
  `.claude/audit/history.jsonl` wherever `.claude/audit/` existed — a directory that `--set-floor`
  creates. Every project that set a floor was opted in without asking. The signal is now the
  history file itself (`touch .claude/audit/history.jsonl`). A guard whose condition is produced by
  a routine operation is not a guard.
- README: commit `floor.json`, and `.gitignore` the history unless you mean to keep the series.

## 0.1.3 — 2026-09-22

- **Corrects a false claim this plugin was making about itself.** Rule 17 listed three levers a
  project can use to withhold a skill's description. Measured on 2026-09-22, with a project skill
  as the negative control: **none of the three reaches a plugin skill**, with or without the
  `<plugin>:` prefix on the `skillOverrides` key. A consuming project's only lever is disabling the
  whole plugin. Check 30 now says so in its own message: a plugin's listing cost is a tax its
  consumers cannot negotiate, which is an argument for writing the description short.

## 0.1.2 — 2026-09-22

- **`jq` is gone.** `bin/deadweight` and the status line template were shell scripts piping through
  `jq`, a dependency the README did not declare and which fails silently where it is missing. Both
  are Python now — the same requirement `audit.py` already had, and the only one.
- **`deadweight --setup-statusline`** writes `.claude/statusline.py` and wires the setting. A plugin
  cannot ship a `statusLine` of its own, so the alternative was a README telling the reader to copy
  a file from a `<plugin root>` it could not name.
- README install section rewritten with the real commands and no placeholders. `claude plugin
  marketplace add e-xode/deadweight` then `claude plugin install deadweight@deadweight`, and a shell
  function for calling `deadweight` outside Claude.

## 0.1.1 — 2026-09-22

- Cache key for the status line switched from `cksum` to `md5`: the shell and a Python status line
  must compute the same key, and `cksum` is not reproducible in Python without reimplementing it.
- The hook now caches the **findings**, not only the counts, and `bin/deadweight` prints them. A
  status line that says `3W` with no way to see which three is a number without a referent.

- **Check 35 — hooks.** The one component that executes, and the one this auditor could not see.
  Catches event names that do not exist (a typo never fires and never complains), commands whose
  script is not there, `${CLAUDE_PLUGIN_ROOT}` used in a project hook — unresolvable by
  construction, since one variable cannot designate one plugin among those installed — matchers on
  events that always fire, and command hooks with no `timeout` (the default is 600s). Reports as
  INFO which hooks sit on `SessionStart`, `UserPromptSubmit`, `UserPromptExpansion` or
  `PostModelSwitch`, the four events whose stdout Claude Code adds to the model's context.
- **A `SessionStart` hook**, `hooks/session-audit.sh`, and a status line template. The hook records
  the audit into the consuming project and prints nothing; the status line shows the numbers to the
  human for free. See "Two channels, two prices" in the README.
- Check counts copied into prose (27 in one file, 29 in two others, 34 in reality) replaced by a
  pointer to the count the script prints.

## 0.1.0 — 2026-09-22

First extraction, from a private fleet of 19 repositories where this doctrine and its auditor were
developed between July and September 2026.

- `config-auditor` skill: 29 check groups over `CLAUDE.md`, skills, references, sub-agents, rules,
  settings, evals, and the always-loaded budget.
- Eight reference files carrying the doctrine behind the checks, each factual claim sourced and
  dated.
- Per-project exceptions move to `<project>/.claude/audit.local.json` — a plugin's own directory is
  a version-stamped cache and cannot hold project state.
- Skill named `config-auditor`. Two constraints shaped it: the Agent Skills spec forbids the
  reserved words `anthropic` and `claude` in a skill `name`, and the name has to be decidable from
  a request alone — a first attempt, `agent-config`, read as "a skill that configures sub-agents"
  and would have competed for requests about `.claude/agents/`. The verb in `auditor` is what
  separates it from application or build configuration.

### Changed — 2026-09-22

- `audit.py` audits **two containers**: a project (`CLAUDE.md` + settings + agents + rules + skills
  at `.claude/skills/`) and a plugin (a manifest + skills at `skills/`). Layout detected from
  `.claude-plugin/plugin.json`, or forced with `--layout`. The nine project-only checks are skipped
  on a plugin; `PROJECT_ONLY` is named by function and read by the dispatch, so it cannot go stale
  decoratively.
- **New check 30 — plugin cost.** A plugin has no always-loaded budget of its own: its descriptions
  are paid by every project that installs it, once each. The budget check does not disappear on a
  plugin, it inverts.
- **New check 31 — project overlay.** `audit.local.json` moves from a bare list of exempt paths to
  `{"exemptions": [{check, path, reason, date}]}`, and the audit enforces it: no reason, no date, an
  unknown check id, or a path that no longer exists are all reported. Breaking change; no repository
  was using the old key.
- **New `--record`.** Appends one line per run to `.claude/audit/history.jsonl` — date, layout, sha
  of `audit.py`, counts and finding ids. Written by the script, never by a model. The sha is what
  makes the series readable: a drop in errors at a different sha is not the same fact as a drop at
  the same sha.
- Anti-trigger detector widened: it missed `Do not use`, which made a correctly written description
  look unguarded.
- **All worked examples anonymised.** Skill names now describe one fictional shop (`shop-*`, `ui-*`,
  `api-*`, `data-*`); structural examples use `<angle-bracket>` placeholders. Removed the project's
  rule inventory, its fleet counts and every `case-studies.md` pointer — a plugin cannot cite a file
  it does not ship: a human shrugs at a dangling link, a model goes looking for it.
- Fixed a cosmetic rename: `claude-anthropic` survived in 18 places, including the invocation command
  given to the reader, which named both the wrong skill and a path a plugin skill never has.
- Self-audit: **0 errors, 0 warnings**. The largest consuming repository unchanged at 0 errors / 19 warnings.

### Added — 2026-09-22 (second pass)

- **Check 32 — skill name shape and reserved words.** The spec allows lowercase letters, digits and
  hyphens, 64 chars max, and forbids `anthropic` and `claude` in a `name`. A bad name works locally
  and is refused on packaging, which is why it survives unseen — so it is an ERROR in a plugin
  (where it blocks distribution) and a WARN in a project (where it is latent). The skill this plugin
  came from was itself called `claude-anthropic`.
- **Check 33 — confusable descriptions.** TF-IDF over the descriptions that actually compete, cosine
  per pair, threshold 0.35 (calibrated on a 59-skill project: 13 pairs flagged, 2 real). Withheld
  skills are excluded — one that is not in the listing cannot steal an activation, and counting it
  manufactures phantom pairs. This is the one defect that is invisible file by file and exists only
  in the set.
- **Check 34 — the ratchet.** `--set-floor` freezes the counts, `--check-floor` fails when they rise.
  The floor carries the sha of `audit.py` and the comparison refuses to run across two instruments.
- **Check 26 now reports eval coverage.** A skill with no `evals/` used to be skipped in silence: a
  bad suite was an error while no suite was invisible. Reported once as a coverage figure, not once
  per skill — a warning that fires sixty times is a warning people scroll past.
- **`CHECK_ID_ALIASES`.** Check ids became a public API the moment an overlay could name one. They
  are never renamed; an id that must change gets an alias entry, and the old one keeps working.
- **CI** (`.github/workflows/audit.yml`): the plugin audits itself against its own floor on every
  push and pull request.
- **`--json` now carries `layout` and `audit_sha`**, for the same reason the history lines do.
- Eval suite for `config-auditor` itself: 5 positive cases, 2 anti-trigger cases.

### Fixed

- The audit's own bookkeeping (`audit.local.json`, `floor.json`, `history.jsonl`) was resolved
  through `CLAUDE_DIR`, which put `audit/floor.json` at the root of a plugin. Split into `STATE_DIR`,
  always `.claude/`: where the audited configuration lives changes with the container, where the
  audit writes its own state does not.
- Last `claude-anthropic` reference, in an `audit.py` docstring, and the manifest description, which
  still said the plugin audits "a project".
