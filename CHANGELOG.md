# Changelog

## 0.13.2 — 2026-09-24

`audit.py` is unchanged: a floor set with 0.13.1 keeps comparing.

### Changed

- **`deadweight --setup-statusline` installs into every host it finds: Claude Code, Copilot CLI,
  or both.** The two do not keep the setting at the same level. Claude Code reads `statusLine` from
  the project, so the line is set per project as before. Copilot CLI reads it from
  `~/.copilot/settings.json` only - set in a repository's `.github/copilot/settings.json` it is
  ignored without a word - so the setup writes one line for every project, and the line finds the
  project from the directory Copilot runs it in. An existing `statusLine` is still left untouched,
  and a settings file with comments is not rewritten.
- **The setup refuses to run inside the plugin.** Without `CLAUDE_PROJECT_DIR` the project is the
  working directory, and an agent that changed into `bin/` to run the command installed the status
  line into the plugin's own folder, where nothing reads it.
- The template falls back to the nearest folder holding `.git` or `.claude/` when its input names no
  project, instead of printing nothing.

## 0.13.1 — 2026-09-23

`audit.py` is unchanged: a floor set with 0.13.0 keeps comparing.

### Changed

- **`deadweight --setup-statusline` writes a launcher instead of a copy of the template.** The
  launcher finds the plugin installed for the project and runs its template, so a release reaches
  the status line at the next session. A copy stays at the version it was taken from: the notices
  0.13.0 added never reached a line set up before it. Run the setup once more to replace a copy.
- **The template exposes `segment(project_dir)`**, which returns the audit segment as a string. A
  status line of your own can load the template from the plugin's install path and call it, rather
  than carry a copy of it. The README says how.
- The status line image shows notices next to warnings, where they usually are.

## 0.13.0 — 2026-09-23

