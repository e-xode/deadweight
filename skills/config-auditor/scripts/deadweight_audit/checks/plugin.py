"""Plugins: manifest, variables, documented flags, companion skills."""
from __future__ import annotations

import json
import re

from ..identity import instrument_files
from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_keys, parse_frontmatter
from ..parsing.markdown import FENCE_RE, fenced_spans, in_spans, strip_code_fences
from ..repo import claude_md_path, readable_files, git_ignored
from ..report import Report


def check_documented_flags(ctx: AuditContext, report: Report) -> None:
    """Every flag the documentation shows must exist in the script.

    Removing a feature and leaving its documentation is the same defect as renaming
    a skill and leaving its mentions: the code is right, the reader is wrong, and
    nothing fails. Measured on this plugin on 2026-09-22, after `--record` was
    removed one release earlier: SIX live references survived, including two inside
    COMMAND BLOCKS a reader would copy and run, and a README that contradicted
    itself - one section said the feature was removed while two others described it
    as present. Thirty-six checks saw none of it.

    Only flags on a line that invokes the audit script are read. A document
    legitimately shows `claude plugin eval --allow-tools` or `git log -p`, and a
    check that flagged those would be noise - and noise is how a check gets skipped.
    """
    root = ctx.root
    # The audited copy of this auditor when there is one (this plugin auditing itself),
    # otherwise the running one. Its flags are declared in the package, not in audit.py.
    scripts = root / ctx.skills_dir / "config-auditor" / "scripts"
    sources = ([scripts / "audit.py"] + sorted((scripts / "deadweight_audit").rglob("*.py"))
               if (scripts / "audit.py").is_file() else instrument_files())
    try:
        src = "".join(f.read_text(encoding="utf-8") for f in sources)
    except OSError:
        return
    declared_flags = set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', src))
    if not declared_flags:
        return
    base = root / ctx.skills_dir
    files = readable_files(base.rglob("*.md")) if base.is_dir() else []
    for extra in ("README.md", "CHANGELOG.md"):
        p = root / extra
        if p.is_file():
            files.append(p)
    seen: dict[str, list[str]] = {}
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # FENCED CODE BLOCKS ONLY. A first version read any line containing
        # `audit.py` and returned five findings across the fleet, all five false:
        # « This is why `audit.py` has no `--fix` flag » - flagged for asserting
        # exactly what the check wants to be true - and two lines where prose put
        # two different commands side by side. The defect this check exists for is
        # a flag inside a block someone COPIES AND RUNS; prose that mentions a flag
        # is a lesser problem and not this one. A detector that is wrong five times
        # out of five is one nobody keeps.
        blocks, pos = fenced_spans(content), 0
        for i, line in enumerate(content.splitlines(keepends=True), 1):
            start, pos = pos, pos + len(line)
            if not in_spans(start, blocks) or FENCE_RE.match(line.rstrip("\r\n")) \
                    or not re.search(r"(?<![\w.-])audit\.py\b", line):
                continue
            for flag in re.findall(r"(?<![\w-])(--[a-z0-9-]+)", line):
                if flag not in declared_flags:
                    seen.setdefault(flag, []).append(f"{f.relative_to(root)}:{i}")
    for flag, where_found in sorted(seen.items()):
        # The CHANGELOG is exempt: naming what was removed is its job.
        live_mentions = [x for x in where_found if not x.startswith("CHANGELOG.md")]
        if not live_mentions:
            continue
        report.add("37-documented-flag", "ERROR",
                   f"`{flag}` is shown with audit.py in {len(live_mentions)} place(s) "
                   f"({', '.join(live_mentions[:4])}) but the script does not accept it. A reader "
                   "copying that line gets an error, and nothing else fails.", str(root))


