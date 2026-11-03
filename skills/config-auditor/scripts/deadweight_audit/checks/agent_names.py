"""44-plugin-agent-bare-name: a plugin asks for its own agent by the name Claude Code does not register."""
from __future__ import annotations

import json
import re

from ..context import AuditContext
from ..parsing.frontmatter import parse_frontmatter
from ..repo import readable_files
from ..report import Report

BUILTIN_AGENTS = frozenset({"general-purpose", "Explore", "Plan", "statusline-setup", "claude",
                            "claude-code-guide"})
# `subagent_type: x`, `subagent_type: "x"`, `"subagent_type": "x"`, `subagent_type=x`.
_ASK_RE = re.compile(r"""subagent_type["'`]?\s*[:=]\s*["'`]?([A-Za-z0-9_.:-]+)""")
TESTED = "2.1.317"


def check_plugin_agent_bare_name(ctx: AuditContext, report: Report) -> None:
    """Measured, Claude Code 2.1.309 (`--plugin-dir`, 2026-10-23): `subagent_type: "security-auditor"`
    answers "Agent type 'security-auditor' not found" and lists `<plugin>:security-auditor`.
    `claude --agent <bare>` is the documented exception and is not read here."""
    root = ctx.root
    try:
        manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8-sig"))
        plugin = manifest.get("name")
    except (OSError, ValueError, UnicodeDecodeError):
        return
    if not isinstance(plugin, str) or not plugin:
        return
    agents_dir = root / ctx.agents_dir
    expected: dict[str, str] = {}
    for p in readable_files(agents_dir.rglob("*.md")):
        try:
            fm, _ = parse_frontmatter(p.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            continue
        name = (fm or {}).get("name") or p.stem
        parts = list(p.relative_to(agents_dir).parent.parts)
        expected[name] = ":".join([plugin, *parts, name])
    if not expected:
        return
    files = []
    files += readable_files((root / "commands").rglob("*.md"))
    files += readable_files((root / ctx.skills_dir).glob("*/SKILL.md"))
    files += readable_files(agents_dir.rglob("*.md"))
    for p in files:
        try:
            text = p.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        seen: set[str] = set()
        for m in _ASK_RE.finditer(text):
            bare = m.group(1).rstrip(".:-")   # a sentence-ending period is not part of the name
            if ":" in bare or bare in BUILTIN_AGENTS or bare not in expected or bare in seen:
                continue
            seen.add(bare)
            report.add("44-plugin-agent-bare-name", "NOTICE",
                       f"'{p.relative_to(root)}' asks for subagent_type '{bare}', an agent this plugin "
                       f"ships: Claude Code {TESTED} registers it as '{expected[bare]}' and answers the "
                       f"bare name with \"Agent type '{bare}' not found\" when the tool is called as written; "
                       "in 9 of 9 command runs (Haiku and Sonnet) the model used the scoped name from its "
                       "first call, so a failed call is possible but was not seen there. "
                       "Write the scoped name (`claude --agent <name>` is the one place the bare name works).", str(p))
