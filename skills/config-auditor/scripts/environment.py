#!/usr/bin/env python3
"""What your environment adds to a session's context, beyond the project's own files.

    python3 environment.py                    # estimate, from file sizes, for the project in cwd
    python3 environment.py --root <project> --json
    python3 environment.py --measure          # four `claude -p` runs on Haiku: costs a few cents

A separate command, not an option of audit.py, for the reason semantic.py is one: what it reports
is information about one user's machine (their account's skills, the plugins they enabled, the MCP
servers they connected), not a property of the repository. It raises no finding, is never counted
and never reaches a floor, and the auditor that counts (audit.py and deadweight_audit/) is not
touched by it - its sha, and every floor taken with it, stays as it is. It imports the auditor's
helpers so the project part is computed exactly as check 17 computes it.

Read-only, no network. It refuses to open the files that hold credentials or MCP secrets: the
credentials file in the configuration directory and the per-user state file `.claude.json` (which
holds the MCP servers a user added with `claude mcp add`). Every open of this process during the
report goes through refused(): by name, by the name of the resolved real path (a symbolic link),
and by file identity (a hard link) with those files - see refused() for exactly what it covers.
Those servers are therefore not counted, and the report says so. `--measure` runs `claude`, which
authenticates itself; this script reads no token and sets no environment variable. But `claude -p`
in the project runs that project's hooks, connects its .mcp.json servers and loads the enabled
plugins' mods, with no trust dialog: it asks first, and says so. See references/environment.md.
"""
from __future__ import annotations

import argparse
import builtins
import contextlib
import errno
import fnmatch
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadweight_audit.checks.agents import check_agents  # noqa: E402
from deadweight_audit.checks.budget import (entry_chars, listed_commands,  # noqa: E402
                                            listing_cap, listing_hidden_skills, project_settings)
from deadweight_audit.checks.skills import check_skills  # noqa: E402
from deadweight_audit.context import AuditContext  # noqa: E402
from deadweight_audit.layout import apply_layout  # noqa: E402
from deadweight_audit.limits import DESCRIPTION_LISTING_MAX_CHARS  # noqa: E402
from deadweight_audit.parsing.frontmatter import (YAML_TRUE, frontmatter_list,  # noqa: E402
                                                  parse_frontmatter)
from deadweight_audit.parsing.markdown import injected_memory, memory_imports  # noqa: E402
from deadweight_audit.repo import project_memory_files, readable_files  # noqa: E402
from deadweight_audit.report import Report  # noqa: E402

# Measured on this plugin's own skill description (characters / tokens reported by the API):
# a rough ratio, kept here and printed with every estimate. Prose in another language, code or
# tables tokenise differently.
CHARS_PER_TOKEN_ROUGH = 2.85

# Refused, by name and by real path: they hold credentials or MCP secrets.
FORBIDDEN_NAMES = {".claude.json", ".credentials.json", ".env"}

# "Imported files can recursively import other files, with a maximum depth of four hops." (memory)
IMPORT_MAX_HOPS = 4

# The extensions the mods reference accepts for a hooks module.
MOD_EXTENSIONS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx")

PROMPT = "Reply with the single word OK."
DEFAULT_MODEL = "claude-haiku-5-5"
CONDITIONS = (
    ("bare", ["--setting-sources", "", "--strict-mcp-config"]),
    ("project", ["--setting-sources", "project", "--strict-mcp-config"]),
    ("all settings, no MCP", ["--strict-mcp-config"]),
    ("all settings", []),
)


# --------------------------------------------------------------------------- reading


def config_dir() -> Path:
    """The user configuration directory: CLAUDE_CONFIG_DIR, else ~/.claude."""
    named = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(named).expanduser() if named else Path.home() / ".claude"


def sensitive_files() -> list[Path]:
    """The real credential and state files of this configuration. Only stat()ed, never opened."""
    cfg = config_dir()
    return [Path.home() / ".claude.json", cfg / ".claude.json", cfg / ".credentials.json"]


REFUSED: list[str] = []


def refused(path) -> bool:
    """True for a path this script must not open. Three tests, none of which opens a file:
    its own name, the name of its resolved real path (os.path.realpath: a symbolic link, or a
    folder link on the way, to .claude.json), and its file identity (os.path.samefile, a stat of
    both sides: a hard link under another name) against the configuration's .claude.json and
    credentials file when they exist. A copy of their content in another file is not detected."""
    if isinstance(path, int):
        return False
    try:
        p = os.fsdecode(os.fspath(path))
    except TypeError:
        return False
    hit = os.path.basename(p) in FORBIDDEN_NAMES
    if not hit:
        try:
            hit = os.path.basename(os.path.realpath(p)) in FORBIDDEN_NAMES
        except (OSError, ValueError):
            hit = True
    if not hit and os.path.exists(p):
        for s in sensitive_files():
            try:
                if os.path.samefile(p, s):
                    hit = True
                    break
            except (OSError, ValueError):
                continue
    if hit and p not in REFUSED:
        REFUSED.append(p)
    return hit


@contextlib.contextmanager
def opening_guard():
    """Puts refused() in front of open() for the whole report, the auditor's helpers included
    (they open files with pathlib, which calls io.open). A refused file reads as empty, so a
    helper that does not expect an error carries on; a write to one raises."""
    real_open, real_io_open = builtins.open, io.open

    def guard(real):
        def wrapper(file, mode="r", *a, **k):
            if refused(file):
                if any(c in str(mode) for c in "wax+"):
                    raise PermissionError(errno.EACCES, "refused: credential or secret file", str(file))
                return io.BytesIO(b"") if "b" in str(mode) else io.StringIO("")
            return real(file, mode, *a, **k)
        return wrapper

    builtins.open, io.open = guard(real_open), guard(real_io_open)
    try:
        yield
    finally:
        builtins.open, io.open = real_open, real_io_open


def read_text(path: Path) -> str | None:
    """A file's text, or None for a refused file (see refused()) or an unreadable one."""
    if refused(path):
        return None
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None


def follow_imports(first: list[Path], seen: set[str], home_and_absolute: bool) -> list[Path]:
    """The files `first` pulls in through `@path` imports, up to IMPORT_MAX_HOPS hops, each once.
    Imports in code spans and code blocks are skipped (memory_imports). Relative paths resolve
    from the importing file; `~/` and absolute paths only when `home_and_absolute`. Every file is
    read through read_text, so a refused one is neither opened nor followed."""
    found: list[Path] = []
    frontier = list(first)
    for _ in range(IMPORT_MAX_HOPS):
        nxt = []
        for f in frontier:
            text = read_text(f)
            if text is None:
                continue
            for ref in memory_imports(text):
                if ref.startswith("~/"):
                    if not home_and_absolute:
                        continue
                    target = Path.home() / ref[2:]
                elif ref.startswith("/") or os.path.isabs(ref):
                    if not home_and_absolute:
                        continue
                    target = Path(ref)
                else:
                    target = f.parent / ref
                if refused(target):
                    continue
                real = os.path.realpath(target)
                if real in seen or not target.is_file():
                    continue
                seen.add(real)
                found.append(target)
                nxt.append(target)
        frontier = nxt
    return found


