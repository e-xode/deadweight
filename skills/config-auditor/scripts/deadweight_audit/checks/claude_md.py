"""CLAUDE.md: size, cross-references, the skills index."""
from __future__ import annotations

import os
import re

from ..checks.budget import unreachable_skills
from ..context import AuditContext
from ..parsing.markdown import injected_memory, strip_code_fences
from ..repo import claude_md_path
from ..report import Report, house, house_note


def check_claude_md(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    path = claude_md_path(root)
    if not path.exists():
        local = root / "CLAUDE.local.md"
        if (root / "AGENTS.md").is_file() and local.is_file() \
                and "@AGENTS.md" not in local.read_text(encoding="utf-8", errors="replace"):
            # "Because CLAUDE.local.md counts, adding one [...] in a project that relies on
            # AGENTS.md stops Claude from reading AGENTS.md for you" (memory, 2026-09-28).
            report.add("01-agents-md-unread", "WARN",
                       "AGENTS.md is not read on this machine: a CLAUDE.local.md exists, and by "
                       "default (`claude-md-or-agents-md`) any CLAUDE.md, .claude/CLAUDE.md or "
                       "CLAUDE.local.md stops Claude Code from reading AGENTS.md. Add `@AGENTS.md` "
                       "to CLAUDE.local.md, or set Project instructions to "
                       "`claude-md-and-agents-md` in your user settings (memory).",
                       str(root / "AGENTS.md"))
            return
        if (root / "AGENTS.md").is_file():
            report.add("01-claude-md-exists", "INFO",
                       "No CLAUDE.md, but an AGENTS.md: Claude Code reads AGENTS.md when no "
                       "CLAUDE.md exists (memory, 'AGENTS.md').", str(root / "AGENTS.md"))
            return
        report.add("01-claude-md-exists", "INFO",
                   "No CLAUDE.md: it is optional, and nothing here is read every session.",
                   str(path))
        return
    raw = path.read_text(encoding="utf-8")
    size = len(injected_memory(raw).encode("utf-8"))
    comments = path.stat().st_size - size
    if size > ctx.limits.CLAUDE_MD_MAX_BYTES:
        report.add(
            "01-claude-md-size",
            house(ctx),
            f"CLAUDE.md is {size} bytes (max {ctx.limits.CLAUDE_MD_MAX_BYTES}). Move knowledge to skills."
            + house_note(f"at most {ctx.limits.CLAUDE_MD_MAX_BYTES} bytes",
                         "under 200 lines (memory) - checked by 01-claude-md-lines"),
            str(path),
        )
    else:
        report.add("01-claude-md-size", "OK", f"CLAUDE.md size {size} bytes <= {ctx.limits.CLAUDE_MD_MAX_BYTES}"
                   + (f" ({comments} bytes of HTML comments not injected)." if comments else "."), str(path))

    text = raw
    injected = injected_memory(raw)
    lines = injected.count("\n") + (0 if injected.endswith("\n") or not injected else 1)
    if lines > ctx.limits.CLAUDE_MD_MAX_LINES:
        report.add("01-claude-md-lines", "WARN",
                   f"CLAUDE.md is {lines} lines (> {ctx.limits.CLAUDE_MD_MAX_LINES}). \"Files over 200 lines "
                   "consume more context and may reduce adherence\" (memory).", str(path))
    agents_md = root / "AGENTS.md"
    # One file linked to the other is read once, and read: "A CLAUDE.md symlinked to
    # AGENTS.md: nothing [to do]" (memory). Missed, it was 16 of 144 findings on 600
    # public repositories (2026-09-27).
    same_file = agents_md.exists() and os.path.realpath(agents_md) == os.path.realpath(path)
    if agents_md.is_file() and not same_file and "@AGENTS.md" not in text:
        report.add("01-agents-md-unread", "WARN",
                   "AGENTS.md sits beside a CLAUDE.md that does not import it. By default "
                   "(`claude-md-or-agents-md`), Claude Code reads AGENTS.md only when no CLAUDE.md "
                   "exists - a CLAUDE.md that names it in words is not enough. Add `@AGENTS.md`, or "
                   "make one a symlink to the other; the user setting `claude-md-and-agents-md` "
                   "reads both, but only for whoever sets it (memory).",
                   str(agents_md))
    stripped = strip_code_fences(text)
    # `/*` after a word is a glob (`lib/*.v`) or bold markdown (`**agent/**`), not a
    # comment: 9 of 12 findings on a public sample, 2026-09-27.
    if re.search(r"^\s*//", stripped, re.MULTILINE) or re.search(r"(?:^|\s)/\*(?!!)", stripped, re.M):
        report.add(
            "12-no-code-comments",
            house(ctx),
            "CLAUDE.md contains // or /* */ outside fenced code blocks."
            + house_note("prose only, no code comments", "nothing on this"),
            str(path),
        )


def check_cross_refs(
    ctx: AuditContext, report: Report, skills: dict[str, dict], agents: dict[str, dict]
) -> None:
    root = ctx.root
    claude_md = claude_md_path(root)
    if not claude_md.exists():
        return
    text = claude_md.read_text(encoding="utf-8")

    referenced_agents: set[str] = set()
    agents_table_match = re.search(
        r"##\s+Agents directory.*?(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE
    )
    if agents_table_match:
        block = agents_table_match.group(0)
        for m in re.finditer(r"\|\s*`([a-z0-9-]+)`\s*\|", block):
            referenced_agents.add(m.group(1))

    for agent_name in agents:
        if agent_name not in referenced_agents:
            report.add(
                "09-agent-in-claude-md",
                house(ctx),
                f"Agent '{agent_name}' exists in .claude/agents/ but is not listed in CLAUDE.md 'Agents directory'."
                + house_note("an '## Agents directory' table in CLAUDE.md",
                             "nothing - the harness already lists every agent's description, "
                             "so the table is paid twice"),
                str(claude_md),
            )
    for ref in referenced_agents:
        if ref not in agents:
            report.add(
                "09-claude-md-agent-missing",
                "WARN",   # a table that names a missing agent points at nothing, whatever the profile
                f"CLAUDE.md references agent '{ref}' but .claude/agents/{ref}.md does not exist",
                str(claude_md),
            )


def check_skill_index(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """The CLAUDE.md index names only the skills the harness listing withholds.

    The per-turn listing already carries every visible skill's name and
    description, so re-listing all of them in CLAUDE.md pays twice. What the
    listing cannot convey is what it is hiding: a `disable-model-invocation`
    skill is absent entirely, and a `skillOverrides` entry may strip the
    description. Those are exactly the entries this section must carry, and
    exactly what this check reconciles.
    """
    root = ctx.root
    claude_md = claude_md_path(root)
    if not claude_md.exists() or not skills:
        return
    text = claude_md.read_text(encoding="utf-8")
    section = re.search(r"##\s+Skills index.*?(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    hidden = unreachable_skills(ctx, skills)
    # Withheld from the model AND from the / menu: nobody can run it. That one is
    # a defect on the documented mechanism, whatever the house convention says.
    dead = {n for n in hidden
            if str(skills[n].get("user-invocable", "")).strip().lower() in {"false", "no", "off", "0"}}
    for name in sorted(dead):
        report.add("15-skill-index", "ERROR",
                   f"Skill '{name}' sets both disable-model-invocation and user-invocable: "
                   "false: neither the model nor the user can invoke it (skills).",
                   str(root / ctx.skills_dir / name / "SKILL.md"))
    hidden -= dead
    if not section:
        # The section exists to point at what the listing withholds. With nothing
        # withheld, its right content is empty, and demanding an empty heading was
        # an error on every project outside the fleet it was calibrated on: a
        # minimal clean project failed on first contact. The defect is not the
        # missing heading; it is a withheld skill that nothing points at.
        if not hidden:
            report.add(
                "15-skill-index",
                "INFO",
                "No 'Skills index' section, and no skill is withheld from the harness listing: "
                "nothing needs one.",
                str(claude_md),
            )
        # A house convention, not a defect: a withheld skill still runs when the user
        # types /name - only the model cannot route to it. As an ERROR it was 39 of
        # 98 ERRORs on a 150-repository sample (2026-09-27), all release or notes
        # skills withheld on purpose.
        for name in sorted(hidden):
            report.add(
                "15-skill-index",
                house(ctx),
                f"Skill '{name}' is withheld from the harness listing: the model cannot pick "
                f"it on its own, and only someone who knows to type /{name} will reach it. "
                "Nothing in CLAUDE.md names it."
                + house_note("a 'Skills index' section in CLAUDE.md naming every withheld skill",
                             "nothing - disable-model-invocation is meant for skills the user "
                             "triggers by hand"),
                str(claude_md),
            )
        return
    body = "\n".join(l for l in section.group(0).splitlines() if not l.lstrip().startswith("➜"))
    indexed = {m.group(1) for m in re.finditer(r"`([a-z0-9][a-z0-9-]+)`", body)}

    for name in sorted(hidden):
        if name not in indexed:
            report.add(
                "15-skill-index",
                house(ctx),
                f"Skill '{name}' is withheld from the harness listing but is not named in the "
                f"CLAUDE.md 'Skills index': the model cannot pick it on its own, and only someone "
                f"who knows to type /{name} will reach it.",
                str(claude_md),
            )
    for ref in sorted(indexed):
        if ref in skills and ref not in hidden:
            report.add(
                "15-skill-index",
                "WARN",
                f"CLAUDE.md 'Skills index' names '{ref}', but that skill is fully listed by the harness. "
                "Drop the entry: the index carries withheld skills only.",
                str(claude_md),
            )
