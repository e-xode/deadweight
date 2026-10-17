# Contributing

## How a change gets in

`main` is protected. Every change arrives through a pull request that:

- passes **`self-audit`** — this plugin runs its own auditor on itself against a recorded floor,
  because a repository that ships an auditor and does not run it on itself has the exact defect it
  exists to catch;
- passes **`verify`** — the manifest and the marketplace entry declare the same version, and that
  version carries a `deadweight--v<version>` tag;
- carries **one approval**, and leaves no unresolved review conversation.

Fork, branch, open the PR. You do not need write access, and nobody has it except the maintainer.

## What the protection does not do, stated plainly

The maintainer can bypass all of it. That is deliberate — the release runs from a local machine,
behind gates that **cannot** run in CI (see below) — and it means this protection is not a wall
against the maintainer's own mistakes. It is a gate for contributions and a guarantee that CI has
passed before anything merges. A guard-rail described as more than it is teaches people to trust it
where it does not hold.

## Why the release does not run in CI

The release gate includes an **anonymity check**: this plugin is extracted from a private fleet, and
nothing from that fleet may reach these files — no repository name, no client name, no machine path.
That check needs the list of private names this public repository must not contain, and **a public
repository holding that list has already leaked**. So the check lives on the private side, and CI
can never be the complete gate.

It has caught real leaks twice, including thirteen absolute machine paths that reached this
repository through a tag and had to be removed.

## Changing a check

- **Check ids are frozen.** A consuming project names them in its `.claude/audit.local.json`;
  renaming one silently makes that exemption inert and the audit then blames the project for a
  rename it did not make. An id that must change gets an entry in `CHECK_ID_ALIASES`, and the old
  one keeps working, for good.
- **Thresholds come in three families.** Mechanism (the 1,024-character spec cap, the listing
  cutoff, the compaction slice) is not negotiable and the overlay refuses to move it. Doctrine is
  a project's to hold, with a reason and a date. Derived comes from the project's own settings.
- **A new or changed check needs a negative control.** Build the faulty input, run the audit, and
  show that it moves. Every wrong conclusion in this repository's history came from the instrument,
  never from the analysis — and two checks shipped with more false positives than true ones before
  a negative control caught them.
- **`audit.py` changing means every consumer's floor stops comparing.** Say so at the top of the
  CHANGELOG entry. Of the first seven releases, two touched `audit.py` and five did not.

## Language

English, in every persisted file — including scripts. Check 11 reads `.md`, `.py` and `.sh`. Files
that are content in another language declare it in their name (`notes-fr.md`, `docs/fr/…`) and are
not reported: a multilingual project carries every language properly, and what separates drift from
localised content is whether the language is declared.

## Add a labelled case

A labelled case is a small fictional repository and the findings the auditor **must** produce on
it. `tests/cases/*.json` (one file per check family) is generated from the maintainer's private
source and must not be edited by hand. Your cases go in `tests/cases.d/<topic>.json`, in the same format, and
`tests/test_cases.py` replays them exactly like the generated ones. Start from
`tests/cases.d/example-shop-refund.json`:

```json
{"cases": [{
  "id": "contrib-28-dead-script-beside-live-reference",
  "files": {"CLAUDE.md": "...", ".claude/skills/shop-refunds/SKILL.md": "...", "...": "..."},
  "git": true,
  "expected": [["28-skill-anchors", "WARN", 1], ["19-frontmatter-quoting", "WARN", 0]],
  "forbidden_messages": [["28-skill-anchors", "refund-window\\.md"]]
}]}
```

- `files` maps a path **relative to the repository root** to its content; `git` runs `git init`.
- `expected` lists `[check id, severity, exact count]` for the checks the case is about; checks it
  does not name are not compared. `forbidden_messages` lists `[check id, regex]` that no finding of
  that check may match. Both check ids must be ones the auditor emits, and the regex must compile.
- Optional keys: `links`, `gitignore`, `runtime` and `known_failure` (described in the `_note` of
  any file of `tests/cases/`); `needs_exec_bit` and `case_sensitive_fs` skip the case on a platform without
  an execute bit or on a case-insensitive filesystem. `known_failure`, `needs_exec_bit` and
  `case_sensitive_fs` are `true` or `false`: a string such as `"no"` is refused by the format test.

Run the whole suite, no network needed:

    python3 -m unittest discover -s tests

Rules the suite enforces:

- **A case states the correct behaviour**, checked by reading the configuration and the official
  documentation, not what the auditor printed. A count of `0` is also satisfied by a check that
  never fires, so a check you expect at `0` must be seen firing in some case; the guard tests fail
  otherwise. The guards compare the check id, not yet the severity: a `0` at a severity the check
  never emits (a `WARN 0` on a check that only emits `NOTICE`) passes them and proves nothing, so
  make sure some case fires your check **at that severity**.
- **A defect you cannot fix** gets `"known_failure": true`: the case is replayed and reported as a
  skip that names its gaps (`OK (skipped=N)`; `-v` lists each one), and does not fail the suite. It
  fails if a check crashes on it, or once it passes: then remove the flag. Say what is wrong in the
  pull request.
- **Ids are unique** across every file of `cases/` and of `cases.d/`. A prefix such as `contrib-`
  keeps yours apart.
- **Fictional names only**: `shop-*`, `ui-*`, `api-*`, `data-*`. No real project, company or person,
  no home folder other than a fictional one, no email outside `example.com` or `.test` (`.md`,
  `.sh` and `.py` are country domains too: only an upper-case file name such as `n@AGENTS.md` is
  read as a file), no token in a real provider format (an obviously fake value works: the secret
  checks read the shape).
- Paths stay inside the case: no absolute path, no `..`.
