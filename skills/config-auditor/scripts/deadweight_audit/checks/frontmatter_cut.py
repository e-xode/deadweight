"""02-frontmatter-early-close: a `---` inside a frontmatter value closes the frontmatter."""
from __future__ import annotations

import re

from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_cut
from ..report import Report
from ..repo import readable_files

# Measured on 2.1.309 (2026-10-23: skills, agents, rules, commands) and again on 2.1.317 (2026-11-03:
# skills, an agent, a hook command, a YAML comment line `# a---b`), Linux, `claude -p`.
TESTED = "2.1.317"


def _targets(ctx: AuditContext):
    root = ctx.root
    out = []
    out += [(p, "skill") for p in readable_files((root / ctx.skills_dir).glob("*/SKILL.md"))]
    out += [(p, "agent") for p in readable_files((root / ctx.agents_dir).rglob("*.md"))]
    out += [(p, "rule") for p in readable_files((root / ctx.claude_dir / "rules").rglob("*.md"))]
    out += [(p, "command") for p in readable_files((root / ctx.claude_dir / "commands").rglob("*.md"))]
    return out


def check_frontmatter_early_close(ctx: AuditContext, report: Report) -> None:
    """One WARN per file whose frontmatter holds `---` before its closing line."""
    for p, kind in _targets(ctx):
        try:
            text = p.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        cut = frontmatter_cut(text)
        if cut is None:
            continue
        rel = str(p.relative_to(ctx.root))
        key = cut["key"] or "a field"
        if cut["comment"]:
            what = f"a comment line in the frontmatter of '{rel}' ({kind})"
        else:
            what = f"'{key}' in the frontmatter of '{rel}' ({kind})"
        if cut["error"] and kind == "agent":
            effect = ("what remains no longer parses, and the agent is not listed at all "
                      "(measured, 2 runs, 2.1.317)")
        elif cut["error"]:
            effect = ("what remains no longer parses: a skill then loads with empty metadata "
                      "(documented, and measured), and a rule's `paths` or a hook would be lost the "
                      "same way (expected, not measured)")
        elif cut["comment"]:
            effect = (f"the text after the dashes ('{cut['read'] or 'the rest of the line'}') is read "
                      "as the end of the frontmatter" + (f"; {', '.join(cut['lost'])} "
                      "are never read" if cut["lost"] else ""))
        elif key == "hooks" and re.match(r"\s*(?:-\s*)?command\s*:", cut["kept_line"]):
            effect = f"a hook command is cut and runs as '{cut['kept_line']}'"
        elif key == "hooks":
            effect = f"a hook field is cut at '{cut['kept_line']}'"
        else:
            lost = f" and {', '.join(cut['lost'])} are never read" if cut["lost"] else ""
            effect = f"it reads '{key}' as '{cut['read']}'{lost}"
        report.add("02-frontmatter-early-close", "WARN",
                   f"{what} holds '---' on line {cut['line']}: "
                   f"Claude Code {TESTED} closes the frontmatter at the first '---' it meets, even "
                   f"inside a value or quotes; {effect}. Write the value without three dashes "
                   "in a row (an em dash, or '- -').", str(p))