def check_plugin_vars_in_project(ctx: AuditContext, report: Report) -> None:
    """`${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` in a project skill: never substituted.

    "Substituted only in plugin skills" (skills, § available string substitutions): in a
    project skill the model reads the variable literally, and a command built on it runs
    against an empty path. 8 of 600 public repositories, 2026-09-27.
    """
    root = ctx.root
    for skill_md in readable_files((root / ctx.skills_dir).glob("*/SKILL.md")):
        try:
            text = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Uses only: in `allowed-tools`, or a `${CLAUDE_PLUGIN_ROOT}/<path>` whose file exists
        # beside the skill or in the repository. A skill that TEACHES plugins quotes the
        # variable as an example: 5 of 8 findings were that (600 public repositories).
        fm_text = text.split("\n---", 2)[0] if text.startswith("---") else ""
        seen = set()
        for mm in re.finditer(r"\$\{?(CLAUDE_PLUGIN_(?:ROOT|DATA))\}?(/[\w./-]+)?", text):
            in_tools = re.search(r"^allowed-tools:.*" + re.escape(mm.group(0)), fm_text, re.M)
            rest = (mm.group(2) or "").strip("/")
            exists_here = rest and ((skill_md.parent / rest).exists() or (root / rest).exists())
            if in_tools or exists_here:
                seen.add(mm.group(1))
        seen = sorted(seen)
        if seen:
            report.add("49-plugin-var-in-project", "ERROR",
                       f"Skill '{skill_md.parent.name}' uses {', '.join('${' + v + '}' for v in seen)}, "
                       "which Claude Code substitutes only in plugin skills: here it stays literal. "
                       "Use ${CLAUDE_SKILL_DIR} or ${CLAUDE_PROJECT_DIR} (skills).", str(skill_md))


# --- Plugin manifest ----------------------------------------------------------
PLUGIN_PATH_FIELDS = ("skills", "agents", "commands", "hooks", "mcpServers", "outputStyles",
                      "lspServers")


def check_plugin_manifest(ctx: AuditContext, report: Report) -> None:
    """What `claude plugin validate` does not say about a plugin's layout."""
    root = ctx.root
    cp = root / ".claude-plugin"
    for d in ("skills", "agents", "hooks", "commands"):
        if (cp / d).exists():
            report.add("44-plugin-layout", "ERROR",
                       f".claude-plugin/{d}/ is not loaded: component directories belong at the "
                       "plugin root, not inside .claude-plugin/ (plugins-reference).",
                       str(cp / d))
    manifest = cp / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8-sig")) if manifest.is_file() else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return
    for key in PLUGIN_PATH_FIELDS:
        vals = data.get(key)
        vals = vals if isinstance(vals, list) else [vals]
        for v in vals:
            if not isinstance(v, str):
                continue
            # "skills: also accepts '.'", and mcpServers "also accepts MCP bundle paths and
            # URLs" (plugins-reference, path rules): both were false ERRORs until 0.19.0.
            if (key == "skills" and v in (".", "./")) or (key == "mcpServers" and v.startswith("https://")):
                continue
            if key == "agents" and not v.endswith(".md"):
                report.add("44-plugin-path", "ERROR",
                           f"plugin.json 'agents': '{v}' - agents entries must be .md files; "
                           "\"Directories aren't accepted\" (plugins-reference).", str(manifest))
                continue
            if not v.startswith("./"):
                report.add("44-plugin-path", "ERROR",
                           f"plugin.json '{key}': '{v}' - every component path must be relative "
                           "and start with './' (plugins-reference).", str(manifest))
                continue
            try:
                inside = (root / v).resolve().is_relative_to(root.resolve())
            except (OSError, ValueError):
                inside = True
            if not inside:
                report.add("44-plugin-path", "ERROR",
                           f"plugin.json '{key}': '{v}' escapes the plugin directory, and that "
                           "component does not load (plugins-reference).", str(manifest))
    for key, folder in (("agents", "agents"), ("commands", "commands"),
                          ("outputStyles", "output-styles"), ("workflows", "workflows"),
                          ("themes", "themes"), ("experimental.themes", "themes")):
        vals = (data.get("experimental") or {}).get("themes") if key == "experimental.themes" \
            else data.get(key)
        if isinstance(vals, dict):
            # `commands` "also accepts an object map" (plugins-reference): its sources count.
            vals = [x.get("source") if isinstance(x, dict) else x for x in vals.values()]
        if vals is None or not (root / folder).is_dir():
            continue
        listed = {(root / v).resolve() for v in (vals if isinstance(vals, list) else [vals])
                  if isinstance(v, str)}
        stray = [p for p in readable_files((root / folder).glob("*.md"))
                 if p.resolve() not in listed and p.parent.resolve() not in listed]
        if stray:
            report.add("44-plugin-path", "WARN",
                       f"plugin.json declares '{key}', which REPLACES the default {folder}/ "
                       f"directory: {len(stray)} file(s) there are not loaded ({stray[0].name}...).",
                       str(manifest))
    market = cp / "marketplace.json"
    if market.is_file() and data.get("version"):
        try:
            entries = json.loads(market.read_text(encoding="utf-8-sig")).get("plugins") or []
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, AttributeError):
            entries = []
        for e in entries:
            if (isinstance(e, dict) and e.get("name") == data.get("name")
                    and e.get("version") and e["version"] != data["version"]):
                report.add("44-plugin-version", "WARN",
                           f"marketplace.json says {e['version']}, plugin.json says "
                           f"{data['version']}: Claude Code always uses plugin.json, without a "
                           "warning (plugins-reference).", str(market))