def read_json(path: Path):
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def frontmatter(path: Path) -> dict:
    text = read_text(path)
    if text is None:
        return {}
    fm, _ = parse_frontmatter(text)
    return fm or {}


def tokens(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN_ROUGH)


def skill_files(base: Path) -> list[Path]:
    """Every `<name>/SKILL.md` under `base`, at any depth (synced skills sit one level deeper),
    leaving out a SKILL.md nested inside another skill's folder."""
    if not base.is_dir():
        return []
    # Shallowest first, so a skill's own SKILL.md is always seen before one nested in it.
    found = sorted((p for p in base.rglob("SKILL.md") if p.is_file()), key=lambda p: (len(p.parts), p))
    tops: list[Path] = []
    for p in found:
        if not any(t.parent in p.parents for t in tops):
            tops.append(p)
    return tops


def skill_entries(files: list[Path], cap: int = DESCRIPTION_LISTING_MAX_CHARS) -> dict:
    """Listed and withheld skills: description + when_to_use, capped as the listing caps them."""
    listed = withheld = chars = 0
    for f in files:
        fm = frontmatter(f)
        if (str(fm.get("disable-model-invocation", "")).strip().lower() in YAML_TRUE
                or frontmatter_list(fm.get("paths", ""))):
            withheld += 1
            continue
        listed += 1
        chars += min(len(fm.get("description", "").strip()) + len(fm.get("when_to_use", "").strip()), cap)
    return {"skills": listed, "skills_withheld": withheld, "skill_chars": chars}


def agent_entries(files: list[Path]) -> dict:
    chars = n = 0
    for f in files:
        fm = frontmatter(f)
        if not fm:
            continue
        n += 1
        chars += len(fm.get("description", "").strip())
    return {"agents": n, "agent_chars": chars}


def command_entries(files: list[Path]) -> dict:
    """A command is listed like a skill; without a description, its first non-empty line."""
    chars = n = 0
    for f in files:
        text = read_text(f)
        if text is None:
            continue
        fm, end = parse_frontmatter(text)
        fm = fm or {}
        if str(fm.get("disable-model-invocation", "")).strip().lower() in YAML_TRUE:
            continue
        desc = fm.get("description", "").strip()
        if not desc:
            body = text.splitlines()[end + 1:] if fm else text.splitlines()
            desc = next((ln.strip() for ln in body if ln.strip()), "")
        n += 1
        chars += min(len(desc) + len(fm.get("when_to_use", "").strip()), DESCRIPTION_LISTING_MAX_CHARS)
    return {"commands": n, "command_chars": chars}


def _label(path: Path, base: Path) -> str:
    try:
        return Path(os.path.normpath(path)).relative_to(base).as_posix()
    except ValueError:
        return str(path)


def memory_entries(base: Path) -> tuple[int, list[str]]:
    """The user's own memory: CLAUDE.md, the rules with no `paths:` in the config dir, and what
    they import. "User-scope memory files, such as `~/.claude/CLAUDE.md` and `~/.claude/rules/`
    [...] Claude Code loads their imports without the dialog" (memory), `~/` and absolute ones too."""
    total, names, loaded = 0, [], []
    seen: set[str] = set()
    md = base / "CLAUDE.md"
    text = read_text(md) if md.is_file() else None
    if text is not None:
        total += len(text)
        names.append("CLAUDE.md")
        loaded.append(md)
        seen.add(os.path.realpath(md))
    rules = base / "rules"
    if rules.is_dir():
        for f in sorted(rules.rglob("*.md")):
            text = read_text(f)
            if text is None:
                continue
            fm, _ = parse_frontmatter(text)
            if not frontmatter_list((fm or {}).get("paths", "")) and os.path.realpath(f) not in seen:
                seen.add(os.path.realpath(f))
                total += len(text)
                names.append(f"rules/{f.relative_to(rules).as_posix()}")
                loaded.append(f)
    for f in follow_imports(loaded, seen, home_and_absolute=True):
        text = read_text(f)
        if text is not None:
            total += len(text)
            names.append(_label(f, base))
    return total, names


def project_memory(ctx: AuditContext) -> list[tuple[str, int]]:
    """(label, bytes) of the project memory loaded at launch, as check 17 counts it
    (always_loaded_memory): the CLAUDE.md files with HTML comments stripped, the rules with no
    `paths:`, and the CLAUDE.md files' relative imports. Re-done here rather than called, so that
    every file goes through read_text and refused(): the auditor's helper opens an import directly."""
    root = ctx.root
    out: list[tuple[str, int]] = []
    seen: set[str] = set()

    def add(p: Path, injected: bool) -> None:
        real = os.path.realpath(p)
        if real in seen:
            return
        text = read_text(p)
        if text is None:
            return
        seen.add(real)
        try:
            label = p.relative_to(root).as_posix()      # as check 17 labels it
        except ValueError:
            label = str(p)
        out.append((label, len((injected_memory(text) if injected else text).encode("utf-8"))))

    memory = [f for f in project_memory_files(root) if not refused(f)]
    for f in memory:
        add(f, True)
    rules = root / ctx.claude_dir / "rules"
    if rules.is_dir():
        for f in readable_files(rules.rglob("*.md")):
            text = read_text(f)
            if text is None:
                continue
            fm, _ = parse_frontmatter(text)
            if not frontmatter_list((fm or {}).get("paths", "")):
                add(f, False)
    # As check 17: imports of CLAUDE.md files only, relative ones only.
    for f in follow_imports(memory, {os.path.realpath(f) for f in memory}, home_and_absolute=False):
        add(f, False)
    return out


def count_hooks(hooks) -> int:
    """Handlers in a settings-shaped `hooks` map."""
    n = 0
    if isinstance(hooks, dict):
        for groups in hooks.values():
            for g in groups if isinstance(groups, list) else []:
                n += len(g.get("hooks", [])) if isinstance(g, dict) and isinstance(g.get("hooks"), list) else 0
    return n


