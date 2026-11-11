"""Regex graders of the evals accept the right diagnosis and reject the wrong one.

    python3 -m unittest discover -s tests

A regex grader is applied by the eval runner, not by the auditor: nothing else checks what it
lets through. Before 0.35.0, `silent-memory/graders/agents-md-unread.md` was widened with bare
words (`never`, `doesn't`, `does not`, `symlink`) anywhere within 300 characters of `AGENTS.md`;
it then passed answers that say the file IS read, and an answer that only quotes the fixture's
own AGENTS.md ("Never edit files under src/generated/"). The negation is now bound to the verb.
These witnesses keep it there.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

EVALS = Path(__file__).resolve().parent.parent / "evals"


def regex_grader(path: Path) -> re.Pattern:
    """The `pattern` and `flags` of a regex grader's frontmatter (JSON-compatible double quotes)."""
    head = path.read_text(encoding="utf-8").split("---")[1]
    fields = {}
    for line in head.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    assert fields.get("type") == "regex", path
    flags = 0
    for ch in json.loads(fields.get("flags", '""')):
        flags |= {"i": re.I, "s": re.S, "m": re.M}[ch]
    return re.compile(json.loads(fields["pattern"]), flags)


class AgentsMdUnread(unittest.TestCase):
    pattern = regex_grader(EVALS / "silent-memory" / "graders" / "agents-md-unread.md")

    RIGHT = [
        "Claude Code doesn't read AGENTS.md; add @AGENTS.md to CLAUDE.md.",
        "Your AGENTS.md isn't loaded by Claude Code at all. Move its rules into CLAUDE.md.",
        "AGENTS.md is skipped: Claude Code only loads CLAUDE.md.",
        "AGENTS.md is never loaded by Claude Code: it reads CLAUDE.md only.",
        "The AGENTS.md file is not read by Claude Code, so its rules never reach the model.",
        "AGENTS.md: Claude Code does not read this file. Point CLAUDE.md at it.",
        "AGENTS.md - Claude Code never reads it; only CLAUDE.md is loaded.",
        "AGENTS.md is not being loaded. Claude Code looks for CLAUDE.md.",
        "AGENTS.md isn’t read by Claude Code.",
    ]

    # Each was accepted by the widened pattern and rejected by the 0.34.0 one.
    WRONG = [
        "AGENTS.md is always read by Claude Code, it never needs to be referenced. The problem is the globs rule.",
        "AGENTS.md doesn't need a symlink, Claude reads it natively alongside CLAUDE.md.",
        "AGENTS.md is loaded fine. Its rule says Never edit files under src/generated/, which is respected.",
        "AGENTS.md:\n# Agent instructions\n\nAlways run `npm run lint` before committing. "
        "Never edit files under src/generated/.",
        "AGENTS.md looks good and does not need changes; the issue is .claude/rules/admin.md using globs.",
        "AGENTS.md is picked up. The memory isn't the problem: `globs` isn't a field of a rule.",
    ]

    def test_right_diagnosis_matches(self):
        for answer in self.RIGHT:
            with self.subTest(answer=answer):
                self.assertTrue(self.pattern.search(answer))

    def test_wrong_answer_does_not_match(self):
        for answer in self.WRONG:
            with self.subTest(answer=answer):
                self.assertIsNone(self.pattern.search(answer))


if __name__ == "__main__":
    unittest.main()
