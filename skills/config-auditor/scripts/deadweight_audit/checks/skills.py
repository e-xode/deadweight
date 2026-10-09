"""Skills: frontmatter, sizes, references, names, where they load."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..checks.budget import listing_cap
from ..checks.descriptions import ANTI_TRIGGER_RE
from ..context import AuditContext
from ..layout import claude_signs, root_level_skills
from ..limits import (
    DESCRIPTION_MAX_CHARS,
    REFERENCE_TOC_SCAN_LINES,
    RESERVED_NAME_TOKENS,
    SKILL_MD_COMPACTION_WARN_BYTES,
    SKILL_NAME_MAX_CHARS,
    SKILL_NAME_RE,
)
from ..checks.security import _hook_commands
from ..parsing.frontmatter import frontmatter_hooks, frontmatter_keys, parse_frontmatter
from ..parsing.markdown import iter_relative_links
from ..repo import readable_files, git_ignored, is_vendored_skill, exists_from_root
from ..report import Report, house, house_note
from ..vocabulary.frontmatter import SKILL_KNOWN_KEYS


def check_unloadable_skills(ctx: AuditContext, report: Report) -> None:
    """A SKILL.md at the repository root is a file, not a skill.

    Severity follows intent, which the auditor can only read from the repository:
    beside a CLAUDE.md, a `.claude/` or a plugin manifest, the author meant these to
    load in Claude Code and they do not - ERROR. Without any such sign the repository
    may target another tool, or installation by copy - WARN, saying where they load.
    """
    root = ctx.root
    found = root_level_skills(root)
    if not found or (ctx.dual_library and ctx.layout == "library"):
        return
    if ctx.dual_library:
        # A skills library that is also worked on with Claude Code: its root skills are
        # there to be copied, and "load nowhere" read as a defect (2 false ERRORs, third
        # public sample, 2026-09-27). Their content is audited in the library pass.
        report.add("40-skill-not-loaded", "INFO",
                   f"{len(found)} skill(s) at the repository root: a library to copy, audited "
                   "as one. They do not load in this project itself - put the ones it uses "
                   "under `.claude/skills/`.", str(root))
        return
    signs = claude_signs(root)
    names = ", ".join(d.name for d in found[:5]) + (f" (+{len(found) - 5})" if len(found) > 5 else "")
    where = ("`skills/<name>/` (plugin)" if ctx.layout != "project"
             else "`.claude/skills/<name>/`")
    report.add(
        "40-skill-not-loaded",
        "ERROR" if signs else "WARN",
        f"{len(found)} skill(s) at the repository root load nowhere as they stand: {names}. "
        "Claude Code finds skills by location, not by content - a project loads "
        "`.claude/skills/`, a plugin loads `skills/`. "
        + (f"This repository carries {', '.join(signs)}, so they were meant to load: "
           f"move them under {where}." if signs else
           "Nothing here says the repository targets Claude Code; if it does, move them "
           "under `skills/` and it loads as a plugin, manifest or not."),
        str(root),
    )


# Directories under `skills/` that are not skills. `_`-prefixed is the widespread
# convention for shared material; the rest are the names the Agent Skills spec
# itself uses for a skill's own subdirectories, which appear one level up in
# repositories that share them between skills.
SUPPORT_DIR_NAMES = {"assets", "templates", "scripts", "references", "shared", "common"}


def is_anthropic_skills_name(name: str) -> bool:
    """`anthropic-skills` or a name inside that namespace: reserved outside a plugin (skills)."""
    n = (name or "").strip().lower()
    return n == "anthropic-skills" or n.startswith("anthropic-skills:")


def plugin_name(root: Path) -> str:
    """The plugin's own prefix: the manifest `name`, else the directory name."""
    try:
        name = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8-sig")).get("name")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        name = None
    return name if isinstance(name, str) and name else root.name


