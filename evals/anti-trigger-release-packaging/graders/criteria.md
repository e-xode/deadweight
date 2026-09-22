---
type: llm
weight: 1
---

The run must NOT load the `config-auditor` skill.

Packaging and distribution belong to `skill-creator` — the skill's own division-of-
responsibilities table assigns them there in as many words. The trap is that this
repository does carry release machinery of its own (a tag workflow, a manifest, a
marketplace entry), so a model reasoning from what the repository contains rather than
from what the skill owns will fire.

A successful response performs or plans the release. It does not open the auditor to do it.
