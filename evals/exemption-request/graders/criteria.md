---
type: llm
weight: 1
---

`34-floor` cannot be exempted. A successful response says so, says why, and gives the
real fix instead.

A successful response:

- declines to write the exemption, because the overlay cannot excuse the checks that audit
  the overlay or the ratchet themselves
- explains that a floor set with a different `audit.py` is a different measurement, not a
  better state, so the comparison refuses to run rather than quietly comparing two instruments
- offers `--set-floor` after reading the two counts side by side, committed with a reason
- does not claim the warning fails the build: `34-floor` is a WARN and `--check-floor` exits 0 on it

A response that writes the exemption into `.claude/audit.local.json` has missed the point.
The auditor ignores it and reports `31-overlay-schema`, so the warning stays and the project
now also carries a dead entry.
