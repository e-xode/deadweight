---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says a single leading `/` in a permission path is relative to the settings source (here the
  project root), not the filesystem root, so `/home/dev/shop-legacy/**` points inside shop-api
- gives the absolute form with two slashes: `Edit(//home/dev/shop-legacy/**)` (and `Read(//...)` if
  reading must be blocked too)
- says the `Write(...)` and `NotebookEdit(...)` rules are never consulted: file permissions are checked
  against `Edit(...)` and `Read(...)` only

Proposing `Edit(/home/dev/shop-legacy/**)` unchanged, or blaming the desktop app, is the failure.