def skill_dirs(base: Path, report: Report, layout: str = "plugin") -> list[Path]:
    """Every directory that holds a SKILL.md, however the author nested them.

    A first version assumed exactly one level - `skills/<name>/SKILL.md` - and
    reported every other directory as a missing SKILL.md. Measured on 15 public
    plugins: 21 of 38 errors came from that assumption alone, against repositories
    that group skills by category (`skills/<category>/<skill>/SKILL.md`) or keep a
    `_shared/` directory beside them. Neither is a defect; both are organisation.

    That measurement was taken on plugins only. In a project, Claude Code reads
    `.claude/skills/<skill-name>/SKILL.md` (skills), and a skill one level deeper did
    not load in Claude Code 2.1.293 (external audit, 2026-10-08): auditing it as a
    loaded skill counted its description in the budget and hid the one defect worth
    reporting. Plugin layout was not tested, so it keeps the category reading.

    A directory is reported only when it holds NEITHER a SKILL.md NOR any descendant
    that does - that is the case where something really is missing.
    """
    found_items: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "SKILL.md").is_file():
            found_items.append(entry)
            continue
        descendants = sorted(p.parent for p in entry.rglob("SKILL.md"))
        support = entry.name.startswith("_") or entry.name.lower() in SUPPORT_DIR_NAMES
        if descendants and layout == "project":
            if support:
                continue                         # parked or shared material, said so by its name
            nested = [p.relative_to(base).as_posix() for p in descendants]
            shown = ", ".join(nested[:3]) + (f" (+{len(nested) - 3})" if len(nested) > 3 else "")
            report.add("02-skill-md-exists", "WARN",
                       f"Directory '{entry.name}' under the skills directory holds no SKILL.md, "
                       f"but {len(nested)} SKILL.md file(s) sit below it: {shown}. Claude Code reads "
                       "`.claude/skills/<skill-name>/SKILL.md` (skills) and did not load a "
                       "skill nested one level deeper (measured, 2.1.293): move each up to "
                       "`.claude/skills/<skill-name>/`. Not audited as loaded skills.",
                       str(entry))
            continue
        if descendants:
            found_items.extend(descendants)          # category, not a skill
            continue
        if support:
            continue                             # support material, not a skill
        other_case = [p.name for p in entry.iterdir() if p.name.lower() == "skill.md"]
        report.add("02-skill-md-exists", "WARN",
                   f"Directory '{entry.name}' under the skills directory holds no SKILL.md "
                   + (f"- it holds '{other_case[0]}', and the name is case-sensitive: Claude Code "
                      "looks for SKILL.md." if other_case else
                      "and no descendant that does. A skill needs one; a support directory "
                      "should be named with a leading underscore so it reads as one."),
                   str(entry))
    return found_items


