"""The always-loaded budget: what every session pays before the first message."""
from __future__ import annotations

import json

from ..context import AuditContext
from ..limits import CHARS_PER_TOKEN, CONTEXT_WINDOW_TOKENS, LISTING_FRACTION_DEFAULT
from ..parsing.frontmatter import YAML_TRUE, frontmatter_list
from ..parsing.markdown import injected_memory
from ..repo import claude_md_path
from ..report import Report, house, house_note


def listing_hidden_skills(ctx: AuditContext, skills: dict[str, dict]) -> set[str]:
    """Skills whose description is NOT paid for in the per-turn skill listing.

    Three mechanisms withhold a description: `disable-model-invocation: true` in
    the skill's own frontmatter, a `skillOverrides` entry in
    `.claude/settings.json` set to anything other than "on", and a non-empty
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
    root = ctx.root
    hidden = {
        name
        for name, data in skills.items()
        if str(data.get("disable-model-invocation", "")).strip().lower() in YAML_TRUE
        or frontmatter_list(data.get("paths", ""))
    }
    settings = root / ctx.claude_dir / "settings.json"
    if settings.is_file():
        try:
            overrides = json.loads(settings.read_text(encoding="utf-8-sig")).get("skillOverrides", {})
        except (json.JSONDecodeError, UnicodeDecodeError):
            overrides = {}
        for name, state in overrides.items():
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
    ctx: AuditContext, report: Report, skills: dict[str, dict], agents: dict[str, dict]
) -> None:
    root = ctx.root
    claude_md = claude_md_path(root)
    claude_md_bytes = (len(injected_memory(claude_md.read_text(encoding="utf-8")).encode("utf-8"))
                       if claude_md.exists() else 0)
    hidden = listing_hidden_skills(ctx, skills)
    raw_skill_chars = sum(len(s.get("description", "")) for s in skills.values())
    skill_chars = sum(
        len(s.get("description", "")) for name, s in skills.items() if name not in hidden
    )
    agent_chars = sum(len(a.get("description", "")) for a in agents.values())
    total = claude_md_bytes + skill_chars + agent_chars
    suppressed = raw_skill_chars - skill_chars
    detail = (
        f" [{len(hidden)} skill(s) withheld from the listing: {suppressed} chars not paid; "
        f"raw skill total {raw_skill_chars}]"
        if hidden
        else ""
    )
    message = (
        f"Always-loaded context: {total} chars "
        f"(CLAUDE.md {claude_md_bytes} B + skill descriptions {skill_chars} + agent descriptions {agent_chars})."
        f"{detail}"
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
    if skill_chars > ctx.limits.SKILL_DESC_AGGREGATE_WARN_CHARS:
        report.add(
            "17-always-loaded-budget",
            house(ctx),
            f"Skill descriptions alone total {skill_chars} chars (> {ctx.limits.SKILL_DESC_AGGREGATE_WARN_CHARS}). "
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
    settings = root / ctx.claude_dir / "settings.json"
    if settings.is_file():
        try:
            value = json.loads(settings.read_text(encoding="utf-8-sig")).get("skillListingBudgetFraction")
            if isinstance(value, (int, float)) and value > 0:
                fraction, source = float(value), "skillListingBudgetFraction"
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
    ceiling = int(fraction * CONTEXT_WINDOW_TOKENS * CHARS_PER_TOKEN)
    listed = sum(len(meta.get("description", "")) for meta in skills.values()
                 if isinstance(meta, dict) and meta.get("listed", True))
    pct = 100 * listed / ceiling if ceiling else 0
    severity = "ERROR" if listed > ceiling else ("WARN" if pct > 80 else "INFO")
    report.add(
        "29-listing-budget-derived",
        severity,
        f"Listed skill descriptions: {listed} chars against a derived ceiling of {ceiling} "
        f"({fraction} x {CONTEXT_WINDOW_TOKENS} tokens x {CHARS_PER_TOKEN} chars/token, an optimistic ratio measured at 2.85 on this plugin's own description, so this ceiling is generous and a token figure under it is a floor; from "
        f"{source}) - {pct:.0f}% used. Past the ceiling the listing silently keeps names and "
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
    skill_chars = sum(len(sk.get("description", "")) for sk in listed.values())
    agent_chars = sum(len(a.get("description", "")) for a in agents.values())
    total = skill_chars + agent_chars
    namespacing = sum(len(plugin_name) + 1 for _ in listed)

    detail = ""
    if hidden:
        suppressed = sum(len(skills[n].get("description", "")) for n in hidden)
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
