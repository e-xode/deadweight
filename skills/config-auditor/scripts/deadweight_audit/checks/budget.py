"""The always-loaded budget: what every session pays before the first message."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..context import AuditContext
from ..limits import (CHARS_PER_TOKEN, CONTEXT_WINDOW_TOKENS, DESCRIPTION_LISTING_MAX_CHARS,
                      LISTING_FRACTION_DEFAULT)
from ..parsing.frontmatter import YAML_TRUE, frontmatter_list, parse_frontmatter
from ..parsing.markdown import injected_memory
from ..repo import claude_md_path, expand_imports, project_memory_files, readable_files
from ..report import Report, house, house_note


def project_settings(ctx: AuditContext) -> dict:
    """`.claude/settings.json` overlaid by `.claude/settings.local.json`, as one dict.

    The local file is where `/skills` saves `skillOverrides` ("`Esc` to save to
    `.claude/settings.local.json`", skills); reading the shared file alone counted
    skills the user had turned off as listed (audit externe 2026-10-08, P2-C--01).
    Local wins key by key; `env` and `skillOverrides` are merged entry by entry.
    """
    merged: dict = {}
    for name in ("settings.json", "settings.local.json"):
        f = ctx.root / ctx.claude_dir / name
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if key in ("env", "skillOverrides") and isinstance(value, dict):
                merged.setdefault(key, {}).update(value)
            else:
                merged[key] = value
    for key in ("env", "skillOverrides"):
        if not isinstance(merged.get(key, {}), dict):
            merged[key] = {}
    return merged


def listing_cap(ctx: AuditContext) -> int:
    """Per-entry cap of the listing: 1,536 chars, or `skillListingMaxDescChars` (skills)."""
    value = project_settings(ctx).get("skillListingMaxDescChars") if ctx.layout != "plugin" else None
    return int(value) if isinstance(value, (int, float)) and value > 0 else DESCRIPTION_LISTING_MAX_CHARS


def _when_to_use(meta: dict) -> str:
    try:
        fm, _ = parse_frontmatter(Path(meta.get("path", "")).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return ""
    return (fm or {}).get("when_to_use", "").strip()


def entry_chars(meta: dict, cap: int) -> int:
    """What one skill's entry costs in the listing: description + when_to_use, capped.

    `when_to_use` is "Appended to `description` in the skill listing and counts toward
    the 1,536-character cap"; "each entry's combined text is capped at 1,536 characters
    regardless of budget" (skills). Counting `description` alone reported 4% of a
    listing that overflowed (audit externe 2026-10-08, P1-C--02 and P2-C--02). Whether
    a separator between the two is counted is not documented, and not counted here.
    """
    wtu = meta.get("when_to_use")
    if wtu is None:
        wtu = _when_to_use(meta)
    return min(len(meta.get("description", "")) + len(wtu), cap)


def listed_commands(ctx: AuditContext, skills: dict[str, dict]) -> dict[str, int]:
    """Listing chars of each `.claude/commands/**/*.md` the model sees, by command name.

    "Custom commands have been merged into skills" and a command file "supports the
    same frontmatter except `name` and `paths`" (skills): its description is listed like
    a skill's, and when there is none "the first non-empty line of the markdown content"
    stands in. Left out: `disable-model-invocation: true`, a `skillOverrides` entry other
    than "on", and a command shadowed by a skill of the same name ("A skill and a file in
    `.claude/commands/` | The skill", skills). Named by file stem: how a nested folder
    names a command is not measured here (audit externe 2026-10-08, P2-C--03).
    """
    base = ctx.root / ctx.claude_dir / "commands"
    if not base.is_dir():
        return {}
    overrides = project_settings(ctx).get("skillOverrides", {}) if ctx.layout != "plugin" else {}
    cap = listing_cap(ctx)
    out: dict[str, int] = {}
    for f in readable_files(base.rglob("*.md")):
        name = f.stem
        if name in skills or str(overrides.get(name, "on")).strip().lower() != "on":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm, end = parse_frontmatter(text)
        fm = fm or {}
        if str(fm.get("disable-model-invocation", "")).strip().lower() in YAML_TRUE:
            continue
        desc = fm.get("description", "").strip()
        if not desc:
            body = text.splitlines()[end + 1:] if fm else text.splitlines()
            desc = next((l.strip() for l in body if l.strip()), "")
        out[name] = min(len(desc) + len(fm.get("when_to_use", "").strip()), cap)
    return out


def always_loaded_memory(ctx: AuditContext) -> list[tuple[str, int]]:
    """(label, bytes) of every memory file loaded at launch.

    The project CLAUDE.md files and CLAUDE.local.md ("All discovered files are
    concatenated into context"), what they import ("imported files also load at
    launch"), and the rules with no `paths:` ("loaded at launch with the same priority
    as `.claude/CLAUDE.md`") - all from memory. One CLAUDE.md alone reported 87 KB
    loaded at launch as 13 chars (audit externe 2026-10-08, P1-C--00). HTML comments
    are taken out of the CLAUDE.md files only, where the stripping is documented.
    """
    root = ctx.root
    out: list[tuple[str, int]] = []
    seen: set[str] = set()

    def add(p, injected: bool) -> None:
        real = os.path.realpath(p)
        if real in seen:
            return
        seen.add(real)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        size = len((injected_memory(text) if injected else text).encode("utf-8"))
        try:
            label = p.relative_to(root).as_posix()
        except ValueError:
            label = str(p)
        out.append((label, size))

    memory = project_memory_files(root)
    for f in memory:
        add(f, True)
    rules = root / ctx.claude_dir / "rules"
    if rules.is_dir():
        for f in readable_files(rules.rglob("*.md")):
            try:
                fm, _ = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if not frontmatter_list((fm or {}).get("paths", "")):
                add(f, False)
    # Imports are documented for CLAUDE.md files; whether a rule's `@path` expands is
    # not, so a rule's imports are not counted.
    for f in memory:
        for imported in expand_imports(f):
            add(imported, False)
    return out


def listing_hidden_skills(ctx: AuditContext, skills: dict[str, dict]) -> set[str]:
    """Skills whose description is NOT paid for in the per-turn skill listing.

    Three mechanisms withhold a description: `disable-model-invocation: true` in
    the skill's own frontmatter, a `skillOverrides` entry in
    `.claude/settings.json` or `.claude/settings.local.json` (where `/skills` writes it)
    set to anything other than "on" - never for a plugin, whose skills "are not affected
    by `skillOverrides`" (skills) - and a non-empty
    `paths:` frontmatter list. The last one is not documented as a withholding
    mechanism by Anthropic, but it was measured twice on this project — headless
    on 2026-09-03, interactive on 2026-09-09 — to remove the skill from the
    listing entirely (name and description) and to make it uninvocable by name,
    with no auto-load and no next-turn offer when a matching file is touched.
    The pilot was closed on 2026-09-09 and no skill carries `paths:` any more;
    this branch is kept as a regression guard, so that a re-added `paths:`
    surfaces as "withheld but not named in the Skills index" instead of a
    silently unreachable skill.
    See references/skill-runtime-mechanisms.md, section Path-scoped skills.

    All three are invisible to a naive character count, which is why the budget
    is reported twice.
    """
    hidden = {
        name
        for name, data in skills.items()
        if str(data.get("disable-model-invocation", "")).strip().lower() in YAML_TRUE
        or frontmatter_list(data.get("paths", ""))
    }
    if ctx.layout == "plugin":
        # "Plugin skills are not affected by `skillOverrides`" (skills): a plugin-root
        # settings.json naming one made check 30 report 0 chars (audit externe
        # 2026-10-08, P1-C--07).
        return hidden
    for name, state in project_settings(ctx).get("skillOverrides", {}).items():
        if name in skills and str(state).strip().lower() != "on":
            hidden.add(name)
    return hidden


def unreachable_skills(ctx: AuditContext, skills: dict[str, dict]) -> set[str]:
    """Withheld skills the model cannot come upon by itself - the index's subject.

    `paths:` withholds a skill from the STARTING listing but does not make it
    unreachable: measured 2026-09-23 on 2.1.280, a `paths: src/**` skill is absent
    from the session's init event, absent after reading README.md (2 of 2), and
    present after reading src/a.ts (2 of 2). The docs say the same: "Claude loads
    the skill automatically only when working with files matching the patterns".
    An earlier measurement on 2.1.259 had found it never loaded. It is counted out
    of the budget, and not demanded in the index.
    """
    return {n for n in listing_hidden_skills(ctx, skills)
            if not (frontmatter_list(skills[n].get("paths", ""))
                    and str(skills[n].get("disable-model-invocation", "")).strip().lower()
                    not in YAML_TRUE)}


def check_always_loaded_budget(
    ctx: AuditContext, report: Report, skills: dict[str, dict] | None, agents: dict[str, dict]
) -> None:
    """`skills` is None when check_skills crashed: every term is non-negative, so CLAUDE.md
    and the agents alone are a lower bound, reported as one (audit externe 3, g--01)."""
    root = ctx.root
    claude_md = claude_md_path(root)
    memory = always_loaded_memory(ctx)
    claude_md_bytes = sum(n for _, n in memory)
    unmeasured = skills is None
    skills = skills or {}
    hidden = listing_hidden_skills(ctx, skills)
    cap = listing_cap(ctx)
    raw_skill_chars = sum(entry_chars(s, cap) for s in skills.values())
    skill_chars = sum(entry_chars(s, cap) for name, s in skills.items() if name not in hidden)
    # Commands are left out too: which ones a skill shadows is unknown without the skill list.
    commands = {} if unmeasured else listed_commands(ctx, skills)
    command_chars = sum(commands.values())
    agent_chars = sum(len(a.get("description", "")) for a in agents.values())
    total = claude_md_bytes + skill_chars + command_chars + agent_chars
    suppressed = raw_skill_chars - skill_chars
    detail = (
        f" [{len(hidden)} skill(s) withheld from the listing: {suppressed} chars not paid; "
        f"raw skill total {raw_skill_chars}]"
        if hidden
        else ""
    )
    # The single-CLAUDE.md wording is kept when that is all that loads.
    if [label for label, _ in memory] in ([], ["CLAUDE.md"]):
        memory_part = f"CLAUDE.md {claude_md_bytes} B"
    else:
        memory_part = (f"memory files {claude_md_bytes} B: "
                       + ", ".join(f"{label} {n}" for label, n in memory))
    command_part = f" + command descriptions {command_chars}" if commands else ""
    message = (
        f"Always-loaded context: {total} chars "
        f"({memory_part} + skill descriptions {skill_chars}{command_part} + agent descriptions {agent_chars})."
        f"{detail}"
    ) if not unmeasured else (
        f"Always-loaded context: at least {total} chars ({memory_part} + agent descriptions "
        f"{agent_chars}); skill and command descriptions not measured, check_skills crashed."
    )
    if total > ctx.limits.ALWAYS_LOADED_ERROR_CHARS:
        report.add(
            "17-always-loaded-budget",
            house(ctx),
            f"{message} Exceeds the hard budget ({ctx.limits.ALWAYS_LOADED_ERROR_CHARS}). Trim descriptions or CLAUDE.md."
            + house_note("a global always-loaded budget", "per-mechanism budgets only - the "
                         "skill listing is sized from skillListingBudgetFraction (check 29)"),
            str(claude_md),
        )
    elif total > ctx.limits.ALWAYS_LOADED_WARN_CHARS:
        report.add(
            "17-always-loaded-budget",
            house(ctx),
            f"{message} Above the target budget ({ctx.limits.ALWAYS_LOADED_WARN_CHARS}).",
            str(claude_md),
        )
    else:
        report.add("17-always-loaded-budget", "INFO", message, str(claude_md))
    if not unmeasured and skill_chars + command_chars > ctx.limits.SKILL_DESC_AGGREGATE_WARN_CHARS:
        report.add(
            "17-always-loaded-budget",
            house(ctx),
            # Commands count here ("Custom commands have been merged into skills", skills);
            # the label says so, or it contradicted the breakdown above (audit externe 3, g4-07).
            f"Skill and command descriptions total {skill_chars + command_chars} chars "
            f"(skills {skill_chars}, commands {command_chars}; > {ctx.limits.SKILL_DESC_AGGREGATE_WARN_CHARS}). "
            "The harness's own listing ceiling is derived in check 29; this is a house ratchet below it.",
            str(claude_md),
        )


# plafond derive
def check_listing_budget_derived(ctx: AuditContext, report: Report, skills: dict) -> None:
    """The listing ceiling this repository actually has, derived from its settings.

    The harness gives the skill listing a fraction of the context window (1% by
    default), scaled by `skillListingBudgetFraction`. On overflow the listing keeps
    every skill NAME and drops DESCRIPTIONS, least-invoked first - silently. So the
    real ceiling is a per-repository number even though the rule is the same
    everywhere. That is why this check derives it instead of hard-coding it: the
    fraction is a dial the repository owns.
    """
    root = ctx.root
    fraction = LISTING_FRACTION_DEFAULT
    source = "harness default"
    settings = project_settings(ctx)
    value = settings.get("skillListingBudgetFraction")
    if isinstance(value, (int, float)) and value > 0:
        fraction, source = float(value), "skillListingBudgetFraction"
    ceiling = int(fraction * CONTEXT_WINDOW_TOKENS * CHARS_PER_TOKEN)
    formula = (f"{fraction} x {CONTEXT_WINDOW_TOKENS} tokens x {CHARS_PER_TOKEN} chars/token, an "
               "optimistic ratio measured at 2.85 on this plugin's own description, so this "
               "ceiling is generous and a token figure under it is a floor; from " + source)
    # "or the `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable to a fixed character
    # count" (skills): set in a settings `env`, it is the ceiling. Which one wins when the
    # fraction is set too is not documented, and the message says so. A variable exported
    # in the user's shell cannot be seen from here (audit externe 2026-10-08, P1-C--03).
    fixed = str(settings.get("env", {}).get("SLASH_COMMAND_TOOL_CHAR_BUDGET", "")).strip()
    if fixed.isdigit() and int(fixed) > 0:
        ceiling = int(fixed)
        formula = ("SLASH_COMMAND_TOOL_CHAR_BUDGET in the settings env, a fixed character count"
                   + ("; skillListingBudgetFraction is set too, and which of the two the harness "
                      "applies is not documented" if source != "harness default" else ""))
    # Only what the listing carries: withheld skills cost nothing, and commands are listed
    # like skills. The `listed` key this filtered on was never set, so every skill counted
    # (audit externe 2026-10-08, P1-C--01, P2-C--00, P2-C--03).
    hidden = listing_hidden_skills(ctx, skills)
    cap = listing_cap(ctx)
    listed = sum(entry_chars(meta, cap) for name, meta in skills.items()
                 if isinstance(meta, dict) and name not in hidden)
    listed += sum(listed_commands(ctx, skills).values())
    pct = 100 * listed / ceiling if ceiling else 0
    severity = "ERROR" if listed > ceiling else ("WARN" if pct > 80 else "INFO")
    report.add(
        "29-listing-budget-derived",
        severity,
        f"Listed skill descriptions: {listed} chars against a derived ceiling of {ceiling} "
        f"({formula}) - {pct:.0f}% used. Past the ceiling the listing silently keeps names and "
        f"drops descriptions, least-invoked first. The chars/token ratio is rough: treat this "
        f"as an order of magnitude, and {ctx.limits.ALWAYS_LOADED_WARN_CHARS} as the house ratchet.",
        str(root / ctx.claude_dir / "settings.json"),
    )


def check_plugin_cost(
    ctx: AuditContext, report: Report, skills: dict[str, dict], agents: dict[str, dict]
) -> None:
    """The always-loaded cost this plugin imposes on EACH consuming project.

    A plugin has no always-loaded budget of its own - no CLAUDE.md, no settings,
    no project context to fill. That does not make its descriptions free: they
    are paid for by every project that installs it, once per project. The budget
    check therefore does not disappear when the container is a plugin, it
    INVERTS. Check 17 asks "what does this project carry?"; check 30 asks "what
    does this plugin add to everyone who installs it?".

    Namespacing is real and reported separately: a plugin skill appears in the
    listing as `plugin-name:skill-name`, so the manifest name plus a colon is
    paid once per listed skill on top of the description.
    """
    root = ctx.root
    manifest = root / ".claude-plugin" / "plugin.json"
    try:
        plugin_name = str(json.loads(manifest.read_text(encoding="utf-8-sig")).get("name") or root.name)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        plugin_name = root.name

    hidden = listing_hidden_skills(ctx, skills)
    listed = {n: sk for n, sk in skills.items() if n not in hidden}
    cap = listing_cap(ctx)
    skill_chars = sum(entry_chars(sk, cap) for sk in listed.values())
    agent_chars = sum(len(a.get("description", "")) for a in agents.values())
    total = skill_chars + agent_chars
    namespacing = sum(len(plugin_name) + 1 for _ in listed)

    detail = ""
    if hidden:
        suppressed = sum(entry_chars(skills[n], cap) for n in hidden)
        detail = (
            f" [{len(hidden)} skill(s) withheld from the listing: {suppressed} chars"
            " not paid by consumers]"
        )
    message = (
        f"Plugin `{plugin_name}` adds {total} chars to the always-loaded context of "
        f"EACH consuming project ({len(listed)} skill description(s) {skill_chars} + "
        f"{len(agents)} agent description(s) {agent_chars}), plus {namespacing} chars of "
        f"`{plugin_name}:` namespacing in the skill listing. This cost is NOT negotiable downstream: `skillOverrides` does not reach a plugin skill (measured 2026-09-22), so a consuming project can only disable the whole plugin.{detail}"
    )
    if total > ctx.limits.PLUGIN_COST_WARN_CHARS:
        report.add(
            "30-plugin-cost",
            house(ctx),
            f"{message} Above {ctx.limits.PLUGIN_COST_WARN_CHARS} chars: every consumer pays this on "
            "every turn. Trim the descriptions or split the plugin."
            + house_note(f"at most {ctx.limits.PLUGIN_COST_WARN_CHARS} chars per plugin",
                         "no per-plugin ceiling; the listing budget is 1% of the context"),
            str(manifest),
        )
    else:
        report.add("30-plugin-cost", "INFO", message, str(manifest))
