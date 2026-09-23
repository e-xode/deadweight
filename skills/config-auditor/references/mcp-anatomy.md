<!-- The worked examples in this file describe one fictional project: an online shop
     whose team runs a remote MCP server `shop-api` (catalogue and orders), a local
     stdio server `shop-db` (read-only database access), and a plugin `shop-kit`
     that bundles a third server `search`. It is invented, and deliberately not
     `foo`/`bar`: a placeholder with no domain teaches nothing about naming or scope.
     Where only the structure matters, <angle-bracket> placeholders are used instead.
     No example carries a real token format: credentials are written `Bearer <token>`
     or `${SHOP_MCP_TOKEN}`. -->

# MCP anatomy

Contents: [Scopes and storage](#scopes-and-storage) · [Transports and required fields](#transports-and-required-fields) · [Environment variables](#environment-variables) · [Secrets](#secrets) · [Project-server approval and workspace trust](#project-server-approval-and-workspace-trust) · [Names: permissions and hooks](#names-permissions-and-hooks) · [Context cost](#context-cost) · [Organisation controls](#organisation-controls) · [What audit.py checks, and what it does not](#what-auditpy-checks-and-what-it-does-not)

Verified against the docs on 2026-09-23 (Claude Code 2.1.280).

Sources, read raw (`curl -sL https://code.claude.com/docs/en/<page>.md`): **mcp**, **managed-mcp**,
**permissions** (§ MCP, tool-name globs), **hooks** (§ Match MCP tools), **plugins-reference**.
Every fact below names its page in parentheses. Lines marked **House** are this plugin's
convention or measurement, not the documentation's.

The angle of this page: an MCP misconfiguration rarely errors. It loads the server without a
field, sends a header empty, or leaves a hook that never fires. Each section says what fails
in silence and where it becomes visible.

## Scopes and storage

| Scope | Loads in | Shared | Stored in |
| --- | --- | --- | --- |
| local (default of `claude mcp add`) | current project | no | `~/.claude.json`, under `projects["<path>"].mcpServers` |
| project | current project | yes, via version control | `.mcp.json` at the project root |
| user | every project | no | `~/.claude.json`, top level |

(mcp, MCP installation scopes)

- "Local" MCP scope is **not** `.claude/settings.local.json`: it lives in the home directory (mcp, Local scope). An auditor that looks for local servers in the repository finds none, correctly.
- Precedence when a name repeats: local > project > user > plugin > claude.ai connectors. **The whole entry from the winning source is used; fields are not merged** (mcp, Scope hierarchy). Scopes match by *name*; plugins and connectors match by *endpoint*, so a plugin server pointing at the same URL as a user server is a duplicate and loses. A server provided through managed `managedMcpServers` ranks above all (mcp, same section, 2.1.259+).
- Same name, different endpoints in two scopes: a warning in `claude mcp list` and `/mcp`, and OAuth sign-ins are stored per endpoint, so signing in once does not carry across projects (mcp, Configuration warnings).
- Reserved names (`workspace`, `claude-in-chrome`, `computer-use`, `Claude Preview`, `Claude Browser`) are **skipped at load** with a warning (mcp, Configuration warnings).
- A plugin's `.mcp.json` sits at the plugin root, never in `~/.claude/`: a `~/.claude/.mcp.json` is not read (plugins, Plugin structure overview).

**How to see it:** `claude mcp list` and `claude mcp get <name>` print the effective definition and the warnings; `/mcp` shows the same per server.

## Transports and required fields

| `type` | Required | Notes (mcp, Installing MCP servers) |
| --- | --- | --- |
| absent / `stdio` | `command` (+ `args`, `env`) | an entry with no `type` **is read as stdio** |
| `http` (alias `streamable-http`) | `url` | recommended for remote servers; OAuth supported |
| `sse` | `url` | **deprecated**; since 2.1.265 `--transport http` falls back to SSE by itself |
| `ws` | `url` | header-only auth, no OAuth, no `claude mcp add --transport ws`; absent from `claude mcp list` |

Silent or near-silent failures:

- **`url` without `type`** → read as stdio → **skipped**, with `MCP server "<name>" has a "url" but no "type"` (mcp, Option 1). In a headless run the only trace is `mcp_server_errors` in the `system/init` event (2.1.219+). → `43-mcp-shape` ERROR.
- **`type: "sse"`** still works but is deprecated → `43-mcp-shape` INFO.
- **Invalid JSON** in `.mcp.json` → `43-mcp-shape` ERROR.
- **Empty `url`** on a remote entry is *not* an error: shown as `not configured`, never connected — the documented way for a plugin to ship a placeholder connector (mcp, Server status detail).
- **Hidden whitespace** (a pasted token with a trailing newline) in `command`, `url`, `args`, `env`, `headers`: warned, **not trimmed**, used as written (mcp, Configuration warnings).
- A stdio server receives `CLAUDE_PROJECT_DIR` in *its* environment, not Claude Code's: referencing `${CLAUDE_PROJECT_DIR}` in `command`/`args` of `.mcp.json` or `~/.claude.json` needs a default, `${CLAUDE_PROJECT_DIR:-.}`. Plugin MCP configs substitute it directly (mcp, Option 3).

Minimal valid project file:

```json
{
  "mcpServers": {
    "shop-api": { "type": "http", "url": "https://mcp.shop.example/mcp",
                  "headers": { "Authorization": "Bearer ${SHOP_MCP_TOKEN}" } },
    "shop-db":  { "command": "node", "args": ["tools/shop-db-server.js", "--read-only"] }
  }
}
```

## Environment variables

Syntax: `${VAR}` and `${VAR:-default}`. Expanded in `command`, `args`, `env`, `url`, `headers` (mcp, Environment variable expansion).

| Case | Behaviour (mcp) | Visible where |
| --- | --- | --- |
| `${VAR}` set | expanded | — |
| `${VAR}` unset, no default | server **still loads with the literal text `${VAR}`** | missing-variable warning in `claude mcp list` and `/mcp` |
| `${VAR:-default}` unset | `default` | — |
| protected credential name, remote `url`/`headers` | **read as empty, set or not; `:-default` ignored** | nothing but a 401 → "failed to connect"; a debug-log line `never expanded toward a remote server` (`claude --debug-file <path>`) |

Protected names: Claude Code's own credentials (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`), cloud-provider credentials (`AWS_BEARER_TOKEN_BEDROCK`), and others the environment carries (`HTTPS_PROXY`, `NPM_TOKEN`) — the page lists these *as examples* ("such as"), so the set is wider than the list (mcp, Credential variables that read as empty). `ANTHROPIC_BASE_URL` still expands. The fix is to copy the value into a variable with a name of your own.

→ `43-mcp-credential-var` ERROR on the five documented names in a remote `url` or `headers`. **House:** the check matches only those five; a name the docs cover without listing it passes unflagged.

`/mcp` and `claude mcp list/get` show a `${VAR}` reference by name, never resolved (mcp, How references appear, 2.1.268+ for `/mcp`). So a screenshot of `/mcp` does not prove the variable is set.

## Secrets

- `.mcp.json` is committed by design (mcp, Project scope). A literal credential in it is in every clone. → `43-mcp-secret` WARN: a value in `url`, `headers`, `env` or `args` that looks like a literal token and contains no `${`. **House:** the pattern is a heuristic (bearer strings, common vendor prefixes); a secret in an unusual shape passes.
- Prefer, in this order: a `${VAR}` reference; **`headersHelper`**, a command printing a JSON object of headers, run at each connection and re-run once on a 401/403 (mcp, Use dynamic headers); OAuth for `http`.
- `headersHelper` facts that change an audit (mcp, same section):
  - it runs in a shell, 10 s limit, output overrides static `headers` of the same name;
  - for project and local servers it runs **only after the workspace trust dialog**; until then the server connects with static `headers` alone (in `-p`/SDK: one `headersHelper not run` line on stderr);
  - from a project `.mcp.json` or a plugin, it runs **without** credential-looking variables (`*TOKEN*`, `*SECRET*`, `*KEY*`, `*AUTH*`, `*PASSWORD*`, any case) — a helper that reads `$SHOP_MCP_TOKEN` gets nothing; read from a file or a credential store;
  - relative paths resolve against the directory of the declaring config (project dir, plugin root, or `~/.claude`), not the shell's cwd;
  - a plugin's `headersHelper` may **not** contain `${user_config.KEY}` (shell-parsed) → server reported misconfigured; put it in `headers` instead (mcp; plugins-reference, User configuration).

## Project-server approval and workspace trust

- Interactive sessions ask before using a `.mcp.json` server; `claude mcp reset-project-choices` resets the answers (mcp, Project scope).
- **`claude -p`, SDK and cloud sessions load project servers without asking**; so does a `bypassPermissions` start with `skipDangerousModePermissionPrompt`. To keep one out: `disabledMcpjsonServers` (any scope, always wins), `--setting-sources` without project, or `--strict-mcp-config` (mcp, Project scope).
- Since 2.1.196, **a cloned repository cannot approve its own servers**: `enableAllProjectMcpServers` / `enabledMcpjsonServers` in the committed `.claude/settings.json` are ignored in an untrusted folder; the server stays `⏸ Pending approval`. Approvals that still apply untrusted: user settings, managed settings, `--settings`. An untracked `.claude/settings.local.json` counts only once the folder is trusted (git is run to check it is untracked) (mcp, Project server approvals and workspace trust).
- → `43-mcp-approval` WARN when either key is committed in the shared `settings.json`. **Why it stays a warning after 2.1.196:** that shipped approval is the shape of CVE-2025-59536 (Check Point Research), it is inert in the untrusted case, and it silently approves every *future* server once the folder is trusted. Approvals belong in `settings.local.json` or user settings.
- `disabledMcpServers` / `enabledMcpServers` (per-project toggles in `~/.claude.json`) are unrelated to the `*Mcpjson*` approval keys; an entry in the wrong list is ignored (mcp, Disable a server without removing it).

## Names: permissions and hooks

Callable name: `mcp__<server>__<tool>` (permissions, MCP; hooks, Match MCP tools). The `<server>` is the configured key, which is a label — a user can call any server `shop-api` (managed-mcp, Match servers: `serverName` "is not a security control").

**Permission rules** (permissions):

| Rule | Effect |
| --- | --- |
| `mcp__shop-api` or `mcp__shop-api__*` | every tool of `shop-api` |
| `mcp__shop-api__get_*` (allow) | valid: a glob **after a literal `mcp__<server>__` prefix** |
| `mcp__*` or `*` in **allow** | **skipped with a warning; approves nothing** |
| `mcp__*` in **deny/ask** | valid: every MCP tool |
| any `mcp__…(…)` with parentheses in a settings file | **skipped**; listed in the invalid-settings dialog and `claude doctor` |

**Hook matchers** (hooks, Match MCP tools):

- `mcp__shop-api__.*` matches all tools of the server. **The `.*` is required**: `mcp__shop-api` is exact-match characters, compared as a whole string, and matches **no tool** (2.1.195+; earlier it matched as an unanchored regex). → `35-hooks-matcher`.
- `mcp__.*__write.*` matches write-prefixed tools on any server.
- Hook input carries `mcp_server.source` (`plugin`, `user`, `project`, …, 2.1.274+): base trust decisions on it, not on the name prefix (hooks, PreToolUse input).

**Plugin-provided servers** (mcp, Plugin-provided MCP servers; plugins-reference, Hooks):

- Tool name: `mcp__plugin_<plugin>_<server>__<tool>`, characters outside `A-Za-z0-9_-` replaced by `_`. The `search` server of `shop-kit` exposes `mcp__plugin_shop-kit_search__query`.
- **A matcher, permission rule, `allowed-tools` or agent `tools` entry written against the bare key (`mcp__search__.*`) never fires.** Nothing warns.
- The *server* registers as `plugin:<plugin>:<server>` — the form an `mcp_tool` hook's `server` field takes.
- Placeholders `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_PROJECT_DIR}` resolve in `command`/`args`/`env` (stdio) and `url`/`headers`/`headersHelper` (remote).

## Context cost

- **Tool search is on by default**: only tool names and server instructions load at session start; definitions are fetched on demand through `ToolSearch` (mcp, Scale with MCP tool search). No per-server tool cap.
- It is **off**, and every tool definition loads upfront, when `ANTHROPIC_BASE_URL` is a non-first-party host, with `ENABLE_TOOL_SEARCH=false`, with `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, on pre-4.5 models on Google Cloud's Agent Platform, and on Azure-hosted Foundry (mcp, Configure tool search). `ENABLE_TOOL_SEARCH=auto[:N]` loads upfront below N % (default 10) of the window.
- Without tool search, a request that needs a still-connecting server waits through **`WaitForMcpServers`**; with it, the wait happens inside `ToolSearch` (mcp, Tool availability).
- **`alwaysLoad: true`** on a server (or `_meta["anthropic/alwaysLoad"]` on a tool) bypasses deferral: every definition is paid every turn, and startup waits up to 5 s for that server (mcp, Exempt a server from deferral). An audit question, not an error: which tool is needed on *every* turn?
- Each tool description and each server's instructions are truncated at 2,048 characters; `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` changes it (2.1.280+) (mcp, For MCP server authors).
- Tool **output**: warning above 10,000 tokens, limit 25,000 (`MAX_MCP_OUTPUT_TOKENS`); over the limit the result goes to a file and the conversation gets a path (mcp, MCP output limits).
- A tool whose input schema fails the API's checks is excluded alone, not the whole server — when the feature flag arrived; otherwise the whole request 400s (mcp, Tools with invalid input schemas).

**House:** `audit.py` does not measure MCP context cost; it cannot see the tool list without connecting.

## Organisation controls

(managed-mcp)

- `managed-mcp.json` (system path) is **exclusive**: only its servers, `managedMcpServers` and in-process app servers load; plugin servers and `--mcp-config` are dropped.
- `allowedMcpServers` / `deniedMcpServers` filter, they do not deploy. Denylist merges from every scope and always wins. Without `allowManagedMcpServersOnly: true`, a user's own allowlist broadens the managed one. `allowedMcpServers: []` allows nothing; unset allows everything.
- `serverName` entries are labels, not controls; use `serverUrl` / `serverCommand`.
- A managed server that uses `${VAR}` is still checked against the allowlist.

## What audit.py checks, and what it does not

| Check | Reads | Fires on |
| --- | --- | --- |
| `43-mcp-shape` | `.mcp.json` at the root | invalid JSON (ERROR); `url` without `type` (ERROR); `type: sse` (INFO) |
| `43-mcp-secret` | same, `url`/`headers`/`env`/`args` | literal-looking token without `${` (WARN) |
| `43-mcp-credential-var` | same, `url`/`headers` | one of the five documented protected names (ERROR) |
| `43-mcp-approval` | shared `.claude/settings.json` | `enableAllProjectMcpServers` / `enabledMcpjsonServers` committed (WARN) |
| `35-hooks-matcher` | hook configs | matcher shapes, including a bare `mcp__<server>` |

**Not checked** (read it by hand, or run the tool that sees it): servers in `~/.claude.json` (outside the repository); servers inline in `plugin.json`; hook matchers or permission rules written against a plugin server's bare key; allow rules of the form `mcp__*`; `alwaysLoad` cost; whether a `${VAR}` is actually set (`claude mcp list` says so).
