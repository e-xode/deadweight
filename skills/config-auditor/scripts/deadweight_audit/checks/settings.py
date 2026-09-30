"""Settings: scope, keys, permission rules."""
from __future__ import annotations

import json
import re
import subprocess

from ..checks.hooks import hook_paths
from ..checks.mcp import SENSITIVE_ENV_RE
from ..context import AuditContext
from ..parsing.frontmatter import parse_frontmatter
from ..repo import readable_files, git_ignored
from ..report import Report
from ..vocabulary.hooks import HOOK_PROJECT_DIR_VARS
from ..vocabulary.settings import (
    BUILTIN_OUTPUT_STYLES,
    PROJECT_SCOPE_IGNORED_MODES,
    SETTINGS_KEYS_GLOBAL,
    SETTINGS_KEYS_MANAGED,
    SETTINGS_KEYS_USER_LOCAL_MANAGED,
    SETTINGS_KEYS_USER_MANAGED,
    SETTINGS_KNOWN_KEYS,
    SETTINGS_OBJECT_FIELDS,
    SETTINGS_PROJECT_IGNORED_FALSE,
)
from ..vocabulary.tools import KNOWN_TOOLS, TOOL_ALIASES


def check_settings_scope(ctx: AuditContext, report: Report) -> None:
    """Settings keys that are silently ignored at project scope, and dangling overrides."""
    root = ctx.root
    for name in ("settings.json", "settings.local.json"):
        path = root / ctx.claude_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.add("24-settings-parse", "ERROR", f"'{name}' is not valid JSON: {exc}", str(path))
            continue
        if not isinstance(data, dict):
            report.add("24-settings-parse", "ERROR", f"'{name}' does not hold a JSON object.", str(path))
            continue

        report.add(
            "24-settings-keys",
            "INFO",
            f"'{name}' top-level keys: {', '.join(sorted(data)) if data else '(none)'}.",
            str(path),
        )

        permissions = data.get("permissions")
        mode = str(permissions.get("defaultMode", "")).strip() if isinstance(permissions, dict) else ""
        if mode in PROJECT_SCOPE_IGNORED_MODES:
            report.add(
                "24-settings-default-mode",
                "WARN",
                f"'permissions.defaultMode: {mode}' in '{name}' is ignored at project scope since "
                "Claude Code 2.1.257 — set it in user or managed settings, or pass --permission-mode.",
                str(path),
            )

        overrides = data.get("skillOverrides")
        if isinstance(overrides, dict):
            for skill_name in sorted(overrides):
                if not (root / ctx.skills_dir / skill_name / "SKILL.md").is_file():
                    # The docs' own example is `"doctor": "off"` - a bundled skill. A key
                    # outside the project may be bundled, personal or synced: legitimate,
                    # and not verifiable from here.
                    report.add(
                        "24-settings-skill-overrides",
                        "NOTICE",
                        f"skillOverrides in '{name}' names '{skill_name}', which is not a project "
                        "skill: fine for a bundled, user or synced skill, dead if it was renamed.",
                        str(path),
                    )


# --- Settings and permissions -----------------------------------------------
def _rule_tool(rule: str) -> str:
    return rule.split("(", 1)[0].strip()