def context_hooks(hooks) -> int:
    """Handlers on the events whose output can reach the model's context."""
    if not isinstance(hooks, dict):
        return 0
    return count_hooks({k: v for k, v in hooks.items() if k in ("SessionStart", "UserPromptSubmit")})


def mcp_server_names(data) -> list[str]:
    """Server names of an `.mcp.json`-shaped file. Only the keys are kept, never a value."""
    if not isinstance(data, dict):
        return []
    servers = data.get("mcpServers", data)
    return sorted(k for k, v in servers.items() if isinstance(v, dict)) if isinstance(servers, dict) else []


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def plugin_summary(root: Path) -> dict:
    """What one plugin directory adds: skills, commands, agents, MCP servers, hooks, mods."""
    manifest = read_json(root / ".claude-plugin" / "plugin.json") or {}
    if not isinstance(manifest, dict):
        manifest = {}
    # Skills: `skills/` is always scanned and the manifest's `skills` adds to it.
    files = skill_files(root / "skills")
    outside: list[str] = []

    def inside(rel) -> bool:
        # "a path that resolves outside the plugin root doesn't load" (plugins reference)
        if _inside(root / str(rel), root):
            return True
        outside.append(str(rel))
        return False

    for extra in _as_list(manifest.get("skills")):
        if isinstance(extra, str) and inside(extra):
            d = (root / extra).resolve()
            if d == root.resolve() and (root / "SKILL.md").is_file():
                files.append(root / "SKILL.md")
            elif d.is_dir() and d != root.resolve():
                files += [f for f in skill_files(d) if f not in files]
    if not files and not (root / "skills").is_dir() and (root / "SKILL.md").is_file():
        files = [root / "SKILL.md"]
    out = skill_entries(files)
    # Commands and agents: the manifest key REPLACES the default folder.
    cmd_files: list[Path] = []
    if "commands" in manifest and isinstance(manifest["commands"], (str, list)):
        for p in _as_list(manifest["commands"]):
            if not inside(p):
                continue
            q = root / str(p)
            cmd_files += sorted(q.rglob("*.md")) if q.is_dir() else ([q] if q.is_file() else [])
    elif "commands" not in manifest and (root / "commands").is_dir():
        cmd_files = sorted((root / "commands").rglob("*.md"))
    out.update(command_entries(cmd_files))
    if isinstance(manifest.get("commands"), dict):
        out["commands"] += len(manifest["commands"])
        out["command_chars"] += sum(len(str(v.get("description", ""))) for v in manifest["commands"].values()
                                    if isinstance(v, dict))
    if "agents" in manifest:
        agent_files = [root / str(p) for p in _as_list(manifest["agents"])
                       if inside(p) and (root / str(p)).is_file()]
    else:
        agent_files = sorted((root / "agents").rglob("*.md")) if (root / "agents").is_dir() else []
    out.update(agent_entries(agent_files))
    # MCP servers: `.mcp.json` first, then the manifest's `mcpServers` (file paths or inline maps).
    servers = set(mcp_server_names(read_json(root / ".mcp.json")))
    for item in _as_list(manifest.get("mcpServers")):
        if isinstance(item, dict):
            servers |= set(mcp_server_names({"mcpServers": item}))
        elif isinstance(item, str) and item.endswith(".json"):
            if inside(item):
                servers |= set(mcp_server_names(read_json(root / item)))
        elif isinstance(item, str):
            servers.add(f"<bundle {Path(item).name}>")
    out["mcp_servers"] = sorted(servers)
    out["outside_root"] = list(dict.fromkeys(outside))
    # Hooks and mods: hooks/hooks.json, `modules` naming a hooks module (mods reference).
    hooks_file = read_json(root / "hooks" / "hooks.json") or {}
    hooks = hooks_file.get("hooks") if isinstance(hooks_file, dict) else None
    out["hooks"] = count_hooks(hooks) + sum(count_hooks(h) for h in _as_list(manifest.get("hooks"))
                                            if isinstance(h, dict))
    out["context_hooks"] = context_hooks(hooks)
    modules = hooks_file.get("modules") if isinstance(hooks_file, dict) else None
    out["mods"] = [str(m) for m in _as_list(modules)
                   if isinstance(m, str) and m.lower().endswith(MOD_EXTENSIONS)]
    out["mod_modules"] = [read_mod(root, m) for m in out["mods"]]
    return out


# --------------------------------------------------------------------------- mods, read statically
#
# A mod's hooks module is JavaScript or TypeScript. Nothing here runs, imports or evaluates it: the
# source is read as text and matched with regular expressions, so a call written another way, or
# built at run time, is missed. Each category says "may": the code path may never run.
# Event and method names: https://code.claude.com/docs/en/plugins/mods/reference
# (Events, Mods API methods, Limits) and https://code.claude.com/docs/en/plugins/mods/api.

MOD_STATIC_LABEL = "static reading of the source; not a measurement"
MOD_SOURCE_MAX_BYTES = 2 * 1024 * 1024
MOD_MAX_FILES = 20

MOD_CATEGORIES = {
    "context": "may add tokens to the model's context",
    "model": "calls a model on the user's plan or API key, outside this session's context",
    "draws": "draws only",
    "guard": "may block or change a tool call",
    "reach": "reaches files, processes or the network",
    "waits": "waits on a model, a process or the network outside the hook's own time limit",
    "unclassified": "unclassified",
}

# Events through which a hook's return reaches what Claude reads (mods reference, "Prompts and what
# Claude reads", "Tools", "Commands", "Session").
CONTEXT_EVENTS = {
    "prompt.submit": "next({ ...e, context }) adds text Claude reads, after the prompt",
    "prompt.compose": "returns the system prompt's sections",
    "prompt.section": "returns the text of a system prompt section",
    "prompt.context": "returns the context sent with the first message",
    "prompt.attachment": "returns the text of a message Claude Code adds for Claude",
    "prompt.mention": "can make an @-mention read a different file",
    "skill.prompt": "returns a skill's text as Claude reads it",
    "session.append": "rewrites a row the conversation keeps",
    "session.receive": "sees a message before Claude reads it, and can keep it from Claude",
    "tool.describe": "returns a tool's description, which Claude reads",
    "command.run": "a command's returned text prints in the transcript and Claude reads it",
}
CONTEXT_CALLS = {
    "session.append": "rewrites what the conversation keeps",
    "session.send": "sends a message another session or a subagent reads",
    "tool.register": "registers a tool with a description Claude reads",
    "prompt.submit": "submits a prompt that starts a turn",
}
# "$.model.complete sends one prompt to a model with your session's credentials" and "Claude's
# conversation isn't part of the request" (mods API): a cost on the plan, not in this context.
MODEL_CALLS = {
    "model.complete": "one prompt, with no conversation history",
    "model.fork": "one question over the current conversation, in a request of its own",
    "model.classify": "one classification request",
}
GUARD_EVENTS = {
    "tool.call": "a tool is about to run: can return { deny } or { result }",
    "tool.check": "returns the decision allow, ask or deny",
    "classic.PreToolUse": "sees a settings PreToolUse hook's input",
    "classic.PermissionRequest": "sees a settings PermissionRequest hook's input",
}
REACH_NAMESPACES = {"fs": "files", "process": "processes", "http": "the network", "mcp": "MCP servers"}
WAIT_CALLS = {"process.run", "process.spawn", "model.complete", "model.fork", "model.classify",
              "http.fetch", "mcp.call", "mcp.connect"}
