---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says Claude Code checks file permissions against `Edit(...)` and `Read(...)` rules only: a `Write(...)` path rule is accepted and never consulted (a startup warning is the only sign)
- replaces it with `Edit(secrets/**)` - and `Read(secrets/**)` if reading must be blocked too, since a Read deny also blocks edits on that path

Saying the glob is wrong, or that deny rules do not work on edits, is the failure.