def check_settings_semantics(ctx: AuditContext, report: Report) -> None:
    """What a settings file says and the harness does not do - silently.

    Every finding here is a line that looks like configuration and is not: a key
    ignored at its scope, an allow rule that approves nothing, an approval a
    cloned repository cannot grant itself. None of them produces an error at
    runtime; the file simply means less than it says.
    """
    root = ctx.root
    for name in ("settings.json", "settings.local.json"):
        path = root / ctx.claude_dir / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue                      # 24-settings-parse already reports it
        if not isinstance(data, dict):
            continue
        shared = name == "settings.json"
        for key in sorted(data):
            if key.startswith("$"):
                continue
            if key not in SETTINGS_KNOWN_KEYS:
                report.add("24-settings-unknown-key", "NOTICE",
                           f"'{key}' in '{name}' is not in the settings reference ({len(SETTINGS_KNOWN_KEYS)} keys, "
                           "2026-09-30): a typo, or a key newer than this auditor.", str(path))
                continue
            fields = SETTINGS_OBJECT_FIELDS.get(key)
            if fields and isinstance(data[key], dict):
                for sub in sorted(set(data[key]) - fields):
                    report.add("24-settings-unknown-subkey", "NOTICE",
                               f"'{key}.{sub}' in '{name}' is not a field of `{key}` in the "
                               f"settings reference ({', '.join(sorted(fields))}): it is ignored "
                               "without a word, so whatever it was meant to turn off stays on.",
                               str(path))
            barred = (SETTINGS_KEYS_MANAGED | SETTINGS_KEYS_USER_MANAGED | SETTINGS_KEYS_GLOBAL
                      | (SETTINGS_KEYS_USER_LOCAL_MANAGED if shared else frozenset()))
            if key in barred:
                where = ("managed settings" if key in SETTINGS_KEYS_MANAGED else
                         "~/.claude.json" if key in SETTINGS_KEYS_GLOBAL else
                         "user settings" + ("" if key in SETTINGS_KEYS_USER_MANAGED
                                            else " or .claude/settings.local.json"))
                report.add("24-settings-scope", "ERROR",
                           f"'{key}' in '{name}' is ignored at this scope, without a word: it "
                           f"takes effect from {where} only (settings-reference, Scope).",
                           str(path))
            if shared and key in SETTINGS_PROJECT_IGNORED_FALSE and data[key] is False:
                report.add("24-settings-scope", "ERROR",
                           f"'{key}: false' in the shared settings.json is ignored: this opt-out "
                           "applies from user, local or managed settings only (settings).",
                           str(path))
        if shared:
            for key in ("enableAllProjectMcpServers", "enabledMcpjsonServers"):
                if key in data:
                    report.add("43-mcp-approval", "WARN",
                               f"'{key}' is committed in the shared settings.json: a cloned "
                               "repository cannot approve its own MCP servers until the workspace "
                               "is trusted, and an approval shipped with the code is how "
                               "CVE-2025-59536 worked. Approvals belong in settings.local.json.",
                               str(path))
            env = data.get("env")
            if isinstance(env, dict):
                for var in sorted(env):
                    if SENSITIVE_ENV_RE.match(var):
                        report.add("24-settings-env", "WARN",
                                   f"'env.{var}' is set in the shared settings.json: every clone "
                                   "sends its requests or credentials where this file says "
                                   "(Check Point Research, CVE-2026-21852). Keep it in user or "
                                   "local settings.", str(path))
        else:
            ign = git_ignored(root)
            if (root / ".git").exists() and not ign(f"{ctx.claude_dir}/settings.local.json"):
                tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch",
                                          f"{ctx.claude_dir}/settings.local.json"],
                                         capture_output=True).returncode == 0
                report.add("24-settings-local", "WARN",
                           "settings.local.json " + ("is COMMITTED: everyone who clones gets "
                           "these personal approvals and overrides" if tracked else
                           "is not ignored by git: it holds personal approvals and overrides")
                           + ", and Claude Code only adds it to .gitignore when it creates the "
                           "file itself (settings).", str(path))

        perms = data.get("permissions")
        if isinstance(perms, dict):
            lists = {k: [r for r in (perms.get(k) or []) if isinstance(r, str)]
                     for k in ("allow", "ask", "deny")}
            for rule in sorted(set(lists["allow"]) & (set(lists["deny"]) | set(lists["ask"]))):
                report.add("42-permissions-conflict", "WARN",
                           f"'{rule}' is both allowed and denied/asked in '{name}': deny, then ask, "
                           "then allow - the allow entry never applies (permissions).", str(path))
            for rule in lists["allow"]:
                tool = _rule_tool(rule)
                # The specifier runs from the FIRST `(` to the closing one: `[^)]*` stopped at
                # the first `)` inside `Bash(grep "[\);}]" ...)` and read the rest of the
                # command as a bare glob (2 false ERRORs, second public sample, 2026-09-27).
                outside = (rule.split("(", 1)[0] if "(" in rule and rule.rstrip().endswith(")")
                           else re.sub(r"\([^)]*\)", "", rule))
                if "*" in outside and not re.match(r"mcp__[A-Za-z0-9_-]+__", outside):
                    report.add("42-permissions-rule", "ERROR",
                               f"allow rule '{rule}' in '{name}' is an unanchored glob: it is "
                               "skipped with a warning and approves nothing. Globs are accepted "
                               "only after a literal `mcp__<server>__` prefix (permissions).",
                               str(path))
                    continue
                if (tool not in KNOWN_TOOLS and tool not in TOOL_ALIASES
                        and not tool.startswith("mcp__")):
                    report.add("42-permissions-rule", "WARN",
                               f"allow rule '{rule}' in '{name}' names no known tool: unlike a "
                               "deny or ask rule, a mistyped allow rule raises no startup "
                               "warning - it just approves nothing (permissions).", str(path))
            for kind, rules in lists.items():
                for rule in rules:
                    # "Claude Code checks file permissions against Edit(path) and Read(path)
                    # rules only. If you write a path rule for Write, NotebookEdit, Glob, or
                    # the legacy MultiEdit tool instead, Claude Code accepts the rule but never
                    # consults it" (permissions). 19 of 600 public repositories, 2026-09-27.
                    m_path = re.match(r"^(Write|NotebookEdit|Glob|MultiEdit)\((.+)\)$", rule.strip())
                    if m_path:
                        tool_name = "Read" if m_path.group(1) == "Glob" else "Edit"
                        report.add("42-permissions-rule", "ERROR",
                                   f"{kind} rule '{rule}' in '{name}' is never consulted: file "
                                   f"permissions are checked against Edit(...) and Read(...) only. "
                                   f"Write it {tool_name}({m_path.group(2)}) (permissions).", str(path))
                        continue
                    if rule.startswith("mcp__") and "(" in rule:
                        report.add("42-permissions-rule", "ERROR",
                                   f"{kind} rule '{rule}' in '{name}': Claude Code skips any "
                                   "`mcp__` rule that has parentheses when it loads a settings "
                                   "file (permissions).", str(path))
                    elif re.search(r":\*\s*\S", rule.split("(", 1)[-1].rstrip(")")):
                        report.add("42-permissions-rule", "WARN",
                                   f"{kind} rule '{rule}' in '{name}': `:*` is recognised only at "
                                   "the end of a pattern; here the colon is literal and the rule "
                                   "matches nothing it seems to (permissions).", str(path))

        sl = data.get("statusLine")
        if isinstance(sl, dict):
            ri = sl.get("refreshInterval")
            if isinstance(ri, (int, float)) and ri < 1:
                report.add("24-settings-statusline", "ERROR",
                           f"statusLine.refreshInterval is {ri} in '{name}': the minimum is 1 "
                           "(statusline).", str(path))
            for token in hook_paths(str(sl.get("command", ""))):
                resolved = token
                for var in HOOK_PROJECT_DIR_VARS:
                    resolved = resolved.replace(var, "")
                resolved = resolved[2:] if resolved.startswith("./") else resolved.lstrip("/")
                if not (root / resolved).exists():
                    report.add("24-settings-statusline", "WARN",
                               f"statusLine command in '{name}' runs '{token}', which does not "
                               "exist: a status line that fails goes blank (statusline).",
                               str(path))
        style = data.get("outputStyle")
        if isinstance(style, str) and style:
            custom = {p.stem for d in (root / ctx.claude_dir / "output-styles",)
                      if d.is_dir() for p in readable_files(d.glob("*.md"))}
            for d in (root / ctx.claude_dir / "output-styles",):
                if d.is_dir():
                    for p in readable_files(d.glob("*.md")):
                        fm, _ = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
                        if fm and fm.get("name"):
                            custom.add(fm["name"].strip())
            if style not in BUILTIN_OUTPUT_STYLES | custom:
                near = [x for x in BUILTIN_OUTPUT_STYLES | custom if x.lower() == style.lower()]
                if near or not custom:
                    report.add("24-settings-output-style", "WARN" if near else "NOTICE",
                               f"outputStyle '{style}' in '{name}' "
                               + (f"differs from '{near[0]}' only by case: a value that does not "
                                  "match exactly gives the Default style (output-styles)."
                                  if near else "matches no built-in or project style - fine if "
                                  "it is a user or plugin style."), str(path))
