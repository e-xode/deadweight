---
type: llm
weight: 1
---

Grade the doctrine. The configuration is in the prompt; the sandbox holds no such files.

A successful response:

- says the `Authorization` header holds a literal credential in a file every clone receives, and
  replaces it with an environment reference such as `"Bearer ${SHOP_MCP_TOKEN}"`
- says `enableAllProjectMcpServers` committed in the shared settings file does not let a cloned
  repository approve its own servers before the workspace is trusted, and that approvals belong
  in each person's `settings.local.json` or user settings
- recommends rotating the token, since it may already be in history elsewhere

Approving the files as they are, or only fixing one of the two, is the failure.
