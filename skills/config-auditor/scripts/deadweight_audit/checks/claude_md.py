"""CLAUDE.md: size, cross-references, the skills index."""
from __future__ import annotations

import os
import re

from ..checks.budget import unreachable_skills
from ..context import AuditContext
from ..parsing.markdown import injected_memory, strip_code_fences
from ..repo import claude_md_path, expand_imports, project_memory_files
from ..report import Report, house, house_note


MEMORY_NAMES = ("CLAUDE.md", "CLAUDE.local.md")


def check_memory_file_case(root, report: Report) -> None:
    """A memory file whose name differs from CLAUDE.md / CLAUDE.local.md only by case.

    Measured on Linux, Claude Code 2.1.291 (2026-10-06): a `claude.md` holding a codeword was
    not loaded (the session answered NONE), the same file named `CLAUDE.md` was. macOS and
    Windows are NOT measured: whether Claude Code loads it there is unknown, so the message
    says only what was measured. Read from the directory listing, never through exists(),
    whose answer depends on the filesystem's case handling.
    """
    # Where each name is a memory file (memory): CLAUDE.md at the root or in .claude/,
    # CLAUDE.local.md at the root only - advising `.claude/CLAUDE.local.md` would move the
    # file to another name that does not load either (found by review, 2026-10-08).
    for folder, allowed in ((root, MEMORY_NAMES), (root / ".claude", ("CLAUDE.md",))):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            wanted = next((m for m in allowed if name.lower() == m.lower() and name != m), None)
            if not wanted:
                continue
            twin = (" A `" + wanted + "` sits next to it: on Linux both exist and only `" + wanted
                    + "` is read, so the two copies can drift apart unseen.") if wanted in names else ""
            report.add("01-claude-md-case", "WARN",
                       f"`{name}` is not read by Claude Code on Linux (tested with 2.1.291), so not in Linux "
                       f"CI or containers either: only `{wanted}` is. Users report it is found on macOS "
                       f"and Windows; the documentation says nothing about case.{twin} "
                       + (f"Merge it into `{wanted}`." if twin else f"Rename it `{wanted}`."),
                       str(folder / name))


def agents_md_imported(root, files) -> bool:
    """Whether one of these memory files - or a file it imports - pulls in ./AGENTS.md.

    An import resolves "relative to the file containing the import", and "Import parsing
    skips Markdown code spans and fenced code blocks" (memory). A substring test for
    `@AGENTS.md` warned on `@./AGENTS.md` and on `@../AGENTS.md` from .claude/CLAUDE.md,
    and passed `@AGENTS.md` in .claude/CLAUDE.md, which points at .claude/AGENTS.md
    (audit externe 2026-10-08, P1-A--03 and P2-A--01).
    """
    target = os.path.realpath(root / "AGENTS.md")
    for f in files:
        if os.path.realpath(f) == target:
            return True                 # the memory file IS AGENTS.md, through a link
        if any(os.path.realpath(p) == target for p in expand_imports(f)):
            return True
    return False


def _import_spelling(root, path) -> str:
    """The `@` import of ./AGENTS.md as written from `path`'s folder."""
    rel = os.path.relpath(root / "AGENTS.md", path.parent).replace(os.sep, "/")
    return "@" + rel


def check_claude_md_size(ctx: AuditContext, report: Report, path) -> None:
    """01-claude-md-size and 01-claude-md-lines for one memory file."""
    root = ctx.root
    label = path.relative_to(root).as_posix()
    # errors="replace": a personal CLAUDE.local.md in Latin-1 stopped the whole check and
    # hid its other findings (audit externe 3, g4-00). Each undecodable byte then counts
    # 3 bytes (U+FFFD) instead of 1: the size is approximate for such a file only.
    raw = path.read_text(encoding="utf-8", errors="replace")
    size = len(injected_memory(raw).encode("utf-8"))
    # Measured on the same decoded text: against the on-disk size, each replaced byte took 2
    # bytes off the comment count, which went negative (external audit 4, cl-01).
    comments = len(raw.encode("utf-8")) - size
    if size > ctx.limits.CLAUDE_MD_MAX_BYTES:
        report.add(
            "01-claude-md-size",
            house(ctx),
            f"{label} is {size} bytes (max {ctx.limits.CLAUDE_MD_MAX_BYTES}). Move knowledge to skills."
            + house_note(f"at most {ctx.limits.CLAUDE_MD_MAX_BYTES} bytes",
                         "under 200 lines (memory) - checked by 01-claude-md-lines"),
            str(path),
        )
    else:
        report.add("01-claude-md-size", "OK", f"{label} size {size} bytes <= {ctx.limits.CLAUDE_MD_MAX_BYTES}"
                   + (f" ({comments} bytes of HTML comments not injected)." if comments else "."), str(path))
    injected = injected_memory(raw)
    lines = injected.count("\n") + (0 if injected.endswith("\n") or not injected else 1)
    if lines > ctx.limits.CLAUDE_MD_MAX_LINES:
        report.add("01-claude-md-lines", "WARN",
                   f"{label} is {lines} lines (> {ctx.limits.CLAUDE_MD_MAX_LINES}). \"Files over 200 lines "
                   "consume more context and may reduce adherence\" (memory).", str(path))


