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