**This release changes `audit.py`, so a floor set with 0.12.0 stops comparing.** The floor counts
do not move: what 0.12.0 reported as INFO and now reports as NOTICE was never counted, and still
is not. Re-set the floor after reading both counts (see
[Versions and your floor](README.md#versions-and-your-floor)). A status line installed before
this release does not show notices until `deadweight --setup-statusline` is run again.

### Changed

- **A fourth severity, NOTICE, for findings that name a file without being a defect.** INFO used to
  carry two things: measurements every run emits (layout, budget, coverage rates), and findings about
  one file - a skill pair separated only by its descriptions, a vendored `SKILL.md` past the
  compaction ceiling, an exemption that excuses nothing, a house convention in the default profile.
  Neither was counted, and the run ended on `All checks passed.` On one repository of the fleet
  this plugin comes from, that line sat under 19 such findings, and the agent that ran the audit
  reported "0 errors, 0 warnings" as the whole result. Those findings are now NOTICE: listed, counted
  as `n` in the summary and the status line, and kept out of the floor. INFO is left with the
  measurements, which never reach zero and are no longer counted anywhere.
- **The summary names notices, and says "passed" only when there are none.** With notices it ends on
  `No error or warning. N notice(s) above: report them too`, then gives the number of measurements
  and asks for them to be offered, not listed. The skill tells the agent the same: every ERROR, WARN
  and NOTICE by name, the measurements by count, shown on request - or appended when there is no one
  to ask.
- **`deadweight` shows notices, and `deadweight --info` the measurements.** The session hook now
  caches both.

## 0.12.0 — 2026-09-23

**This release changes `audit.py`, so a floor set with 0.11.0 stops comparing.** One check moves:
`28-skill-anchors` stops reporting paths written from `.claude/skills/`, so a count can only drop.
Re-set the floor after reading both counts (see
[Versions and your floor](README.md#versions-and-your-floor)).

### Fixed

- **A skill naming a sibling skill's file from `.claude/skills/` was reported as a dead anchor**
  (`28-skill-anchors`). A body that says `shop-refunds/scripts/measure.mjs` resolves against the
  skills folder, the base the overlay already tried for its own paths; check 28 tried the
  repository root and the citing skill's folder only. The file existed, the finding said it did
  not, and the one way to silence it was to rewrite a correct `SKILL.md` around the auditor.

## 0.11.0 — 2026-09-23

**This release changes `audit.py`, so a floor set with 0.10.0 stops comparing.** The counts
themselves barely move: one false ERROR disappears, and a new check reports at INFO, which a floor
does not count. Re-set the floor after reading both counts (see
[Versions and your floor](README.md#versions-and-your-floor)).

### Fixed

- **An overlay holding only `"profile": "house"` was reported as an ERROR** (`31-overlay-schema`,
  "does nothing") — the exact file the README suggests. 0.10.0 added `profile` and left the schema
  check listing `exemptions` and `thresholds` only. Measured on the fleet this plugin comes from:
  10 repositories carried that one false ERROR.
- **`severity` on an `11-english-only` exemption was ignored.** That check skipped exempted files
  before the overlay ran, so an exemption could erase its finding but not downgrade it. Exemptions
  are now applied in one place for every check.

### New

- **`31-overlay-unused` (INFO)**: an exemption that excused nothing in this run. Check 31 already
  caught an exemption naming an unknown check or a vanished file; it missed the third way one dies —
  the auditor stopped firing there, as 0.10.0 did for false positives in checks 22, 28 and 33. Such
  an entry is harmless today and hides the next real defect of that check under that path.
- **`31-overlay-schema` (WARN)** on a `profile` other than `house` or `doc`: a typo silently ran the
  default profile.

## 0.10.0 — 2026-09-23

**This release changes `audit.py`, so a floor set with an earlier version stops comparing.**
Expect the warning count to drop: on the fleet this auditor comes from, 65 warnings across 12
repositories were the auditor's own, and one repository went from 19 to 1 — the one real defect.

### The doctrine, re-read against the documentation

Every reference was compared with the raw documentation pages of Claude Code 2.1.280 and rewritten.
They had been verified against 2.1.259, and several things they stated were no longer true: a
`paths:` skill does load when a matching file is read (measured, and what the docs say); a bundled
skill can be hidden; a subagent may spawn subagents; `bypassPermissions` declared by a subagent is
not honoured. Content describing one particular project's setup is gone. Four references are new:
hooks, settings and permissions, MCP, plugins.

### New checks — what the harness ignores without a word

- **Settings** (`24-settings-scope`): 76 of the 231 settings keys do nothing in a project's shared
  `settings.json`; the Scope column of the settings reference is now read. Also credential or
  routing variables in the shared `env` (`24-settings-env`), a committed or un-ignored
  `settings.local.json` (`24-settings-local`), status line and output style.
- **Permissions** (`42-*`): a rule both allowed and denied, an allow rule naming no tool (it raises
  no warning), an unanchored glob, an `mcp__…(…)` rule, `:*` mid-pattern.
- **MCP** (`43-*`): a literal credential in `.mcp.json`, a credential variable that reads as empty,
  a `url` without `type`, server approvals committed in the shared file.
- **Hooks** (`35-*`): `if` on a non-tool event, combined `if`, a bare `mcp__<server>` matcher,
  unknown handler types and missing fields, the real per-event timeout.
- **Plugins** (`44-*`): component directories inside `.claude-plugin/`, paths without `./` or
  escaping the plugin, fields that replace a default directory, version drift.
- **Agents, skills, CLAUDE.md**: unknown frontmatter fields, `permissionMode`, `Agent(<type>)` in a
  subagent (ignored), `CLAUDE.md` over 200 lines, `@` imports that do not resolve, `AGENTS.md` not
  imported, `CLAUDE.local.md` committed, commands shadowed by a skill, `globs:` in a rule.

### Vocabulary aligned with the docs

The lists of tools (21 → 46), models (`fable`), agent fields (18), skill fields (20) and settings keys
(231) now match the documentation. `Task` is accepted as the alias it is. The maintainers check the
lists against the live pages before every release: a list that enumerates what is valid drifts
toward false with every harness release.

### House conventions no longer pass for Anthropic's

Several checks enforced choices this plugin makes, with the tone of documented rules. They were
checked on 2026-09-23 against the raw documentation, Anthropic's public repositories and guides,
archived versions of the pages and specialised sites — see `evals/CONVENTIONS.md`. Three families:

- **Supported by a measurement** — a negative clause between two skills that compete (check 33).
  A WARN where the measurement applies, and nowhere else.
- **Contradicted by Anthropic** — the check now tests Anthropic's rule, and the house preference is
  an INFO: a reference over 100 lines needs a table of contents (the old "split it past 300 lines"
  warned people who followed the documentation); CLAUDE.md is measured in lines, not bytes.
- **No source, no measurement** — the `## Agents directory` table, a rule under 2 KB, English only,
  a global budget, description lengths. INFO, each finding naming what Anthropic documents instead.
  A project that wants them as warnings sets `"profile": "house"` in `.claude/audit.local.json`.

On 20 public repositories never seen before: warnings 196 → 86, the same 10 errors, no verified
defect lost.

### Severity follows one rule

**ERROR** when the defect is certain — the harness rejects or ignores the thing, or its target does
not exist. **WARN** for a probable defect or a convention of this plugin. **INFO** for what cannot be
verified from the repository. Several house conventions were ERRORs and are now WARNs (`01-claude-md-size`,
`09-*`, `13-no-global-scripts`, `17-always-loaded-budget`); a missing `CLAUDE.md` is INFO — it is optional.

Measured on 20 public repositories drawn after all tuning, never seen before: **10 errors, all
real** (0.9.0 reported 36 on the same repositories), and 50 of the 55 warnings that are not house
conventions checked true by hand.

### What it stops saying wrongly

- **`28-skill-anchors` checked half a path.** The pattern opened on a word boundary, and `/` is
  not a word character, so `.claude/skills/<skill>/scripts/measure.mjs` was read as
  `scripts/measure.mjs`, looked up from the root, and reported dead. The whole path is read now.
  The bug was there from the first release that shipped the check.
- **`33-description-overlap` now sees its own remedy.** When each of two close descriptions
  excludes the other in its anti-trigger clause, the pair is reported as INFO — separated by
  declaration, not measured. When only one side excludes the other, the WARN names the missing
  direction. A name mentioned outside an exclusion clause still counts for nothing.

### The same commit gives the same count on every machine

A floor that moves with the machine is not a floor. Measured on one repository: 0 findings on the
machine that built it, 1 on a fresh clone of the same commit.

- **Anchors and rule globs git ignores are not counted.** `dist/`, `node_modules/`, or any path
  under an ignored directory exists only where the project was built or its assets downloaded. It
  is asked of `git check-ignore`, which answers from the rules and works on absent paths, and it
  is reported as an INFO listing what could not be verified. Absolute paths and paths outside the
  repository are treated the same way.


## 0.9.0 — 2026-09-23

**This release changes `audit.py`, so a floor set with an earlier version stops comparing.**

Measured on a second sample of **15 public repositories created after the first sample was
drawn**, so none of them can have been in it. On that sample 0.8.0 reported **7 errors, and 6
were its own**: it mistook shapes it did not know for projects missing their `CLAUDE.md`. This
release reports **16, all checked by hand**: 11 are plain defects (a `name` that does not match
its folder, a broken link), 4 depend on a house threshold or on whether `CLAUDE.md` is required,
and none is the auditor's.

### Claude Code finds skills by location, not by content

Measured from the session's `init` event: `<name>/SKILL.md` at a repository root loads neither
in a project nor under `--plugin-dir`; `skills/<name>/SKILL.md` loads under `--plugin-dir` with
no manifest at all, and `claude plugin validate` passes.

- **Two new layouts.** `library` — skills kept at the root, no project, no manifest: their content
  is audited instead of being ignored. `none` — no Claude Code configuration at all (a `SKILL.md`
  under another tool's folder, or a test fixture): one INFO, and no "CLAUDE.md not found".
- **A plugin without a manifest is a plugin.** `skills/*/SKILL.md` at the root, with no
  `CLAUDE.md` and no `.claude/`, is now audited as one.
- **`40-skill-not-loaded`.** Skills at the root load nowhere as they stand. ERROR when the
  repository carries a sign it targets Claude Code (`CLAUDE.md`, `.claude/`, `.claude-plugin/`),
  WARN otherwise — the repository may target another tool, or installation by copy.

### What it stops saying wrongly

- **`15-skill-index` no longer demands an empty heading.** A missing `## Skills index` was an
  ERROR on every project, including a minimal clean one. The section exists to point at skills
  the listing withholds: with none withheld it is not needed (INFO), and with one withheld and no
  section, the ERROR names that skill.

### Status line

- **A number is shown only when it changes what you do.** Zero counts are dropped (`19W`, not
  `0E 19W`; `✓` when both are zero). The version appears only as a difference: `↑0.9.0` when the
  local copy of the marketplace knows a newer release than the one installed — read from Claude
  Code's own files, no network.
- **`↻` alone** marks a number that is not comparable. It used to carry a remedy — "reopen the
  session" — which was wrong whenever the floor was the older side: measuring again changes nothing
  there. `deadweight` now says which case applies, `--fresh` or `--set-floor`.
- **`deadweight --fresh` rewrites the cache the status line reads.** It used to run the audit and
  print it, leaving the `↻` it had just told you to clear exactly where it was.
- **The README opens with install and use**, and the reference comes after. The status line image
  is generated from the real template on a fictional project (`docs/render_statusline.py`).

## 0.8.0 — 2026-09-22

**This release changes `audit.py`, so a floor set with an earlier version stops comparing.**

Measured against a sample of **15 third-party public repositories** cloned for the purpose —
configurations this auditor had never seen. On that sample it reported **38 errors before, 7
after, and all 7 are real**. The 31 it stopped reporting were its own defects, not theirs.

### What it stops saying wrongly

- **The frontmatter parser lost every field that followed a YAML comment.** A `# SECTION` line
  above `name:` was glued onto the name, so every downstream check judged a value the file does
  not contain. One sampled repository produced **422 false errors** from this alone, and 179 of
  the sample's `SKILL.md` files carry such a comment. A second defect sat beside it: the flush
  discarded nothing when no key had been seen yet, which is how the comment leaked forward.

- **Half the checks escaped the dispatch.** `PROJECT_ONLY` and `PLUGIN_ONLY` only governed the
  checks called through the `run()` wrapper; the other eighteen were called directly and ran
  everywhere. A dispatch that decides for some of its subjects is not a dispatch. Every check
  now goes through it, and a `marketplace` layout — a repository whose `.claude-plugin/` holds
  only a catalogue — runs the one check that has a subject there instead of thirty-seven.

- **Nested skill folders are found.** A repository that groups skills by category
  (`skills/<domain>/<skill>/SKILL.md`) had **none** of them audited, and was told its skills were
  missing. 165 skills in one sampled repository were invisible. Directories named `assets`,
  `templates`, `scripts`, `references`, `shared`, `common`, or prefixed `_`, are support folders
  and no longer reported as malformed skills.

- **A plugin that ships only commands, agents or hooks is valid.** It was an ERROR. Telling an
  author their working plugin is broken is how an auditor gets uninstalled rather than heeded.

- **Links inside fenced code blocks are specimens, not references.** A reference file showing a
  reader how to write a context map links to the `src/` the reader will create. Links that climb
  above the repository root are no longer checked either: `../../../-/issues/174` resolves on a
  forge, and nothing outside the repository can be verified from inside it.

- **The overlay reached exactly one check.** An exemption written for any id other than
  `11-english-only` was schema-checked, counted in the summary, and applied to nothing. Nobody
  had been bitten because nobody had written one. It now applies to every check — and `severity`
  is the addition that makes the file worth writing: `WARN` or `INFO` **downgrades** a finding
  instead of erasing it, so the count stays visible and `--check-floor` still watches it grow.
  No exemption can silence `31-*`, `34-audit-sha` or `00-layout`: a valve able to disconnect its
  own pressure gauge is not a valve.

- **The README documented a schema the auditor rejects.** It still showed `english_only_exempt`,
  a key nothing has read since the structured `exemptions` list landed. A project following the
  README earned a `31-overlay-schema` error for doing so.

- **`36-foreign-skill` accepted a bare arrow, and a bare arrow means transition.** On the same
  15-repository sample it returned **140 findings of which roughly 130 were false**: `running →
  `success``, `→ `not-started``, `→ `8867-4`` — state tables, enum values, status strings. Only
  the stated `➜ See skill:` convention is read now, and an agent the plugin ships is no longer
  reported as a skill it lacks. The sample drops from 140 findings to 0; a synthetic control
  confirms the check still fires on a genuine dangling route.

- **A check that fires more than five times is rolled up** in the text report. One repository
  produced 188 dead-anchor warnings: the reader learns the number, not the anchors, and pays 188
  lines for it. `--all` and `--json` still show everything, and the floor always counted
  everything — the ceiling is a display decision, never a detection one.

- **`04-skill-description-antitrigger` now states its register.** It demands a practice whose
  benefit this project tried to measure and could not: at 3 runs per arm the eval harness's own
  noise (±0.67 on a control arm that no edit can reach) exceeds the effect, and the one direction
  the numbers leaned was the counter-intuitive one. The message says it is doctrine, says the
  measurement was inconclusive, and names the sample size that would settle it.

- **The two anti-trigger eval cases were retired and rewritten from the sample.** The old ones
  were echoes of the description *and* too easy — "refactor a controller" sits nowhere near a
  configuration audit, so it passed whatever the description said. The new ones are near misses
  drawn from real public repositories: scaffolding a `.claude/` tree, and shipping a release.
  Writing the first of them exposed a real defect — the description offered `packaging skills as
  a plugin` as a trigger, which a release task matches — now narrowed to `a plugin manifest or
  marketplace entry needs checking`.

- **A cross-reference to a plugin skill was reported as broken.** Checks 18 and 36 read
  `➜ See skill: deadweight:config-auditor` — the very form a consuming project must write to
  route here — stopped at the `:`, kept `deadweight` alone, and reported a non-existent skill.
  The plugin therefore manufactured an ERROR in any project that followed the convention the
  plugin itself prescribes. A namespaced name now parses whole and is not resolved: whether it
  exists depends on what the reader installed, and nothing on disk says. Same call already made
  for a link that climbs above the repository root.

- **`marketplace.json` no longer carries a second version number.** `metadata.version` said
  `1.0.0` while the plugin entry said `0.8.0`. Written once at 0.1.0 and never touched across
  eight releases, it was inert, the field is optional, and two numbers nothing synchronises are
  two numbers that drift.

### What it judges now

**The auditor now judges whether an eval suite can fail.** Three checks, each born from a defect
found by hand on this plugin's own suite on 2026-09-22 — every one of which `26-evals-schema`
declared sound:

- **`39-eval-judged-fact`** — an `llm` rubric that states a fact about the run (*"must load"*,
  *"must not call"*) while the case carries no `tool_used` grader. The judge reads the last
  message, not the trajectory, so it can pass a run that did the opposite. Measured here:
  a rubric opening with *"The run must load the `config-auditor` skill"* passed **3 runs out of
  5 in which the skill was never loaded**. The judge was not capricious, it was blind.
- **`39-eval-all-llm`** — a case whose every grader is a judge. Measured on twenty runs: a
  deterministic grader carries a standard deviation of **0.000**, the judge grading the same
  runs **0.49**. Whatever can be counted is being voted on.
- **`39-eval-no-fixture`** — no case declares a `scaffold_script`, so every case runs against an
  empty workspace. A rubric that asks the run to measure a CLAUDE.md, a skill or a budget is
  asking about files that are not there.

**An unreadable file took the whole audit down.** Nine call sites caught only
`UnicodeDecodeError`, so a file the process may not open raised `PermissionError` and ended the
run — found when an eval sandbox masked `.claude/loop.md` and the transcript reported that the
audit script crashes. The catches now include `OSError`, and the new **`38-unreadable`** reports
what was skipped: an auditor that says nothing about what it could not read is claiming a
coverage it does not have.

**Checks 04 and 08b carried two different anti-trigger patterns.** 08b's missed `Do not use`
with a space, which 04 accepted, so the same clause was seen on a skill and not on an agent.
One shared `ANTI_TRIGGER_RE` now serves both, widened to the openers actually in use. It also
accepts non-English openers: a project that has formally exempted `11-english-only` writes its
descriptions in its own language, and refusing to see the clause there fires this check on
precisely the projects that already declared their exception.

**The skill's own description was under-triggering, measured.** Two requests squarely inside its
subject did not load it: *"Two of our skills keep firing on each other's requests"* (**1 run in
10**) and an exemption request (**0 in 10**). The diagnosis cost nothing — the first shared **no
word of four letters or more** with the trigger surface, the second shared one. Two clauses were
added (748 to 899 chars, cap 1,024), after which both reach **10 out of 10**, the first at a
constant prompt (Fisher exact, **p = 0.000119**).

**Three eval rubrics now grade doctrine rather than a measurement.** The eval sandbox masks the
workspace's `.claude/` files, so no case can read a real CLAUDE.md, skill or agent:
`33-description-overlap` reports `0 listed description(s)` there. `budget-growth` and
`two-skills-compete` were failing every run for a reason unrelated to the skill.

**`exemption-request` was a case that passed without the skill under test.** It asked how to
silence a warning on a file kept in another language — answerable from general knowledge, and
answered correctly in 3 runs of 5 in which the skill never loaded. It now asks for an exemption
on `34-audit-sha`, which cannot be exempted: the overlay may not excuse the checks that audit
the overlay or the ratchet themselves. The right answer is a reasoned refusal.

## 0.7.1 — 2026-09-22

- **An exemption now covers every path check 11 reports.** The `src/` branch never consulted the
  overlay, so a project could declare an exception on a file under `src/` and keep being reported
  for it: the mechanism meant to remove the noise produced it instead. Paths there are relative to
  the project root, which is how a reader names a file under `src/`; the template says so.

## 0.7.0 — 2026-09-22

**This release changes `audit.py`, so a floor set with an earlier version stops comparing.**

- **Check 11 reads scripts, not only Markdown.** The rule says English in every persisted artefact,
  and a script is the most read file in a plugin after the README — but the check never opened a
  `.py` or a `.sh`. This auditor's own source had drifted to **95 French words**, found by a reader
  rather than by the check that exists for exactly this.

  A first fix exempted `audit.py`, because the check's own French dictionary would otherwise trip
  it. That would have made the one file where the drift happened the one file that cannot be
  policed. The dictionary is fenced with `# i18n-data:` markers and skipped instead.

- **Content declared as a locale is no longer flagged.** A multilingual project has to carry each
  language properly, French included; a check that reports `pricing-fr.md` for being in French is
  wrong in a way that costs it its credibility. What matters is that the language is **declared in
  the name**. Measured on one repository: **11 of 19 findings under `src/` were locale-suffixed
  files**, reported only because the convention there is `-fr.md` while the check exempted
  `.fr.md`. Across four repositories the count went from 25 to 12, and everything that disappeared
  was correctly-declared localised content.

  The exemption rests on the **name**, not the content, and deliberately so: a French file with no
  locale marker still reads as drift, which is precisely the defect worth seeing.

## 0.6.0 — 2026-09-22

The status line template was two designs behind the one its author runs. Improving your own copy
and leaving the shipped one behind is the same defect as removing a feature and leaving its
documentation — found the same way, by a reader rather than by a check.

- **Colour encodes what needs an action, not the size of the count.** A repository at its floor
  showed yellow every day, for the state where there is nothing to do. It is dim now; yellow is
  reserved for errors, red for the one urgent case — a count above the floor.
- **Freshness is measured, not guessed from age.** A threshold on age answered "is this number
  old?" when the question is "is it still true?": three days in an untouched repository is exact,
  two minutes in one you just edited is already false. The segment now compares the measurement
  against the newest mtime of the configuration — ~6 ms over 500 files, against a 300 ms debounce —
  and `.claude/audit/` is excluded, since setting a floor would otherwise invalidate the
  measurement that produced it.
- **The plugin's name leads the segment** and doubles as the command that shows the detail, which
  makes the word `audit` redundant.
- Two signals for one fact are one too many: the age no longer prints next to a staleness message.

## 0.5.1 — 2026-09-22

- **Check 37 reads fenced code blocks only.** Released an hour earlier, it read any line containing
  `audit.py` and produced five findings across a fleet of sixteen repositories — **five false, none
  true**. The best of them flagged the sentence « This is why `audit.py` has no `--fix` flag »:
  reported for asserting exactly what the check wants to be true. The other two were prose putting
  two different commands on one line.

  The defect this check exists for is a flag inside a block someone **copies and runs**. Prose that
  mentions a flag is a lesser problem and not this one. A detector wrong five times out of five is
  one nobody keeps — and a check that is skipped protects nothing.

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
