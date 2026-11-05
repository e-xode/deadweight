---
type: llm
weight: 1
---

Grade the doctrine. The setting is in the prompt.

A successful response:

- says plugin skills are not affected by `skillOverrides`, so the entry changes nothing (the skills page says so)
- says the way to act on a plugin skill is the plugin itself: `/plugin`, or disabling the plugin (`enabledPlugins`), not a different `skillOverrides` value or key spelling

Suggesting a different value of `skillOverrides`, or a different spelling of the key, as the fix is the failure.
