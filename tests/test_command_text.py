"""The command named in the documentation runs where it is read, held on the text of the files.

    python3 -m unittest tests.test_command_text

Since 0.36.0 there is no bare `deadweight` on the Bash tool's `PATH` (no `bin/`), and
`scripts/deadweight` has no `#!` line and no executable bit: it runs only as
`python3 <plugin root>/scripts/deadweight`. A relative `scripts/deadweight --semantic` in the skill
gave rc 127 from a project folder (audit of 0.36.0, B-00), and inside `SKILL.md` `scripts/` reads as
the skill's own folder, which has no `deadweight`.

- `SKILL.md` is run by Claude: every `scripts/deadweight` there is
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/deadweight"` (the variable is substituted in a skill's text),
  and no backticked command starts with a bare `deadweight`.
- The other documents (README, PRIVACY, references, evals) may also name the file in backticks, or
  give the command with a placeholder root (`<plugin root>/`, `<installPath>/`, the README's `$p/`).

Read from the files on disk, not from git, so it runs in any copy. `CHANGELOG.md` is history and
`evals/results/` holds model output: neither is held.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "config-auditor" / "SKILL.md"
PATH = re.compile(r"scripts/deadweight(?![\w-])")
IN_SKILL = 'python3 "${CLAUDE_PLUGIN_ROOT}/'
ELSEWHERE = (IN_SKILL, "python3 <plugin root>/", "python3 <installPath>/", 'python3 "$p/')
BARE = re.compile(r"`deadweight\s+-")


def misplaced(text: str, prefixes: tuple[str, ...], name_allowed: bool) -> list[str]:
    """Each `scripts/deadweight` not preceded by one of `prefixes`, as `line: excerpt`."""
    found = []
    for m in PATH.finditer(text):
        before = text[:m.start()]
        if any(before.endswith(p) for p in prefixes):
            continue
        if name_allowed and before.endswith("`") and text[m.end():m.end() + 1] == "`":
            continue                            # the file named, not a command
        line = text.count("\n", 0, m.start()) + 1
        found.append(f"{line}: {text[max(0, m.start() - 30):m.end() + 15]!r}")
    return found


def documents() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).parts
        if not p.is_file() or rel[0] in {".git", "tests"} or rel[:2] == ("evals", "results"):
            continue
        if p.name == "CHANGELOG.md" or p == SKILL:
            continue
        if p.suffix == ".md" or (rel[0] == "evals" and p.suffix in {".json", ".py", ".sh"}):
            out.append(p)
    return out


class CommandText(unittest.TestCase):
    def test_skill_names_the_command_with_python3_and_the_plugin_root(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertEqual(misplaced(text, (IN_SKILL,), name_allowed=False), [],
                         f'in SKILL.md write `{IN_SKILL}scripts/deadweight" <option>`')

    def test_skill_has_no_bare_deadweight_command(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        found = [f"{text.count(chr(10), 0, m.start()) + 1}: {text[m.start():m.start() + 40]!r}"
                 for m in BARE.finditer(text)]
        self.assertEqual(found, [], "no bare `deadweight` on the Bash tool's PATH since 0.36.0")

    def test_documents_name_the_file_or_a_runnable_command(self) -> None:
        found = []
        for p in documents():
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found += [f"{p.relative_to(ROOT).as_posix()}:{hit}"
                      for hit in misplaced(text, ELSEWHERE, name_allowed=True)]
        self.assertEqual(found, [], "a relative `scripts/deadweight <option>` runs nowhere: "
                                    "name the file in backticks or write `python3 <plugin root>/...`")

    def test_the_documents_are_found(self) -> None:
        names = {p.relative_to(ROOT).as_posix() for p in documents()}
        for expected in ("README.md", "PRIVACY.md", "evals/README.md"):
            self.assertIn(expected, names)
        self.assertTrue(SKILL.is_file())


if __name__ == "__main__":
    unittest.main()