def check_skills(ctx: AuditContext, report: Report) -> dict[str, dict]:
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    if ctx.layout == "none":
        return {}
    if ctx.layout == "library":
        # Only the root folders that ARE skills: `src/` or `docs/` beside them are
        # not malformed skills, and the recursive walk would call them that.
        entries = root_level_skills(root)
    elif not skills_dir.is_dir():
        if ctx.layout == "marketplace":
            report.add("02-skills-dir", "INFO",
                       "A marketplace repository ships no skills of its own; the plugins it "
                       "lists carry them. Audit each plugin directory separately.",
                       str(root))
            return {}
        # A plugin may legitimately ship only commands, agents or hooks. Calling
        # that an error tells an author their working plugin is broken, which is
        # how an auditor gets uninstalled rather than heeded.
        # In a project these live under .claude/; at a plugin root, beside skills/.
        base = root / ctx.claude_dir if ctx.layout == "project" else root
        other = [d for d in ("commands", "agents", "hooks") if (base / d).exists()]
        if other:
            report.add("02-skills-dir", "INFO",
                       f"No {ctx.skills_dir}/ — this one ships {', '.join(other)} instead. "
                       "Skill checks have no subject here.", str(root))
        else:
            report.add("02-skills-dir", "INFO",
                       f"{ctx.skills_dir}/ not found, and no commands/, agents/ or hooks/ either "
                       "— nothing here declares anything.", str(skills_dir))
        return {}
    else:
        entries = skill_dirs(skills_dir, report, ctx.layout)
    skills: dict[str, dict] = {}
    seen_names: dict[str, str] = {}
    ignored = git_ignored(root)
    for entry in sorted(entries):
        skill_md = entry / "SKILL.md"
        if not skill_md.exists():
            continue            # a dangling link: 47-dangling-symlink reports it
        text = skill_md.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        if not fm:
            # Claude Code loads it anyway - "All fields are optional": the folder gives
            # the name, the first non-empty line the description (skills). A defect -
            # that first line is rarely a trigger - but not a rejection. Measured on a
            # calibration sample, 2026-09-23: 12 such skills reported as ERRORs.
            report.add(
                "02-skill-frontmatter",
                "WARN",
                f"SKILL.md in '{entry.name}' has no YAML frontmatter: Claude Code still loads "
                "it, named after the folder and described by its first non-empty line - "
                "rarely a usable trigger. The Agent Skills spec requires name and description.",
                str(skill_md),
            )
            continue
        name = fm.get("name", "").strip()
        desc = fm.get("description", "").strip()
        # Claude Code: "All fields are optional", `name` defaults to the folder
        # (skills). Only the Agent Skills spec requires it - a library is packaged
        # and uploaded under that spec, a project skill never is. As an ERROR on
        # projects it was 20 of 98 ERRORs on a 150-repository sample, 2026-09-27.
        if not name and ctx.layout == "library":
            report.add("02-skill-frontmatter", "WARN",
                       f"Skill '{entry.name}' sets no 'name': Claude Code names it after the "
                       "folder, but the Agent Skills spec requires the field, and packaging or "
                       "upload rejects the skill without it.", str(skill_md))
        if not desc:
            # Same defect as a SKILL.md with no frontmatter at all, which is a WARN: the
            # skill loads, with nothing to be picked by. An ERROR here and a WARN there
            # graded the same fact twice (third public sample, 2026-09-27).
            report.add("02-skill-frontmatter", "WARN",
                       f"Skill '{entry.name}' has no description (missing or empty): it loads, "
                       "but Claude has nothing to pick it by - only /name reaches it.",
                       str(skill_md))

        for key in frontmatter_keys(text):
            if key not in SKILL_KNOWN_KEYS:
                near = [k for k in SKILL_KNOWN_KEYS if k.replace("-", "_") == key.replace("-", "_")]
                report.add("02-skill-unknown-field", "WARN",
                           f"Skill '{entry.name}' sets '{key}', which is not a skill field: Claude "
                           "Code ignores it without reporting an error (skills)."
                           + (f" Did you mean '{near[0]}'?" if near else ""), str(skill_md))
        if re.search(r"[<>]", desc):
            # Claude Code loads it; claude.ai upload and skill-creator's quick_validate
            # reject it. On a Vue storefront (`ui-shop`) all five hits were Vue vocabulary (`<script setup>`):
            # legitimate in a project that never uploads, a real risk for a plugin.
            report.add("04-skill-description-brackets", "WARN" if ctx.layout == "plugin" else "NOTICE",
                       f"Skill '{entry.name}' description contains '<' or '>': Claude Code loads "
                       "it, but claude.ai upload and skill-creator's quick_validate reject angle "
                       "brackets in a description (platform best practices).", str(skill_md))
        # Both reservations hold outside a plugin only (skills): "skips a skill you author
        # at that name in the enterprise, personal, and project locations", and "outside a
        # plugin, a skill folder or command file whose name is `anthropic-skills` or starts
        # with `anthropic-skills:` doesn't load". A plugin's skills/synced/ loads as
        # <plugin>:synced (external audit, 2026-10-08, Claude Code 2.1.293).
        if ctx.layout != "plugin":
            if entry.name.lower() == "synced":
                report.add("02-skill-md-exists", "ERROR",
                           "A skill folder named 'synced' is skipped: the name is reserved for "
                           "skills synced from claude.ai (skills).", str(skill_md))
            reserved = [n for n in (entry.name, name) if is_anthropic_skills_name(n)]
            if reserved:
                report.add("02-skill-md-exists", "ERROR",
                           f"Skill '{entry.name}' does not load: outside a plugin, a skill folder "
                           f"or frontmatter `name` that is `anthropic-skills` or starts with "
                           f"`anthropic-skills:` is reserved for skills synced from claude.ai "
                           f"(skills). Here: `{reserved[0]}`.", str(skill_md))
        wtu = fm.get("when_to_use", "").strip()
        # "the combined `description` and `when_to_use` text is truncated at 1,536
        # characters in the skill listing" (skills): with no when_to_use, the description
        # alone is what gets cut. Guarded by `wtu` until 0.23.0. The cap is the project's
        # `skillListingMaxDescChars` when set ("The cap is configurable with
        # skillListingMaxDescChars", skills); the constant alone told a project that
        # raised it that the listing cut text it shows in full.
        cap = listing_cap(ctx)
        if len(desc) + len(wtu) > cap:
            report.add("04-skill-description-length", "WARN",
                       f"Skill '{entry.name}': "
                       + ("description + when_to_use is " if wtu else "description is ")
                       + f"{len(desc) + len(wtu)} chars (> {cap}); the "
                       "listing cuts the rest (skills).", str(skill_md))
        if name and name != entry.name:
            # "Must match the parent folder" is the Agent Skills spec's: packaging rejects
            # the skill. In Claude Code the skill still loads - two names, not a failure. As
            # an ERROR on projects it was 39 of 159 ERRORs on a second public sample
            # (2026-09-27), the P2 class again. Which name is the command (skills, "How a
            # skill gets its command name"): in a project `name` sets it and "the directory
            # name also invokes the skill"; in a plugin `name` replaces the directory name
            # in the last segment. Until 0.23.0 this said the command was the folder.
            if ctx.layout == "library":
                how = ": the Agent Skills spec requires them equal, and packaging rejects the skill."
            elif ctx.layout == "plugin":
                how = (f": the command is /<plugin>:{name}, not the folder name (skills). "
                       "Packaging under the Agent Skills spec would reject the mismatch.")
            else:
                how = (f": the command is /{name}, and /{entry.name} also invokes it (skills) - "
                       "two names for one skill. Packaging under the Agent Skills spec would "
                       "reject the mismatch.")
            report.add(
                "03-skill-name-matches-folder",
                "ERROR" if ctx.layout == "library" else "WARN",
                f"Frontmatter name '{name}' does not match folder '{entry.name}'" + how,
                str(skill_md),
            )

        if desc and desc[0] in (">", "|"):
            report.add(
                "02-frontmatter-block-scalar",
                "ERROR",
                f"Skill '{entry.name}' description parsed as a raw block-scalar indicator — frontmatter parser failed.",
                str(skill_md),
            )

        if desc:
            if len(desc) < ctx.limits.DESCRIPTION_MIN_CHARS:
                report.add(
                    "04-skill-description-length",
                    house(ctx),
                    f"Skill '{entry.name}' description is only {len(desc)} chars (min {ctx.limits.DESCRIPTION_MIN_CHARS})."
                    + house_note(f"at least {ctx.limits.DESCRIPTION_MIN_CHARS} chars",
                                 "a description that says what the skill does and when to use "
                                 "it, up to 1,024 chars - no minimum"),
                    str(skill_md),
                )
            if len(desc) > DESCRIPTION_MAX_CHARS:
                report.add(
                    "04-skill-description-length",
                    "WARN",
                    f"Skill '{entry.name}' description is {len(desc)} chars (> {DESCRIPTION_MAX_CHARS}). "
                    "The Agent Skills spec caps 'description' at 1,024 chars "
                    "(agentskills.io/specification), the one upload and packaging validate against. "
                    f"Claude Code's own limit is the listing cutoff: {cap:,} chars for "
                    "'description' + 'when_to_use' combined (skills).",
                    str(skill_md),
                )
            if not ANTI_TRIGGER_RE.search(desc):
                report.add(
                    "04-skill-description-antitrigger",
                    # Family 1: the measurement behind this clause is about confusable
                    # pairs, and check 33 is where it applies as a WARN. On a skill with
                    # no close neighbour the clause is only a cost paid every turn.
                    house(ctx),
                    # The measurement (5/10 -> 0/10 on a near miss, 2026-09-22) was taken on
                    # THIS plugin's skill; quoted in every report, 423 times on a public sample,
                    # it read as a law about everyone's. It lives in the references.
                    f"Skill '{entry.name}' description says when to use it, not when not to. "
                    "A 'Do not use for ...' clause pays where a near request would fire the "
                    "wrong skill (33-description-overlap measures that)."
                    + house_note("an anti-trigger clause in every description",
                                 "nothing for skills; plugin-dev recommends it for agents"),
                    str(skill_md),
                )

        size = skill_md.stat().st_size
        vendored = is_vendored_skill(entry)
        if size > ctx.limits.SKILL_MD_ERROR_BYTES:
            # A house ceiling (skill-anatomy.md), reported as an ERROR until 2026-09-27. The
            # documented mechanism - what survives compaction - is 21's, which fires too:
            # an `elif` until 0.23.0 kept 21 silent above this ceiling, so a 60 KB skill
            # got a NOTICE and a 25 KB one a WARN (external audit, 2026-10-08).
            report.add(
                "05-skill-md-size",
                "NOTICE" if vendored else house(ctx),
                f"SKILL.md in '{entry.name}' is {size} bytes (> {ctx.limits.SKILL_MD_ERROR_BYTES}). Split it."
                + (" Vendored skill — reported for information only." if vendored else
                   house_note(f"at most {ctx.limits.SKILL_MD_ERROR_BYTES} bytes", "under 500 lines (skill "
                              "authoring best practices); past ~5,000 tokens, lost after "
                              "compaction - checked by 21-skill-md-compaction")),
                str(skill_md),
            )
        if size > SKILL_MD_COMPACTION_WARN_BYTES:
            report.add(
                "21-skill-md-compaction",
                "NOTICE" if vendored else "WARN",
                f"SKILL.md in '{entry.name}' is {size} bytes (> {SKILL_MD_COMPACTION_WARN_BYTES}, "
                "roughly 5,000 tokens): content past ~5,000 tokens is dropped after the first "
                "auto-compaction; move detail to references."
                + (" Vendored skill — reported for information only." if vendored else ""),
                str(skill_md),
            )

        if name and name in seen_names:
            # In a project `name` sets the command "unless another command already uses
            # that name", and "the directory name also invokes the skill" (skills): both
            # load, each folder still reaches its own, and only one gets /<name>. Reported
            # as an ERROR in a project until 2026-09-27 - 4 false ERRORs in one fresh
            # public repository. In a plugin `name` is the command, so a duplicate is a
            # real collision.
            project = ctx.layout == "project"
            report.add(
                "06-skill-duplicate-name",
                "NOTICE" if project else "ERROR",
                f"Duplicate skill name '{name}' (also in '{seen_names[name]}')"
                + (f": in a project both load and each folder name still invokes its own, but "
                   f"only one of them gets /{name} (skills)." if project else ""),
                str(skill_md),
            )
        elif name:
            seen_names[name] = entry.name

        for link in dict.fromkeys(l for l, _ in iter_relative_links(text)):
            if exists_from_root(root, link):
                continue
            target = (skill_md.parent / link).resolve()
            try:
                target.relative_to(skill_md.parent.resolve())
            except ValueError:
                continue
            if not target.exists():
                # Same machine-dependence as 20: a target git ignores was installed, not
                # committed.
                rel_target = os.path.relpath(target, root.resolve()).replace(os.sep, "/")
                if ignored(rel_target):
                    report.add("07-skill-broken-link", "NOTICE",
                               f"SKILL.md in '{entry.name}' links to '{link}', under a path git "
                               "ignores: present only where it was installed. Not counted.",
                               str(skill_md))
                    continue
                report.add(
                    "07-skill-broken-link",
                    "ERROR",
                    f"SKILL.md in '{entry.name}' links to non-existent '{link}'",
                    str(skill_md),
                )

        skills[entry.name] = {
            "name": name,
            "description": desc,
            "path": str(skill_md),
            "disable-model-invocation": fm.get("disable-model-invocation", ""),
            "user-invocable": fm.get("user-invocable", ""),
            "paths": fm.get("paths", ""),
        }
    return skills


