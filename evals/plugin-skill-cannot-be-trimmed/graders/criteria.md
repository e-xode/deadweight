---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says no key is wrong in the way the user thinks: `skillOverrides` does not reach plugin skills at all, with or without the `<plugin>:` prefix
- says the project levers that withhold a skill from the listing (`skillOverrides`, `disable-model-invocation`, `paths:`) act on project or personal skills, not on a plugin's
- gives the lever that does exist: disable or uninstall the whole plugin (through `/plugin` or `enabledPlugins`), or ask its author to trim the description

Proposing another spelling of the key (without the prefix, another value, another settings file) as the fix is the failure.