# Calls a mod that only draws may make: reading, its own state and store, the clock, the interface.
DRAW_SAFE_CALLS = {"plugin.name", "plugin.root", "prompt.read", "command.list", "tool.list",
                   "agent.list", "config.list", "env.get", "settings.read"} | {
    f"session.{m}" for m in ("messages", "cwd", "root", "model", "turns", "id", "repo", "surfaces",
                             "usage", "version")}
DRAW_SAFE_NAMESPACES = {"ui", "state", "store", "clock"}
API_NAMESPACES = ("plugin", "ui", "command", "tool", "agent", "model", "prompt", "turn", "session",
                  "config", "settings", "env", "fs", "store", "state", "clock", "http", "process",
                  "mcp", "audio", "telemetry")

_RE_REGISTER = (
    re.compile(r"function\s+register\s*\(\s*([A-Za-z_$][\w$]*)"),
    re.compile(r"\bregister\s*[:=]\s*(?:async\s+)?(?:function\s*)?\(?\s*([A-Za-z_$][\w$]*)"),
    re.compile(r"export\s+default\s+(?:async\s+)?function\s*[\w$]*\s*\(\s*([A-Za-z_$][\w$]*)"),
)
_RE_CALL = re.compile(r"(?<![\w$])[A-Za-z_$][\w$]*\s*(?:\?\.|\.)\s*(" + "|".join(API_NAMESPACES)
                      + r")\s*(?:\?\.|\.)\s*([A-Za-z_]\w*)\s*\(")
_RE_WAIT = re.compile(r"\b(?:await|return)\s+[A-Za-z_$][\w$]*\s*\.\s*(" + "|".join(API_NAMESPACES)
                      + r")\s*\.\s*([A-Za-z_]\w*)\s*\(")
_RE_IMPORT = re.compile(r"""(?:\bimport\s+(?:[\w$*{}\s,]+\s+from\s+)?|\bexport\s+[\w$*{}\s,]*\s+from\s+"""
                        r"""|\brequire\s*\(\s*)(['"])([^'"]+)\1""")
