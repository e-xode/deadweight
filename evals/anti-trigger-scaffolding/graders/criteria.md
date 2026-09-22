---
type: llm
weight: 1
---

The run must NOT load the `config-auditor` skill, and must NOT reach for it to decide what
to generate.

This case is a near miss by construction. The request names the exact objects the skill
audits — agents, skills, hooks, settings — in the exact container it audits them in. Every
lexical signal points at the skill. Only two things point away, and both live in the
skill's own text rather than in the request:

- the skill **judges an existing configuration**; it does not author one
- core rule 5 is explicit — propose, never auto-fix, which is why `audit.py` has no `--fix`

A successful response either asks what the project needs before writing anything, or
scaffolds from first principles. A response that loads `config-auditor` has read the
skill's vocabulary and missed its verb.
