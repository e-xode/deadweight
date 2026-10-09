"""`.mcp.json`: secrets, credentials, approvals."""
from __future__ import annotations

import json
import re

from ..checks.security import SECRET_LITERAL_RE
from ..context import AuditContext
from ..report import Report


# Names that route requests or carry credentials. In a committed project file they
# redirect or leak for everyone who clones it (Check Point Research, CVE-2026-21852).
SENSITIVE_ENV_RE = re.compile(r"^(ANTHROPIC_(BASE_URL|API_KEY|AUTH_TOKEN|CUSTOM_HEADERS)"
                              r"|.*(_TOKEN|_API_KEY|_SECRET|PASSWORD))$")


# "The covered names are" ... credentials read as EMPTY in an MCP url or header (mcp). The
# docs give five as examples ("such as"); the second line is MEASURED on 2.1.294
# (2026-10-08): each reached a local http server as an empty header, set or unset, with or
# without a :-default, while AWS_ACCESS_KEY_ID, GITHUB_TOKEN and a name of one's own expanded.
MCP_EMPTY_CREDENTIAL_VARS = re.compile(
    r"\$\{(ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|AWS_BEARER_TOKEN_BEDROCK|HTTPS_PROXY|NPM_TOKEN"
    r"|AWS_SESSION_TOKEN|AWS_SECRET_ACCESS_KEY|CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_FOUNDRY_API_KEY"
    r"|ANTHROPIC_CUSTOM_HEADERS|AZURE_CLIENT_SECRET|GOOGLE_APPLICATION_CREDENTIALS|NODE_AUTH_TOKEN"
    r")(:-[^}]*)?\}")
MCP_DOCUMENTED_EMPTY = frozenset({"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "AWS_BEARER_TOKEN_BEDROCK",
                                  "HTTPS_PROXY", "NPM_TOKEN"})


# --- MCP ----------------------------------------------------------------------
def check_mcp(ctx: AuditContext, report: Report) -> None:
    """Project MCP servers (`.mcp.json`): the configuration that holds secrets.

    It is committed by design - shared with everyone who clones - which is what
    makes a literal token in it a leak, and a credential variable in a URL a
    header sent empty.
    """
    root = ctx.root
    path = root / ".mcp.json"
    if not path.is_file():
        return
    try:
        # utf-8-sig, like every JSON file this script reads: Claude Code reads a .mcp.json
        # that opens on a UTF-8 BOM and lists its servers (`claude mcp list`), and applies
        # a BOM-prefixed settings.json (its `env` reached a Bash call), 2026-09-27. Fixed
        # first for .mcp.json alone - the one file measured - and the next fresh sample
        # found the same BOM in a settings.json: the defect was the reader, not the file.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        report.add("43-mcp-shape", "ERROR", f"'.mcp.json' is not valid JSON: {exc}", str(path))
        return
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return
    for srv, conf in sorted(servers.items()):
        if not isinstance(conf, dict):
            continue
        if conf.get("url") and not conf.get("type"):
            report.add("43-mcp-shape", "ERROR",
                       f"MCP server '{srv}' has a url and no type: Claude Code skips it (mcp).",
                       str(path))
        if str(conf.get("type", "")).lower() == "sse":
            report.add("43-mcp-shape", "NOTICE",
                       f"MCP server '{srv}' uses the SSE transport, which is deprecated (mcp).",
                       str(path))
        blobs = [("url", conf.get("url"))]
        blobs += [(f"headers.{k}", v) for k, v in (conf.get("headers") or {}).items()]
        blobs += [(f"env.{k}", v) for k, v in (conf.get("env") or {}).items()]
        blobs += [(f"args[{i}]", v) for i, v in enumerate(conf.get("args") or [])]
        for where, val in blobs:
            if not isinstance(val, str):
                continue
            if SECRET_LITERAL_RE.search(val) and "${" not in val:
                # ERROR since 0.18.0: a credential in a committed file has leaked to every
                # clone - more serious than most ERRORs here, and it was a WARN beside an
                # agent missing its description (600 public repositories, 2026-09-27).
                report.add("43-mcp-secret", "ERROR",
                           f"MCP server '{srv}' {where} holds what looks like a literal "
                           "credential in a file every clone receives. Reference an environment "
                           "variable instead: \"${VAR}\" (mcp).", str(path))
            if where == "url" or where.startswith("headers."):
                m = MCP_EMPTY_CREDENTIAL_VARS.search(val)
                if m:
                    report.add("43-mcp-credential-var", "ERROR",
                               f"MCP server '{srv}' {where} uses ${{{m.group(1)}}}: in a remote "
                               "server's url and headers this name reads as EMPTY, whether set "
                               "or not, and a :-default is ignored (" + (
                                   "mcp" if m.group(1) in MCP_DOCUMENTED_EMPTY else
                                   "measured on Claude Code 2.1.294; the mcp docs list examples") + ").",
                               str(path))