_RE_DYNAMIC = (
    (re.compile(r"\bimport\s*\("), "a dynamic import(), whose target is not read"),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bnew\s+Function\s*\("), "new Function()"),
    (re.compile(r"(?<![\w$])\$\s*\["), "the mods API reached by a computed name ($[...])"),
    (re.compile(r"[=(,]\s*\{[^{}]*\}\s*=\s*\$(?![\w$.])|\b(?:const|let|var)\s*\{[^{}]*\}\s*=\s*\$(?![\w$.])"),
     "the mods API destructured, so its calls are not written $.namespace.method"),
)


def strip_js_comments(src: str) -> str:
    """Source with // and /* */ comments blanked, string literals kept. A regular expression
    literal containing // or /* can fool it: a limit of reading without parsing."""
    out, i, n = [], 0, len(src)
    quote = None
    while i < n:
        c = src[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "'\"`":
            quote = c
            out.append(c)
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            out.append("\n" * src.count("\n", i, n if j < 0 else j))
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _mod_sources(plugin_root: Path, first: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    """The module and the local files it imports, read as text. Never executed."""
    sources: list[tuple[Path, str]] = []
    problems: list[str] = []
    todo, seen = [first], set()
    while todo:
        f = todo.pop(0)
        key = str(f.resolve()) if f.exists() else str(f)
        if key in seen:
            continue
        seen.add(key)
        if len(seen) > MOD_MAX_FILES:
            problems.append(f"more than {MOD_MAX_FILES} local files imported: the rest not read")
            break
        if not _inside(f, plugin_root):
            problems.append(f"{f.name}: outside the plugin, not read")
            continue
        try:
            size = f.stat().st_size
        except OSError:
            problems.append(f"{f.name}: missing or unreadable")
            continue
        if size > MOD_SOURCE_MAX_BYTES:
            problems.append(f"{f.name}: larger than {MOD_SOURCE_MAX_BYTES // (1024 * 1024)} MiB, not read")
            continue
        text = read_text(f) if f.is_file() else None
        if text is None:
            problems.append(f"{f.name}: missing or unreadable")
            continue
        sources.append((f, text))
        for _, spec in _RE_IMPORT.findall(strip_js_comments(text)):
            if spec == "claude-code":
                continue
            if not spec.startswith("."):
                problems.append(f"imports the package '{spec}', whose code is not read")
                continue
            target = (f.parent / spec)
            if not target.suffix and not target.exists():
                target = next((target.with_name(target.name + e) for e in MOD_EXTENSIONS
                               if target.with_name(target.name + e).is_file()), target)
            todo.append(target)
    return sources, problems


def _event_matches(pattern: str, names) -> list[str]:
    return [n for n in names if fnmatch.fnmatchcase(n, pattern)]


def classify_mod(texts: list[str]) -> dict:
    """Events, mods API calls and categories of a hooks module, from its source text only."""
    code = "\n".join(strip_js_comments(t) for t in texts)
    unclassified: list[str] = []
    names = {"on"}
    found_register = False
    for rx in _RE_REGISTER:
        for m in rx.finditer(code):
            found_register = True
            names.add(m.group(1))
    events: list[str] = []
    name_alt = "|".join(re.escape(n) for n in sorted(names))
    for m in re.finditer(r"(?<![\w$.])(?:" + name_alt + r")\s*\(\s*(['\"`]?)", code):
        q = m.group(1)
        rest = code[m.end():m.end() + 200]
        if not q:
            if rest.lstrip().startswith(")"):
                continue  # on() with no argument: not a registration
            unclassified.append("an event name computed at run time")
            continue
        end = rest.find(q)
        literal = rest[:end] if end >= 0 else ""
        if q == "`" and "${" in literal:
            unclassified.append("an event name built from a template")
            continue
        if re.fullmatch(r"[A-Za-z*][\w.*-]*", literal or "") and literal not in events:
            events.append(literal)
    if not found_register:
        unclassified.append("no register function found by name")
    long_lines = [ln for ln in code.splitlines() if len(ln) > 2000]
    if long_lines:
        unclassified.append("lines over 2,000 characters: minified or bundled code")
    for rx, why in _RE_DYNAMIC:
        if rx.search(code) and why not in unclassified:
            unclassified.append(why)
    calls = sorted({f"{a}.{b}" for a, b in _RE_CALL.findall(code)})
    waits = sorted({f"{a}.{b}" for a, b in _RE_WAIT.findall(code)} & WAIT_CALLS)
    reasons: dict[str, list[str]] = {}

    def add(cat: str, why: str) -> None:
        if why not in reasons.setdefault(cat, []):
            reasons[cat].append(why)

    for ev in events:
        for name in _event_matches(ev, CONTEXT_EVENTS):
            add("context", f"listens to {ev}" + (f" (matches {name})" if name != ev else "")
                + f": {CONTEXT_EVENTS[name]}")
        for name in _event_matches(ev, GUARD_EVENTS):
            add("guard", f"listens to {ev}" + (f" (matches {name})" if name != ev else "")
                + f": {GUARD_EVENTS[name]}")
    for c in calls:
        if c in CONTEXT_CALLS:
            add("context", f"calls $.{c}: {CONTEXT_CALLS[c]}")
        if c in MODEL_CALLS:
            add("model", f"calls $.{c}: {MODEL_CALLS[c]}")
        ns = c.split(".", 1)[0]
        if ns in REACH_NAMESPACES:
            add("reach", f"calls $.{c} ({REACH_NAMESPACES[ns]})")
    for c in waits:
        add("waits", f"awaits or returns $.{c}: the 10-second limit on a hook's own time does not "
                     "count time inside a mods API call")
    other = [c for c in calls if c not in DRAW_SAFE_CALLS and c.split(".", 1)[0] not in DRAW_SAFE_NAMESPACES]
    if (events and all(fnmatch.fnmatchcase(ev, "ui.*") for ev in events)
            and not reasons and not other and not unclassified):
        add("draws", "listens to " + ", ".join(events) + " only, and calls nothing beyond the "
                     "interface, its own state and store, the clock and read-only methods")
    if unclassified:
        reasons["unclassified"] = list(dict.fromkeys(unclassified))
    order = list(MOD_CATEGORIES)
    return {
        "events": events,
        "calls": calls,
        "categories": [{"id": k, "label": MOD_CATEGORIES[k], "why": reasons[k]}
                       for k in order if k in reasons],
        "basis": MOD_STATIC_LABEL,
    }


def read_mod(plugin_root: Path, module: str) -> dict:
    """One hooks module, located relative to hooks/hooks.json as the mods reference says."""
    path = plugin_root / "hooks" / module
    sources, problems = _mod_sources(plugin_root, path)
    info = classify_mod([t for _, t in sources]) if sources else {
        "events": [], "calls": [], "categories": [], "basis": MOD_STATIC_LABEL}
    if problems or not sources:
        cats = [c for c in info["categories"] if c["id"] not in ("unclassified", "draws")]
        why = list(dict.fromkeys(problems or ["module not read"]))
        prior = next((c["why"] for c in info["categories"] if c["id"] == "unclassified"), [])
        cats.append({"id": "unclassified", "label": MOD_CATEGORIES["unclassified"],
                     "why": list(dict.fromkeys(prior + why))})
        info["categories"] = cats
    info["module"] = module
    info["files_read"] = [_rel(p, plugin_root) for p, _ in sources]
    return info


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


# --------------------------------------------------------------------------- origins


def project_origin(root: Path) -> dict:
    """The project's own share, computed with the auditor's own helpers (check 17)."""
    ctx = AuditContext(root=root)
    apply_layout(ctx, "project")
    scratch = Report()
    skills = check_skills(ctx, scratch) or {}
    agents = check_agents(ctx, scratch) or {}
    hidden = listing_hidden_skills(ctx, skills)
    cap = listing_cap(ctx)
    memory = project_memory(ctx)
    commands = listed_commands(ctx, skills)
    settings = project_settings(ctx)
    out = {
        "memory_bytes": sum(n for _, n in memory),
        "memory_files": [label for label, _ in memory],
        "skills": len(skills) - len(hidden),
        "skills_withheld": len(hidden),
        "skill_chars": sum(entry_chars(s, cap) for n, s in skills.items() if n not in hidden),
        "commands": len(commands),
        "command_chars": sum(commands.values()),
        "agents": len(agents),
        "agent_chars": sum(len(a.get("description", "")) for a in agents.values()),
        "output_style": None,
        "output_style_chars": 0,
        "hooks": count_hooks(settings.get("hooks")),
        "context_hooks": context_hooks(settings.get("hooks")),
        "mcp_servers": mcp_server_names(read_json(root / ".mcp.json")),
    }
    style = settings.get("outputStyle")
    if isinstance(style, str) and style.strip():
        out["output_style"] = style
        out["output_style_chars"] = output_style_chars(style, [root / ".claude" / "output-styles",
                                                               config_dir() / "output-styles"])
    return out


def output_style_chars(name: str, dirs: list[Path]) -> int:
    """The body of a custom output style, found by file stem or frontmatter `name`; 0 for a
    built-in style or one not found."""
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            text = read_text(f)
            if text is None:
                continue
            fm, end = parse_frontmatter(text)
            if f.stem == name or (fm or {}).get("name", "").strip() == name:
                return len("\n".join(text.splitlines()[end:]).strip())
    return 0


def account_origin(base: Path) -> dict:
    """The user configuration directory: memory, skills (synced included), agents, synced plugins."""
    mem, names = memory_entries(base)
    out = {"memory_bytes": mem, "memory_files": names}
    out.update(skill_entries(skill_files(base / "skills")))
    out.update(agent_entries(sorted((base / "agents").rglob("*.md")) if (base / "agents").is_dir() else []))
    settings = read_json(base / "settings.json")
    settings = settings if isinstance(settings, dict) else {}
    out["hooks"] = count_hooks(settings.get("hooks"))
    out["context_hooks"] = context_hooks(settings.get("hooks"))
    synced = []
    sroot = base / "plugins" / "synced"
    if sroot.is_dir():
        for bucket in sorted(p for p in sroot.iterdir() if p.is_dir() and not p.name.startswith(".")):
            for plug in sorted(p for p in bucket.iterdir() if p.is_dir() and not p.name.startswith(".")):
                if (plug / ".claude-plugin").is_dir() or (plug / "skills").is_dir():
                    s = plugin_summary(plug)
                    meta = read_json(bucket / f"{plug.name}.meta.json")
                    s["name"] = plug.name
                    if isinstance(meta, dict) and isinstance(meta.get("name"), str):
                        s["name"] = meta["name"]
                    manifest = read_json(plug / ".claude-plugin" / "plugin.json")
                    if isinstance(manifest, dict) and isinstance(manifest.get("name"), str):
                        s["name"] = manifest["name"]
                    synced.append(s)
    out["synced_plugins"] = synced
    return out


def enabled_plugins(root: Path, base: Path) -> dict[str, tuple[bool, str]]:
    """plugin id -> (enabled, the settings file that decided). Local > project > user."""
    decided: dict[str, tuple[bool, str]] = {}
    for label, f in (("user", base / "settings.json"),
                     ("project", root / ".claude" / "settings.json"),
                     ("local", root / ".claude" / "settings.local.json")):
        data = read_json(f)
        ep = data.get("enabledPlugins") if isinstance(data, dict) else None
        if isinstance(ep, dict):
            for pid, on in ep.items():
                decided[pid] = (on is True or (isinstance(on, list) and bool(on)), label)
    return decided


def installed_plugins(base: Path) -> dict[str, list[dict]]:
    data = read_json(base / "plugins" / "installed_plugins.json")
    if not isinstance(data, dict):
        return {}
    plugins = data.get("plugins", data)
    if not isinstance(plugins, dict):
        return {}
    return {pid: [e for e in _as_list(v) if isinstance(e, dict)] for pid, v in plugins.items()
            if isinstance(pid, str) and "@" in pid}


def _same(a: str, b: Path) -> bool:
    try:
        return Path(a).resolve() == b.resolve()
    except (OSError, ValueError):
        return False


def plugins_origin(root: Path, base: Path) -> list[dict]:
    """Installed plugins enabled for this project, each with what it adds."""
    decided = enabled_plugins(root, base)
    out = []
    for pid, entries in sorted(installed_plugins(base).items()):
        # The installation that applies here: one for this project, else a user-scope one.
        here = [e for e in entries if e.get("scope") in ("project", "local")
                and _same(str(e.get("projectPath", "")), root)]
        user = [e for e in entries if e.get("scope") == "user"]
        entry = (here or user or [None])[0]
        if entry is None or not entry.get("installPath"):
            continue
        path = Path(str(entry["installPath"]))
        if pid in decided:
            on, by = decided[pid]
        else:
            manifest = read_json(path / ".claude-plugin" / "plugin.json")
            on = not (isinstance(manifest, dict) and manifest.get("defaultEnabled") is False)
            by = "default (no enabledPlugins entry)"
        if not on:
            continue
        s = plugin_summary(path) if path.is_dir() else {"missing": True}
        s.update({"id": pid, "enabled_by": by, "scope": entry.get("scope"),
                  "version": entry.get("version")})
        out.append(s)
    return out


def chars_of(o: dict) -> int:
    return (o.get("memory_bytes", 0) + o.get("skill_chars", 0) + o.get("command_chars", 0)
            + o.get("agent_chars", 0) + o.get("output_style_chars", 0))


def environment(root: Path) -> dict:
    REFUSED.clear()
    with opening_guard():
        return _environment(root)


def _environment(root: Path) -> dict:
    base = config_dir()
    project = project_origin(root)
    account = account_origin(base)
    plugins = plugins_origin(root, base)
    plugin_mcp = [(p.get("id"), n) for p in plugins for n in p.get("mcp_servers", [])]
    synced_mcp = [(p.get("name"), n) for p in account["synced_plugins"] for n in p.get("mcp_servers", [])]
    mcp = {
        "project_servers": project["mcp_servers"],
        "plugin_servers": [f"{a}: {b}" for a, b in plugin_mcp],
        "synced_plugin_servers": [f"{a}: {b}" for a, b in synced_mcp],
        "user_servers": "not read (the file that holds them also holds secrets)",
        "connectors": "not visible on disk",
    }
    mcp["servers_found"] = len(mcp["project_servers"]) + len(plugin_mcp) + len(synced_mcp)
    # Two plugins may declare a server of the same name; how the harness names and merges them
    # is not read here, so both counts are given.
    mcp["distinct_names"] = len(set(mcp["project_servers"]) | {b for _, b in plugin_mcp + synced_mcp})
    # `--setting-sources project` loads the project source only; "local" is a source of its own
    # (cli-reference), loaded by the later runs: a plugin enabled in settings.local.json is there.
    project_plugins = [p for p in plugins if p["enabled_by"] == "project"]
    user_plugins = [p for p in plugins if p not in project_plugins]
    totals = {
        "project": chars_of(project),
        "account": chars_of(account) + sum(chars_of(p) for p in account["synced_plugins"]),
        "plugins": sum(chars_of(p) for p in plugins),
    }
    # What --measure separates: `--setting-sources project` loads the project's files and the
    # plugins its shared settings enable; the user's and the local settings add the rest.
    comparable = {
        "project_setting_source": totals["project"] + sum(chars_of(p) for p in project_plugins),
        "user_setting_source": totals["account"] + sum(chars_of(p) for p in user_plugins),
    }
    mods = [f"{p.get('id') or p.get('name')}: {m}" for p in plugins + account["synced_plugins"]
            for m in p.get("mods", [])]
    mod_inventory = [{"plugin": p.get("id") or p.get("name"), **info}
                     for p in plugins + account["synced_plugins"] for info in p.get("mod_modules", [])]
    return {
        "root": str(root),
        "refused": list(REFUSED),
        "config_dir": str(base),
        "chars_per_token_rough": CHARS_PER_TOKEN_ROUGH,
        "project": project,
        "account": account,
        "plugins": plugins,
        "mcp": mcp,
        "mods": mods,
        "mod_inventory": mod_inventory,
        "mod_notes": MOD_NOTES,
        "chars": totals,
        "tokens_estimate": {k: tokens(v) for k, v in totals.items()},
        "comparable_to_measure_chars": comparable,
        "comparable_to_measure_tokens_estimate": {k: tokens(v) for k, v in comparable.items()},
        "not_counted": [
            "Claude Code's own system prompt, built-in tools, skills and agents (the bare condition of --measure)",
            "MCP tool definitions: they come from the servers at run time, not from files",
            "MCP servers added with `claude mcp add` at user or local scope, and claude.ai connectors",
            "the output of SessionStart and UserPromptSubmit hooks",
            "what a mod changes in the prompt",
        ],
    }


# --------------------------------------------------------------------------- text report


def _line(label: str, o: dict) -> list[str]:
    parts = []
    if o.get("memory_bytes"):
        parts.append(f"memory {o['memory_bytes']} chars ({', '.join(o.get('memory_files', []))})")
    parts.append(f"{o.get('skills', 0)} skills {o.get('skill_chars', 0)} chars"
                 + (f" (+{o['skills_withheld']} withheld, not paid)" if o.get("skills_withheld") else ""))
    if o.get("commands"):
        parts.append(f"{o['commands']} commands {o['command_chars']} chars")
    parts.append(f"{o.get('agents', 0)} agents {o.get('agent_chars', 0)} chars")
    if o.get("output_style"):
        parts.append(f"output style '{o['output_style']}' {o.get('output_style_chars', 0)} chars")
    return [f"  {label}", "    " + "; ".join(parts)]


MOD_NOTES = {
    "basis": MOD_STATIC_LABEL,
    "cost": "time and token cost not measured; this report reads mods and runs none, but --measure "
            "runs `claude -p`, which loads and runs the mods of the enabled plugins",
    "built_in": "built-in mods (such as cc-plugin-agents-md, cc-plugin-diff, cc-plugin-plugin-authoring) "
                "are not in your files and are not counted",
    "cross_check": "/plugin shows a line such as '1 mod active' that omits built-in mods: compare its "
                   "count with this one",
    "not_seen": "mods loaded with --plugin-dir or CLAUDE_CODE_PLUGIN_DIRS are not read",
    "draws_measured": "a mod that only draws (ui.render) added 0 first-request input tokens in a 3-run "
                      "test on Claude Code 2.1.295 (claude -p); in claude -p the ui.render hook did not "
                      "run, so the interactive case is not measured",
}


def render_mods(env: dict) -> list[str]:
    inv = env.get("mod_inventory", [])
    notes = env.get("mod_notes", MOD_NOTES)
    out = [f"MODS  {len(inv)} found in the files read; {notes['cost']}"]
    for m in inv:
        out.append(f"  {m['plugin']}: {m['module']}"
                   + (f" (read: {', '.join(m['files_read'])})" if m.get("files_read") else ""))
        out.append("    events: " + (", ".join(m["events"]) if m["events"] else "none found"))
        if not m["categories"]:
            out.append("    no category: " + ("no hook registered" if not m["events"] else
                                              "none of the events or calls the categories look for"))
        for c in m["categories"]:
            out.append(f"    - {c['label']} [{notes['basis']}]")
            out += [f"        {w}" for w in c["why"]]
            if c["id"] == "draws":
                out.append(f"        note: {notes['draws_measured']}")
    out.append(f"  Not counted: {notes['built_in']}; {notes['not_seen']}.")
    out.append(f"  Cross-check: {notes['cross_check']}.")
    return out


def render(env: dict) -> str:
    r = env["chars_per_token_rough"]
    t, c = env["tokens_estimate"], env["chars"]
    out = [f"Environment of {env['root']}",
           f"user configuration directory: {env['config_dir']}",
           f"Tokens are an estimate from file sizes, not a measurement: characters / {r} "
           f"(a rough ratio measured on this plugin's own text). `--measure` measures it.", ""]
    p = env["project"]
    out.append(f"PROJECT  ~{t['project']} tokens ({c['project']} chars)")
    out += _line("files of the project (what audit.py's budget counts)", p)
    if p.get("hooks"):
        out.append(f"    hooks: {p['hooks']} ({p['context_hooks']} on SessionStart/UserPromptSubmit: output not estimated)")
    out.append("")
    a = env["account"]
    out.append(f"ACCOUNT  ~{t['account']} tokens ({c['account']} chars)")
    out += _line("user configuration directory (skills, synced skills, agents, memory)", a)
    if a.get("hooks"):
        out.append(f"    hooks: {a['hooks']} ({a['context_hooks']} on SessionStart/UserPromptSubmit: output not estimated)")
    for s in a["synced_plugins"]:
        out.append(f"    synced plugin {s['name']}: {s['skills']} skills {s['skill_chars']} chars, "
                   f"{s['agents']} agents {s['agent_chars']} chars, ~{tokens(chars_of(s))} tokens")
    out.append("")
    out.append(f"PLUGINS  ~{t['plugins']} tokens ({c['plugins']} chars), {len(env['plugins'])} enabled for this project")
    for s in env["plugins"]:
        if s.get("missing"):
            out.append(f"  {s['id']} (enabled by {s['enabled_by']}): installed path missing")
            continue
        extra = []
        if s.get("commands"):
            extra.append(f"{s['commands']} commands {s['command_chars']} chars")
        if s.get("mcp_servers"):
            extra.append(f"{len(s['mcp_servers'])} MCP servers")
        if s.get("hooks"):
            extra.append(f"{s['hooks']} hooks")
        if s.get("mods"):
            extra.append(f"{len(s['mods'])} mod" + ("s" if len(s["mods"]) > 1 else ""))
        if s.get("outside_root"):
            extra.append("manifest paths outside the plugin, not loaded and not counted: "
                         + ", ".join(s["outside_root"]))
        out.append(f"  {s['id']} {s.get('version') or ''} (enabled by {s['enabled_by']}): "
                   f"{s['skills']} skills {s['skill_chars']} chars, {s['agents']} agents "
                   f"{s['agent_chars']} chars" + (", " + ", ".join(extra) if extra else "")
                   + f", ~{tokens(chars_of(s))} tokens")
    out.append("")
    m = env["mcp"]
    out.append(f"MCP  {m['servers_found']} servers declared in files ({m['distinct_names']} distinct names); "
               "tokens not estimated "
               "(tool definitions come from the servers)")
    if m["project_servers"]:
        out.append(f"  project .mcp.json: {len(m['project_servers'])} ({', '.join(m['project_servers'])})")
    if m["plugin_servers"]:
        out.append(f"  enabled plugins: {len(m['plugin_servers'])} ({', '.join(m['plugin_servers'])})")
    if m["synced_plugin_servers"]:
        out.append(f"  synced plugins: {len(m['synced_plugin_servers'])} ({', '.join(m['synced_plugin_servers'])})")
    out.append("  user and local servers (`claude mcp add`): not read - the file that holds them also holds secrets")
    out.append("  claude.ai connectors: not visible on disk")
    out.append("")
    out += render_mods(env)
    k = env["comparable_to_measure_tokens_estimate"]
    out.append("")
    out.append(f"As --measure splits it: project settings ~{k['project_setting_source']} tokens "
               f"(project + plugins its settings.json enables), user and local settings "
               f"~{k['user_setting_source']} tokens (account + plugins enabled by the user or by "
               "settings.local.json), MCP not estimated.")
    if env.get("refused"):
        out.append(f"Refused, not opened (credential or secret file, by name, real path or file "
                   f"identity): {', '.join(env['refused'])}")
    out.append("Not counted: " + "; ".join(env["not_counted"]) + ".")
    return "\n".join(out)


# --------------------------------------------------------------------------- --measure


def first_turn(stdout: str) -> dict:
    """The init event's counts and the result's input tokens, from stream-json lines."""
    info: dict = {}
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            for key in ("skills", "agents", "plugins", "mcp_servers", "tools"):
                v = ev.get(key)
                info[key] = len(v) if isinstance(v, list) else None
        elif ev.get("type") == "result":
            u = ev.get("usage") or {}
            info["input_tokens"] = sum(int(u.get(k) or 0) for k in
                                       ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            info["cost_usd"] = ev.get("total_cost_usd")
    return info


def measure(root: Path, model: str, claude: str) -> list[dict]:
    rows = []
    for label, flags in CONDITIONS:
        cmd = [claude, "-p", "--model", model, "--output-format", "stream-json", "--verbose",
               *flags, PROMPT]
        try:
            done = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600)
            row = first_turn(done.stdout)
            row["exit_code"] = done.returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            row = {"error": type(e).__name__}
        row["condition"] = label
        row["flags"] = " ".join(f if f else '""' for f in flags)
        rows.append(row)
    return rows


def measure_diffs(rows: list[dict]) -> dict:
    t = [r.get("input_tokens") for r in rows]
    if len(t) != 4 or any(x is None for x in t):
        return {}
    return {"project": t[1] - t[0], "account_and_user_plugins": t[2] - t[1], "mcp": t[3] - t[2],
            "bare": t[0], "total": t[3]}


def render_measure(rows: list[dict], diffs: dict) -> str:
    out = ["", "MEASURED (one run per condition, so noisy; first-turn input tokens as the API reports them)"]
    for r in rows:
        if "error" in r or r.get("input_tokens") is None:
            out.append(f"  {r['condition']:<22} failed ({r.get('error') or 'exit ' + str(r.get('exit_code'))})")
            continue
        out.append(f"  {r['condition']:<22} {r['input_tokens']:>7} tokens  skills {r.get('skills')}, "
                   f"agents {r.get('agents')}, plugins {r.get('plugins')}, MCP {r.get('mcp_servers')}, "
                   f"tools {r.get('tools')}   [{r['flags']}]")
    if diffs:
        out.append(f"  project adds {diffs['project']}, account and user plugins {diffs['account_and_user_plugins']}, "
                   f"MCP {diffs['mcp']} (bare {diffs['bare']}, total {diffs['total']})")
    else:
        out.append("  differences not computed: a run did not report its tokens")
    return "\n".join(out)


MEASURE_WARNING = (
    "--measure runs `claude -p` four times in the project, with your own login (a few cents). That "
    "is opening a Claude Code session in that folder without the workspace trust dialog: it runs the "
    "hooks of the project's settings, connects the servers of its .mcp.json and loads the mods of the "
    "enabled plugins (\"Without `--bare`, a `-p` session runs the hooks in a project's "
    "`.claude/settings.json` and connects the servers in its `.mcp.json`, even in a folder you've "
    "never trusted\", headless). It asks on the terminal, or needs --yes; with --json it needs --yes.")


def consent_text(env: dict, root: Path, model: str) -> str:
    """What --measure will run, counted from the files just read."""
    p = env["project"]
    plugin_hooks = sum(s.get("hooks", 0) for s in env["plugins"])
    return (f"--measure runs `claude -p --model {model}` four times in {root}, with your own login "
            f"(a few cents). That is opening a Claude Code session in this folder, without the "
            f"workspace trust dialog. It will run: {p.get('hooks', 0)} hook(s) of the project's "
            f"settings, {len(p.get('mcp_servers', []))} server(s) of the project's .mcp.json, "
            f"{len(env.get('mods', []))} mod(s) of the enabled and synced plugins; and your user "
            f"settings' hooks ({env['account'].get('hooks', 0)}) and the enabled plugins' hooks "
            f"({plugin_hooks}). Only for a folder you trust.")


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="What your environment adds to a session's context, beyond the project's files.",
        epilog="Estimate from file sizes by default (no network, nothing written). " + MEASURE_WARNING)
    parser.add_argument("--root", default=".", help="Project root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--measure", action="store_true",
                        help="Also measure, beside the estimate: four `claude -p` runs in the project "
                             "(costs a few cents; runs its hooks, MCP servers and mods: see below)")
    parser.add_argument("--yes", action="store_true",
                        help="Run --measure without asking (required with --json or without a terminal)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for --measure (default: {DEFAULT_MODEL})")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"--root {root}: not a directory", file=sys.stderr)
        return 2
    env = environment(root)
    if args.measure:
        claude = shutil.which("claude")
        if not claude:
            print("--measure needs the `claude` command on PATH, installed and logged in.", file=sys.stderr)
            return 2
        if not args.yes:
            # The question goes to stderr and the answer comes from the terminal, so stdout
            # carries the report only: with --json, nothing but JSON (audit externe, do-01).
            if args.json or not (sys.stdin.isatty() and sys.stderr.isatty()):
                print(consent_text(env, root, args.model) + "\n--measure was not run: "
                      + ("with --json, confirm with --yes." if args.json else
                         "no terminal to ask on; confirm with --yes."), file=sys.stderr)
                return 2
            print(consent_text(env, root, args.model) + " Go on? [y/N] ", end="", file=sys.stderr,
                  flush=True)
            answer = sys.stdin.readline()
            if answer.strip().lower() not in ("y", "yes"):
                print("Not measured.", file=sys.stderr)
                return 1
        rows = measure(root, args.model, claude)
        env["mod_notes"] = dict(env["mod_notes"], cost="time cost not measured; --measure ran `claude -p`, "
                                "which loads and runs the mods of the enabled plugins: whatever they "
                                "add to the first request is inside the measured figures, not separated")
        env["measured"] = {"model": args.model, "runs": rows, "differences": measure_diffs(rows),
                           "note": "one run per condition, so noisy"}
    if args.json:
        print(json.dumps(env, indent=2, ensure_ascii=False))
    else:
        print(render(env))
        if "measured" in env:
            print(render_measure(env["measured"]["runs"], env["measured"]["differences"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