# --- Commands, rules, CLAUDE.md companions -----------------------------------
def check_companions(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """Files beside the configuration that change what it means."""
    root = ctx.root
    cmd_dir = root / ctx.claude_dir / "commands"
    if cmd_dir.is_dir():
        for p in readable_files(cmd_dir.rglob("*.md")):
            if not p.exists():
                continue        # a dangling link: 47-dangling-symlink reports it
            if p.stem in skills:
                report.add("45-command-shadowed", "WARN",
                           f"commands/{p.name} and the skill '{p.stem}' share a name: the skill "
                           "wins, and the command never runs (skills).", str(p))
            fm, _ = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace"))
            for key in ("name", "paths"):
                if fm and key in fm:
                    report.add("45-command-shadowed", "WARN",
                               f"commands/{p.name} sets '{key}', which a command file does not "
                               "support (skills, 'Command files').", str(p))
    rules_dir = root / ctx.claude_dir / "rules"
    if rules_dir.is_dir():
        for p in readable_files(rules_dir.rglob("*.md")):
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            for key in frontmatter_keys(text):
                if key != "paths":
                    report.add("14-rule-unknown-field", "WARN" if key in ("globs", "path", "glob") else "NOTICE",
                               f"Rule '{p.name}' sets '{key}': `paths` is the only field a rule "
                               "reads" + (" - `globs:` is Cursor's name for it" if key == "globs"
                                          else "") + " (memory).", str(p))
    ign = git_ignored(root)
    local = root / "CLAUDE.local.md"
    if local.is_file() and (root / ".git").exists() and not ign("CLAUDE.local.md"):
        report.add("01-claude-local", "WARN",
                   "CLAUDE.local.md is not ignored by git: it holds personal, per-machine "
                   "instructions, and committed it becomes everyone's (memory).", str(local))
    md = claude_md_path(root)
    if md.is_file():
        body = strip_code_fences(md.read_text(encoding="utf-8", errors="replace"))
        body = re.sub(r"`[^`]*`", "", body)
        # The `@` must open the token: `@./node_modules/@scope/pkg/AGENTS.md` is one
        # import, and a second `@` inside the path was read as a second one.
        for m in re.finditer(r"(?<![\w./@-])@((?:~/|\.{0,2}/)?[\w./@-]+\.[A-Za-z0-9]+)\b", body):
            ref = m.group(1)
            if ref.startswith("~/") or ref.startswith("/"):
                continue                  # outside the repository: approval dialog, unverifiable
            rel = ref[2:] if ref.startswith("./") else ref
            if ign(rel):
                continue                  # generated or installed (node_modules/): machine-dependent
            target = (md.parent / ref)
            if not target.exists() and not (root / ref).exists():
                report.add("01-claude-md-import", "WARN",
                           f"CLAUDE.md imports '@{ref}', which does not exist - the import "
                           "resolves relative to the importing file (memory).", str(md))