def check_claude_md(ctx: AuditContext, report: Report) -> None:
    root = ctx.root
    check_memory_file_case(root, report)
    # Every memory file that loads is measured, not the first one found: "target under
    # 200 lines per CLAUDE.md file" (memory; audit externe 2026-10-08, P2-A--06).
    for memory in project_memory_files(root):
        check_claude_md_size(ctx, report, memory)
    path = claude_md_path(root)
    if not path.exists():
        local = root / "CLAUDE.local.md"
        if (root / "AGENTS.md").is_file() and local.is_file() \
                and not agents_md_imported(root, [local]):
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
    text = path.read_text(encoding="utf-8")
    agents_md = root / "AGENTS.md"
    # One file linked to the other is read once, and read: "A CLAUDE.md symlinked to
    # AGENTS.md: nothing [to do]" (memory). Missed, it was 16 of 144 findings on 600
    # public repositories (2026-09-27). The committed files decide: CLAUDE.local.md is
    # personal, and an import there reads AGENTS.md for its owner only.
    committed = [p for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md") if p.is_file()]
    if agents_md.is_file() and not agents_md_imported(root, committed):
        spelling = _import_spelling(root, path)
        report.add("01-agents-md-unread", "WARN",
                   "AGENTS.md sits beside a CLAUDE.md that does not import it. By default "
                   "(`claude-md-or-agents-md`), Claude Code reads AGENTS.md only when no CLAUDE.md "
                   "exists - a CLAUDE.md that names it in words is not enough. Add "
                   f"`{spelling}` to {path.relative_to(root).as_posix()} (an import resolves from "
                   "the importing file), or "
                   "make one a symlink to the other; the user setting `claude-md-and-agents-md` "
                   "reads both, but only for whoever sets it (memory).",
                   str(agents_md))
    stripped = strip_code_fences(text, indented=True)
    # `/*` after a word is a glob (`lib/*.v`) or bold markdown (`**agent/**`), not a
    # comment: 9 of 12 findings on a public sample, 2026-09-27. A `/*` with no closing
    # `*/` is a root glob (` /*.env`), not a comment (audit externe 2026-10-08, P2-B--05).
    if re.search(r"^\s*//", stripped, re.MULTILINE) \
            or re.search(r"(?:^|\s)/\*(?!!)(?:(?!/\*).)*?(?<![*/])\*/", stripped, re.M | re.S):
        report.add(
            "12-no-code-comments",
            house(ctx),
            "CLAUDE.md contains // or /* */ outside code blocks."
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
        # Any name the harness accepts: it "can't contain `:`" and must not start with `-`
        # (sub-agents). `[a-z0-9-]+` read `shop_QA` as no entry at all (audit externe
        # 2026-10-08, P1-B--01). A `/` is kept out: a path in the table is not a name.
        # The cells of the column headed `Agent` only - the first column when no header
        # says so: the other cells hold a model (`sonnet`) or a tools list (`Read, Grep`,
        # the documented spelling), and reading them named agents that do not exist (audit
        # externe 3, g4-01). A table folded into two `Agent | Domain` pairs has two such
        # columns; the first cell alone left the second half unlisted (fusion, audit 3).
        # A GFM delimiter cell is one dash or more with optional colons, and the outer
        # pipes are optional: `|:--|` or `--- | ---` hid the `Agent` header, and only the
        # first column was read (external audit 4, cl-00).
        lines = block.splitlines()
        cols = [0]
        for i, line in enumerate(lines):
            if "|" not in line:
                cols = [0]
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if "|" in nxt and re.fullmatch(r"\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*", nxt):
                named = [j for j, c in enumerate(cells)
                         if re.fullmatch(r"[*_`]*(?:sub-?)?agents?(?: name)?[*_`]*", c, re.IGNORECASE)]
                cols = named or [0]
                continue
            for j in cols:
                m = re.fullmatch(r"`([^`:|\s/-][^`:|/]*?)`", cells[j]) if j < len(cells) else None
                if m:
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
                f"CLAUDE.md references agent '{ref}', but no agent has `name: {ref}` - an agent "
                "is known by its `name` field, not its filename (sub-agents)."
                + _same_stem(ctx, agents, ref),
                str(claude_md),
            )


def _same_stem(ctx: AuditContext, agents: dict[str, dict], ref: str) -> str:
    """When a file named after the missing agent exists, the name it actually carries."""
    from pathlib import Path
    for ident, data in agents.items():
        if Path(data.get("path", "")).stem == ref:
            return (f" {ctx.agents_dir}/{Path(data['path']).name} exists, but its `name` is "
                    f"'{ident}'.")
    return f" No file {ctx.agents_dir}/{ref}.md either."


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
                house(ctx),     # the index is a house convention (audit externe 2026-10-08, P1-B--05)
                f"CLAUDE.md 'Skills index' names '{ref}', but that skill is fully listed by the harness. "
                "Drop the entry: the index carries withheld skills only."
                + house_note("a 'Skills index' that names withheld skills only",
                             "nothing on a skills index - the listing already carries every "
                             "visible skill's description (skills)"),
                str(claude_md),
            )