_SETTINGS_COMMAND_STRINGS = ("apiKeyHelper", "awsAuthRefresh", "awsCredentialExport",
                             "gcpAuthRefresh", "otelHeadersHelper")
_SETTINGS_COMMAND_OBJECTS = ("statusLine", "subagentStatusLine", "fileSuggestion")


def check_no_global_scripts(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    global_scripts = root / ctx.claude_dir / "scripts"
    if not global_scripts.exists():
        return
    files = [p for p in global_scripts.rglob("*") if p.is_file()]
    if not files:
        return
    # A script that a settings hook or the statusLine runs belongs to no skill: hooks in
    # settings run project scripts outside any skill (hooks), so "its owning skill's
    # scripts/" was wrong advice, and following it broke the configured path (external
    # audit, 2026-10-08). Such a script is not reported.
    # Only what runs it counts: the `command` of a command hook and `statusLine.command`.
    # The whole settings text was searched, so a permission rule or an `env` value naming
    # the script exempted it too (external audit 3, 2026-10-08).
    configured = ""
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((root / ctx.claude_dir / name).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        # The other keys whose value is a command Claude Code runs (settings-reference:
        # "a shell command line" for the credential helpers, an object with `command` for
        # fileSuggestion and the two status lines) run a script outside any skill too
        # (external audit 4, 2026-10-08).
        runs = [data.get(key) for key in _SETTINGS_COMMAND_STRINGS]
        runs += [data[key].get("command") for key in _SETTINGS_COMMAND_OBJECTS
                 if isinstance(data.get(key), dict)]
        configured += "\n" + "\n".join(_hook_commands(data.get("hooks"))
                                       + [run for run in runs if isinstance(run, str)])
    # Hooks also live in agent and skill frontmatter ("Hooks in skills and agents",
    # hooks): a script one of them runs belongs to no skill either. Only the `hooks:`
    # block is read - a description or a body that merely mentions the path runs nothing.
    defs = list((root / ctx.claude_dir / "agents").rglob("*.md")) \
        + list((root / ctx.skills_dir).glob("*/SKILL.md"))
    for md in readable_files(defs):
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        configured += "\n" + "\n".join(_hook_commands(frontmatter_hooks(text)))
    prefix = "" if ctx.claude_dir == "." else f"{ctx.claude_dir}/"
    for path in files:
        if f"{prefix}scripts/{path.relative_to(global_scripts).as_posix()}" in configured:
            continue
        report.add(
            "13-no-global-scripts",
            house(ctx),
            f"Script '{path.name}' lives in .claude/scripts/ (global pool). Its owning skill's scripts/ would carry it."
            + house_note("no global .claude/scripts/",
                         "scripts/ inside a skill as its anatomy, and nothing against a project folder"),
            str(path),
        )


def check_reference_sizes(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    if not skills_dir.is_dir():
        return
    for ref in readable_files(skills_dir.glob("*/references/**/*.md")):
        skill_dir = skills_dir / ref.relative_to(skills_dir).parts[0]
        try:
            text = ref.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # `count("\n") + 1` counted a final newline as a line: a 100-line file read as 101
        # and got the WARN the rule ("longer than 100 lines") does not ask for (0.23.0).
        lines = len(text.splitlines())
        if lines <= ctx.limits.REFERENCE_TOC_LINES:
            continue
        head = "\n".join(text.splitlines()[:REFERENCE_TOC_SCAN_LINES]).lower()
        # Any language, any typography: `Contents :` (French spacing), `Sommaire`,
        # `Table des matières`, or a line or list of 3+ anchor links. `contents:` alone
        # missed 7 of 7 French references that had one (2026-09-27).
        # ... with 3 entries or more: a keyword alone (`Contents : see below`) is not one.
        # 3 entries, or as many as the file has sections: a 2-section file lists 2.
        sections = [h for h in re.findall(r"^## (.+)$", text, re.M)
                    if not re.match(r"(?i)\W*(?:table of contents|contents|sommaire|table des mati)", h)]
        needed = min(3, max(1, len(sections)))
        has_toc = len(re.findall(r"\]\(#", head)) >= 3
        head_lines = head.splitlines()
        all_lines = text.lower().splitlines()
        for k, ln in enumerate(head_lines):
            m = re.match(r"^\W*(?:table of contents|contents|sommaire|table des mati[eè]res)\b\W*(.*)$", ln)
            if not m:
                continue
            inline = [e for e in re.split(r"\s*[·,;|]\s*", m.group(1)) if e.strip()]
            listed = 0
            # The list may run past the scanned head: read it from the whole file.
            for nxt in all_lines[k + 1:]:
                if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", nxt):
                    listed += 1
                elif nxt.strip():
                    break
            if len(inline) >= needed or listed >= needed:
                has_toc = True
                break
        rel_name = ref.relative_to(skills_dir).as_posix()
        if not has_toc:
            report.add(
                "16-reference-size",
                "WARN",
                f"Reference '{rel_name}' is {lines} lines (> {ctx.limits.REFERENCE_TOC_LINES}) with no table of contents. "
                "Add one near the top: \"For reference files longer than 100 lines, include a table of "
                "contents\" (Anthropic, skill authoring best practices).",
                str(ref),
            )
        elif lines > ctx.limits.REFERENCE_WARN_LINES and not is_vendored_skill(skill_dir):
            report.add(
                "16-reference-size",
                house(ctx),
                f"Reference '{rel_name}' is {lines} lines (> {ctx.limits.REFERENCE_WARN_LINES}) with a table of contents."
                + house_note(f"split past {ctx.limits.REFERENCE_WARN_LINES} lines",
                             "a table of contents is enough - which this file has"),
                str(ref),
            )


def _flow_closes_early(value: str) -> bool:
    """Whether a value opening a flow collection closes it and goes on: `[beta] Deploy`."""
    depth = 0
    for i, ch in enumerate(value):
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return bool(value[i + 1:].strip())
    return False                                # unclosed here: it may go on next line


def check_frontmatter_quoting(ctx: AuditContext, report: Report) -> None:
    """Flag plain (unquoted) frontmatter scalars containing ': '.

    Claude Code's frontmatter reader is tolerant, but a plain scalar holding
    a colon-space sequence — which every 'Don't use for: ...' anti-trigger
    produces — is invalid under strict YAML and is rejected by js-yaml and
    PyYAML. Quote the value so any downstream consumer can parse the file.
    """
    root = ctx.root
    targets: list[Path] = []
    skills_dir = root / ctx.skills_dir
    agents_dir = root / ctx.agents_dir
    if skills_dir.is_dir():
        targets.extend(readable_files(skills_dir.glob("*/SKILL.md")))
    if agents_dir.is_dir():
        targets.extend(readable_files(agents_dir.rglob("*.md")))

    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not text.startswith("---"):
            continue
        lines = text.splitlines()
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            continue
        for raw in lines[1:end]:
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(\S.*)$", raw)
            if not m:
                continue
            key, scalar = m.group(1), m.group(2).strip()
            where = path.parent.name if path.name == "SKILL.md" else path.stem
            # ` #` opens a YAML comment: a ': ' after it is not in the value, and quoting
            # the line as advised would move the comment into it (external audit, 2026-10-08).
            value = re.split(r"\s#", scalar, maxsplit=1)[0].rstrip()
            if scalar[0] in "[{":
                # A flow collection must close on its own bracket; `[beta] Deploy ...` opens
                # one and strict YAML (PyYAML) rejects the rest. Skipped until 0.23.0. Only a
                # collection closed ON THIS LINE with text after it is reported: `[Read,` may
                # continue on the next line, which this line reader cannot see.
                if _flow_closes_early(value):
                    report.add(
                        "19-frontmatter-quoting",
                        "WARN",
                        f"'{key}' in {where} is an unquoted scalar starting with '{scalar[0]}' — strict YAML reads a flow collection and rejects the rest. Wrap the value in double quotes.",
                        str(path),
                    )
                continue
            if scalar[0] in "\"'>|":
                continue
            if ": " in value:
                report.add(
                    "19-frontmatter-quoting",
                    "WARN",
                    f"'{key}' in {where} is an unquoted scalar containing ': ' — invalid under strict YAML. Wrap the value in double quotes.",
                    str(path),
                )


def check_orphan_references(ctx: AuditContext, report: Report) -> None:
    """Every reference must be reachable from its own SKILL.md.

    A reference linked only from a sibling reference sits two hops from the
    body, and the second hop is the one Claude skips: it gets read partially,
    or not at all. Vendored skills are not exempt — reachability is not a size
    budget. Non-markdown assets are, since they are consumed as data. A file in
    a references/ subdirectory (archives, retired routes) may instead be routed
    from a top-level reference that SKILL.md links — the router pattern.

    Where references live: `references/`, the docs' `reference/`, and markdown files
    at the skill root (`my-skill/reference.md`, skills; the `advanced.md` ->
    `details.md` chain of the best practices). Only `references/` was read until
    0.23.0, so the layouts the docs themselves show were never checked (external
    audit, 2026-10-08). README, CHANGELOG and LICENSE at the root are for people.
    """
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_md.is_file():
            continue
        ref_dirs = [d for d in (skill_dir / "references", skill_dir / "reference") if d.is_dir()]
        top = [p for p in readable_files(skill_dir.glob("*.md"))
               if p.name != "SKILL.md"
               and not re.match(r"(?i)(readme|changelog|license|licence)\b", p.name)]
        for d in ref_dirs:
            top += readable_files(d.glob("*.md"))
        if not top:
            continue
        top_parents = {skill_dir, *ref_dirs}
        try:
            text = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        linked = {(skill_md.parent / link).resolve() for link, _ in iter_relative_links(text)}
        routers: list[tuple[str, set[Path]]] = []
        for router in top:
            router_rel = router.relative_to(skill_dir).as_posix()
            if not (router.resolve() in linked or router_rel in text or router.name in text):
                continue
            try:
                router_text = router.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            router_links = {(router.parent / link).resolve() for link, _ in iter_relative_links(router_text)}
            routers.append((router_text, router_links))
        candidates = list(dict.fromkeys(
            [p for p in top if p.parent == skill_dir]
            + [p for d in ref_dirs for p in readable_files(d.rglob("*.md"))]))
        for ref in candidates:
            rel = ref.relative_to(skill_dir).as_posix()
            if ref.resolve() in linked or rel in text or ref.name in text:
                continue
            if ref.parent not in top_parents and any(
                ref.resolve() in router_links or ref.name in router_text
                for router_text, router_links in routers
            ):
                continue
            report.add(
                "25-orphan-reference",
                "WARN",
                f"Reference '{skill_dir.name}/{rel}' is neither linked nor named from its SKILL.md — "
                "a reference reachable only from another reference gets read partially or not at all.",
                str(ref),
            )


def check_skill_names(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """Shape and reserved words in `name`, per the Agent Skills spec.

    A non-conformant name keeps working locally, which is why it survives: nothing
    fails until the skill is packaged or uploaded. Until 0.23.0 the severity followed
    the container - ERROR in a plugin, on the belief that the name blocks distribution.
    Claude Code documents no such rejection for plugins (see below), so it is a WARN
    everywhere: a latent problem that surfaces the day the skill is packaged.
    """
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    # Corrected 0.23.0 (external audit, 2026-10-08): the plugin ERROR rested on the spec
    # alone, and Claude Code scopes that validation to "claude.ai skill uploads, the
    # Skills API, and packaging with `package_skill.py`" (skills) - not to plugins. No
    # Claude Code rejection of a plugin skill's name is documented: WARN everywhere.
    own_prefix = f"{plugin_name(root)}:" if ctx.layout == "plugin" else None
    for name in sorted(skills):
        loc = str(skills_dir / name / "SKILL.md")
        declared = str(skills[name].get("name") or name)
        # "If the `name` you write already starts with the plugin's own prefix, Claude
        # Code doesn't add the prefix again on v2.1.246 or later" (skills): documented as
        # valid, so the shape is read on what follows the prefix.
        shape = declared[len(own_prefix):] if own_prefix and declared.startswith(own_prefix) else declared
        if not SKILL_NAME_RE.match(shape):
            report.add("32-skill-name-shape", "WARN",
                       f"Skill name `{declared}` is not lowercase letters, digits and single "
                       "hyphens (agentskills.io/specification). Claude Code loads it; the spec "
                       "rejects it when the skill is packaged or uploaded.", loc)
        if len(shape) > SKILL_NAME_MAX_CHARS:
            report.add("32-skill-name-shape", "WARN",
                       f"Skill name `{declared}` is {len(shape)} chars (max "
                       f"{SKILL_NAME_MAX_CHARS}).", loc)
        # The Agent Skills specification enumerates the `name` constraints in full -
        # 1-64 characters, lowercase alphanumerics and hyphens, no leading, trailing
        # or consecutive hyphen, and it must match the parent directory. Verified
        # 2026-09-22 at agentskills.io/specification: THERE IS NO RESERVED WORD.
        #
        # This check used to raise an ERROR saying "the spec forbids them", and it
        # fired on a third party's plugin. A rule invented and attributed to a
        # standard is worse than no rule: the reader learns it, and learns it wrong.
        # Kept as INFO, sourced honestly, because the concern is real - a name
        # carrying a vendor's is a poor name - but it is an opinion, not a rule.
        # Corrected 2026-09-23: the open spec has no reserved word, but Anthropic's
        # platform does - "Cannot contain reserved words: 'anthropic', 'claude'"
        # (platform.claude.com, agent-skills best practices). Claude Code accepts the
        # name; claude.ai and the Skills API refuse it. WARN: rejected somewhere real.
        hit = [t for t in RESERVED_NAME_TOKENS if t in declared.lower()]
        if hit:
            # Outside a plugin, `anthropic-skills` does NOT load (skills): 02-skill-md-exists
            # reports it as an ERROR; "Claude Code loads it" was false there until 0.23.0.
            unloaded = ctx.layout != "plugin" and (is_anthropic_skills_name(declared)
                                                  or is_anthropic_skills_name(name))
            report.add(
                "32-skill-name-reserved", "WARN",
                f"Skill name `{declared}` contains `{', '.join(hit)}`: "
                + ("outside a plugin Claude Code does not load it (02-skill-md-exists), and "
                   if unloaded else "Claude Code loads it, but ")
                + "claude.ai and the Skills API reject reserved words in `name` "
                "(platform.claude.com, agent-skills best practices).",
                loc)
