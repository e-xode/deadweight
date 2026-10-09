"""Settings: scope, keys, permission rules."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..checks.hooks import HOME_PREFIXES, hook_paths
from ..checks.mcp import SENSITIVE_ENV_RE
from ..context import AuditContext
from ..parsing.frontmatter import parse_frontmatter
from ..repo import readable_files, git_ignores, git_tracked
from ..report import Report
from ..vocabulary.hooks import HOOK_PROJECT_DIR_VARS
from ..vocabulary.settings import (
    BUILTIN_OUTPUT_STYLES,
    PROJECT_SCOPE_IGNORED_MODES,
    SETTINGS_KEYS_GLOBAL,
    SETTINGS_KEYS_IGNORED_SILENTLY,
    SETTINGS_KEYS_IGNORED_WITH_WARNING,
    SETTINGS_KEYS_MANAGED,
    SETTINGS_KEYS_USER_LOCAL_MANAGED,
    SETTINGS_KEYS_USER_MANAGED,
    SETTINGS_KNOWN_KEYS,
    SETTINGS_OBJECT_FIELDS,
    SETTINGS_PROJECT_IGNORED_FALSE,
    SETTINGS_PROJECT_TURNS_OFF,
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
def _dotted_keys(prefix: str, value: object) -> list[str]:
    """Every nested key of a settings object, as the reference spells it: `sandbox.network.x`."""
    if not isinstance(value, dict):
        return []
    out: list[str] = []
    for sub in sorted(value):
        dotted = f"{prefix}.{sub}"
        out.append(dotted)
        out.extend(_dotted_keys(dotted, value[sub]))
    return out


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
            if shared and key in SETTINGS_PROJECT_IGNORED_FALSE and data[key] is False:
                # One misplaced line, one finding: this one is the more precise of the two.
                report.add("24-settings-scope", "ERROR",
                           f"'{key}: false' in the shared settings.json is ignored: this opt-out "
                           "applies from user, local or managed settings only (settings).",
                           str(path))
                continue
            acting = SETTINGS_PROJECT_TURNS_OFF.get(key, ...)
            if acting is None or (acting is not ... and data[key] is acting):
                value = json.dumps(data[key])
                if key == "autoContinueAtUsageLimit" and data[key] is not False:
                    report.add("24-settings-scope", "ERROR",
                               f"'{key}: {value}' in '{name}' is not ignored: it turns the feature "
                               "OFF. The value counts from user settings, `--settings` and managed "
                               "settings only; while none of those sets the key, a project or local "
                               "file that sets it turns the feature off (settings-reference, Scope).",
                               str(path))
                else:
                    report.add("24-settings-scope", "NOTICE",
                               f"'{key}: {value}' in '{name}' turns the feature off only while no "
                               "higher-scope file (user settings, `--settings`, managed settings) "
                               "sets the key; a `true` in this file would not turn it on "
                               "(settings-reference, Scope).",
                               str(path))
                continue
            # The scope tables hold dotted entries too (`sandbox.bwrapPath`, Managed): a
            # nested key is judged by its own path, and a barred parent covers its children.
            for dotted in [key] + (_dotted_keys(key, data[key]) if key not in barred else []):
                if dotted not in barred:
                    continue
                where = ("managed settings" if dotted in SETTINGS_KEYS_MANAGED else
                         "~/.claude.json" if dotted in SETTINGS_KEYS_GLOBAL else
                         "user settings" + ("" if dotted in SETTINGS_KEYS_USER_MANAGED
                                            else " or .claude/settings.local.json"))
                loud = (", with a warning" if dotted in SETTINGS_KEYS_IGNORED_WITH_WARNING
                        else ", without a word" if dotted in SETTINGS_KEYS_IGNORED_SILENTLY
                        else "")
                report.add("24-settings-scope", "ERROR",
                           f"'{dotted}' in '{name}' is ignored at this scope{loud}: it "
                           f"takes effect from {where} only (settings-reference, Scope).",
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
                                   f"'env.{var}' is set in the shared settings.json: once a clone's "
                                   "workspace is trusted - or at once in a `-p` run, which shows "
                                   "no trust dialog - its requests or credentials go where this "
                                   "file says (settings-reference, env; Check Point Research, "
                                   "CVE-2026-21852). Keep it in user or local settings.", str(path))
        else:
            # Asked of git, not of `root / ".git"`: audited from a subfolder of a repository,
            # a committed file read as "not ignored", and a machine without git crashed the
            # check (external audit 3, 2026-10-08). Outside a repository, or when git cannot
            # answer, nothing is said.
            rel_local = f"{ctx.claude_dir}/settings.local.json"
            state = git_tracked(root, rel_local)
            tracked = state == "tracked"
            if tracked or (state == "untracked" and not git_ignores(root, rel_local)):
                report.add("24-settings-local", "WARN",
                           "settings.local.json " + ("is COMMITTED: everyone who clones gets "
                           "these personal approvals and overrides" if tracked else
                           "is not ignored by this repository's git rules: it holds personal "
                           "approvals and overrides. A global git exclude is not counted, on "
                           "purpose - it protects one machine, not the next clone")
                           + ". Claude Code adds it to your global git excludes the first time it "
                           "writes the file; created by hand, it is yours to add to .gitignore "
                           "(settings).", str(path))

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
                # The whole Agent tool: Manual mode does not list it among the tools that
                # ask (permissions), sub-agents started with no rule at all in default and
                # dontAsk modes (claude -p, 2026-10-09), and auto mode drops `Agent` allow
                # rules (permission-modes). Restricting is done with deny or ask rules.
                if rule.strip() in ("Agent", "Agent(*)"):
                    report.add("42-permissions-rule", "NOTICE",
                               f"allow rule '{rule}' in '{name}' has no measured effect: "
                               "sub-agents start without it in default and dontAsk modes, and "
                               "auto mode drops it. To limit sub-agents, deny or ask "
                               "`Agent(<name>)` instead (permissions, permission-modes).",
                               str(path))
                    continue
                # `MultiEdit(<path>)` is a path rule for the legacy tool: the never-consulted
                # ERROR below says what to write. Two findings, "write it Edit(...)" and "names
                # no known tool", contradicted each other (user report, 2026-10-09).
                if (tool not in KNOWN_TOOLS and tool not in TOOL_ALIASES
                        and not tool.startswith("mcp__")
                        and not re.match(r"^MultiEdit\(.+\)$", rule.strip())):
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
                        # The advice must not stay wrong: `Write(/abs/**)` became `Edit(/abs/**)`,
                        # still anchored at the settings source (anthropics/claude-code#98443).
                        home = _home_variable(m_path.group(2))
                        fixed = home or _absolute_path(m_path.group(2), root, ctx, name)
                        report.add("42-permissions-rule", "ERROR",
                                   f"{kind} rule '{rule}' in '{name}' is never consulted: file "
                                   f"permissions are checked against Edit(...) and Read(...) only. "
                                   f"Write it {tool_name}({fixed or m_path.group(2)})"
                                   + (f" - with `~/`: `$HOME` {_HOME_NOT_EXPANDED}" if home else
                                      " - with `//`: a single leading `/` anchors at the settings "
                                      "source, not the filesystem root" if fixed else "")
                                   + " (permissions).", str(path))
                        continue
                    m_rw = re.match(r"^(Read|Edit)\((.+)\)$", rule.strip())
                    home = _home_variable(m_rw.group(2)) if m_rw else None
                    if home:
                        report.add("42-permissions-rule", "WARN",
                                   f"{kind} rule '{rule}' in '{name}' names `$HOME`, which "
                                   f"{_HOME_NOT_EXPANDED}, so the rule does not apply to the home "
                                   f"directory. Write {m_rw.group(1)}({home}) (permissions).",
                                   str(path))
                        continue
                    fixed = _absolute_path(m_rw.group(2), root, ctx, name) if m_rw else None
                    if fixed:
                        report.add("42-permissions-path-anchor", "WARN",
                                   f"{kind} rule '{rule}' in '{name}': a single leading `/` is "
                                   "\"relative to the settings source\", not the filesystem root - "
                                   f"'{m_rw.group(2)}' is looked up under {_settings_source(name)}. "
                                   f"For an absolute path write {m_rw.group(1)}({fixed}) (permissions).",
                                   str(path))
                    if rule.startswith("mcp__") and "(" in rule:
                        report.add("42-permissions-rule", "ERROR",
                                   f"{kind} rule '{rule}' in '{name}': Claude Code skips any "
                                   "`mcp__` rule that has parentheses when it loads a settings "
                                   "file (permissions).", str(path))
                    # Command patterns only: `WebFetch(domain:*.example.com)` and
                    # `Agent(model:*)` use a `param:` prefix where `*` is a plain wildcard.
                    elif (_rule_tool(rule) in ("Bash", "PowerShell")
                          and re.search(r":\*\s*\S", rule.split("(", 1)[-1].rstrip(")"))):
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
                # Resolved as the hooks check does: `~/.claude/statusline.sh` is the docs' own
                # example, and an absolute path is a path - neither lives under the repository.
                resolved = token
                for var in HOOK_PROJECT_DIR_VARS:
                    resolved = resolved.replace(var, str(root))
                outside = token.startswith(HOME_PREFIXES) or token.startswith("/")
                for pre in HOME_PREFIXES:
                    if resolved.startswith(pre):
                        resolved = str(Path.home() / resolved[len(pre):])
                resolved = resolved[2:] if resolved.startswith("./") else resolved
                target = Path(resolved) if resolved.startswith("/") else root / resolved
                if not target.exists():
                    report.add("24-settings-statusline", "WARN",
                               f"statusLine command in '{name}' runs '{token}', which does not "
                               "exist" + (" on this machine" if outside else "")
                               + ": a status line that fails goes blank (statusline).",
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
            # `default` in any case gives the Default style, which is what it asks for
            # (output-styles: "`default` appears in the `/output-style` list").
            if style not in BUILTIN_OUTPUT_STYLES | custom and style.lower() != "default":
                near = [x for x in BUILTIN_OUTPUT_STYLES | custom if x.lower() == style.lower()]
                if near or not custom:
                    report.add("24-settings-output-style", "WARN" if near else "NOTICE",
                               f"outputStyle '{style}' in '{name}' "
                               + (f"differs from '{near[0]}' only by case: a value that does not "
                                  "match exactly gives the Default style (output-styles)."
                                  if near else "matches no built-in or project style - fine if "
                                  "it is a user or plugin style."), str(path))


# Top-level folders of an absolute path on macOS, Linux or WSL. A rule that starts with one of
# them after a SINGLE slash almost always meant the filesystem root (permissions: "A pattern like
# `/Users/alice/file` isn't an absolute path ... Use `//Users/alice/file`").
SYSTEM_ROOTS = ("Users", "home", "opt", "tmp", "private", "var", "etc", "mnt", "srv", "root",
                "Volumes", "usr", "Library", "Applications")


def _settings_source(name: str) -> str:
    return "~/.claude/" if name.startswith("~") else "the project root"


# The permissions page names four path forms - `//` absolute, `~/` home, `/` relative to the
# settings source, and relative - and no variable. Probe, Claude Code 2.1.295 (2026-10-09,
# `claude -p` with --settings, one run each): a deny on `Read($HOME/probe/secret.txt)` let the
# file be read, a deny on `Read(~/probe/secret.txt)` refused it.
_HOME_NOT_EXPANDED = ("is not expanded in a permission rule (a deny on Read($HOME/...) did not "
                      "block the read on Claude Code 2.1.295; `~/` is the home directory)")


def _home_variable(spec: str) -> str | None:
    """`~/<rest>` when a rule's path starts with `$HOME/` or `${HOME}/`, else None."""
    m = re.match(r"^\$(?:HOME|\{HOME\})/(.*)$", spec.strip())
    return f"~/{m.group(1)}" if m else None


def _absolute_path(spec: str, root, ctx, name: str) -> str | None:
    """`//<path>` when `spec` is a single-slash path that names a system folder, else None.

    `Edit(/src/**)` in project settings is legitimate, and so is `/home/**` in a project that has
    a `home/` folder: a folder that exists under the settings source is never flagged.
    """
    m = re.match(r"^/([A-Za-z]+)(/|$)", spec)
    if not m or spec.startswith("//") or m.group(1) not in SYSTEM_ROOTS:
        return None
    if (root / m.group(1)).exists():
        return None
    return "/" + spec