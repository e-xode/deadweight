"""The audit reads a repository; it never runs the program the repository's `.git/config` names.

    python3 -m unittest discover -s tests

`core.fsmonitor` names a program git runs to list changed files. A clone does not carry it,
but a `.git/` folder received as files can: `git ls-files` ran the script on 0.27.0. Each of
the four git calls the auditor makes is exercised here against a witness script that would
leave a file behind. Fictional shop throughout.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402
from deadweight_audit.repo import (  # noqa: E402
    GIT_SAFE, git_ignores, git_tracked, rule_scope_files, tracked_paths,
)

PLUGIN = HERE.parent
# Every Python file the plugin runs on a user's machine. A new git call anywhere in them must
# pass `-c core.fsmonitor=false`; the behavioural tests above only exercise the four known ones
# (external audit of 0.28.0: a static guard, so a fifth call cannot slip in unseen).
SHIPPED = sorted([*(PLUGIN / "skills" / "config-auditor" / "scripts").rglob("*.py"),
                  *(PLUGIN / "skills" / "config-auditor" / "templates").glob("*.py"),
                  *(PLUGIN / "skills" / "config-auditor" / "probes").rglob("*.py"),
                  *(PLUGIN / "hooks").glob("*.py"), PLUGIN / "bin" / "deadweight"])
# Exempt git subcommands, with the reason. `init` creates a new repository in a fresh temporary
# folder (probes/run_probes.py): there is no configuration of anyone's to obey yet.
EXEMPT_SUBCOMMANDS = {"init"}


def unguarded_git_calls(source: str) -> list[int]:
    """Lines of `subprocess.*(["git", ...])` calls whose list lacks the override before the subcommand.

    Git reads `-c core.fsmonitor=false` as a global option only before the subcommand; after
    it the same words are arguments of the subcommand (git 2.53.0 reads `-c` after `ls-files` as
    `--cached`), so the override must come first (catch-up audit of 0.28.0, E-00). Only a call
    written as a literal list is seen: a list built in pieces or a string run through a shell is not.
    """
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and node.args
                and isinstance(node.args[0], (ast.List, ast.Tuple)) and node.args[0].elts):
            continue
        elts = node.args[0].elts
        if not (isinstance(elts[0], ast.Constant) and elts[0].value == "git"):
            continue
        seen, skip, i = False, False, 1
        while i < len(elts):
            e = elts[i]
            i += 1
            if skip:
                skip = False
                continue
            if isinstance(e, ast.Starred):
                seen = seen or (isinstance(e.value, ast.Name) and e.value.id == "GIT_SAFE")
                continue
            if not isinstance(e, ast.Constant) or not isinstance(e.value, str):
                continue
            if e.value == "-c" and i < len(elts) and isinstance(elts[i], ast.Constant) \
                    and elts[i].value == "core.fsmonitor=false":
                seen, skip = True, True
            elif e.value in ("-c", "-C"):
                skip = True
            elif e.value.startswith("-"):
                continue
            else:
                # The first plain word is the subcommand: the override had to come before it.
                if not seen and e.value not in EXEMPT_SUBCOMMANDS:
                    bad.append(node.lineno)
                break
    return bad


@unittest.skipUnless(shutil.which("git") and os.name == "posix", "needs git and a POSIX shell")
class FsmonitorNotRun(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "shop-api"
        self.witness = base / "fsmonitor-ran"
        (self.root / ".claude").mkdir(parents=True)
        (self.root / "CLAUDE.md").write_text("# shop-api\n\nRun `make test`.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "add", "CLAUDE.md"], check=True,
                       capture_output=True)
        hook = base / "shop-fsmonitor.sh"
        hook.write_text(f"#!/bin/sh\ntouch '{self.witness}'\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        subprocess.run(["git", "-C", str(self.root), "config", "core.fsmonitor", str(hook)],
                       check=True, capture_output=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def assert_not_run(self) -> None:
        self.assertFalse(self.witness.exists(), "the repository's core.fsmonitor program ran")

    def test_witness_runs_without_the_override(self):
        # The negative control: the setup does make git run the program.
        subprocess.run(["git", "-C", str(self.root), "ls-files"], capture_output=True)
        self.assertTrue(self.witness.exists())

    def test_tracked_paths(self):
        tracked_paths(self.root)
        self.assert_not_run()

    def test_rule_scope_files(self):
        rule_scope_files(self.root)
        self.assert_not_run()

    def test_git_tracked(self):
        self.assertEqual(git_tracked(self.root, "CLAUDE.md"), "tracked")
        self.assert_not_run()

    def test_git_ignores(self):
        git_ignores(self.root, ".claude/settings.local.json")
        self.assert_not_run()

    def test_whole_audit(self):
        with contextlib.redirect_stdout(io.StringIO()):
            main(["--root", str(self.root), "--json", "--all"])
        self.assert_not_run()


class EveryGitCallIsGuarded(unittest.TestCase):
    def test_git_safe_is_the_override(self):
        self.assertEqual(GIT_SAFE, ("-c", "core.fsmonitor=false"))

    def test_the_walker_sees_a_bare_call(self):
        # The negative control: without it, a walker that matches nothing passes every file.
        src = ("import subprocess\n"
               "subprocess.run(['git', '-C', 'shop-api', 'ls-files'])\n"
               "subprocess.run(['git', '-C', 'shop-api', *GIT_SAFE, 'ls-files'])\n"
               "subprocess.run(['git', '-c', 'core.fsmonitor=false', 'status'])\n"
               "subprocess.run(['git', 'init', '-q', 'shop-new'])\n"
               "subprocess.run(['git', '-C', 'shop-api', 'ls-files', '-c', 'core.fsmonitor=false'])\n"
               "subprocess.run(['git', 'ls-files', *GIT_SAFE])\n")
        # Lines 2, 5 and 6: no override, and the override placed after the subcommand.
        self.assertEqual(unguarded_git_calls(src), [2, 6, 7])

    def test_the_walker_finds_the_four_audit_calls(self):
        repo = PLUGIN / "skills" / "config-auditor" / "scripts" / "deadweight_audit" / "repo.py"
        src = repo.read_text(encoding="utf-8")
        mutated = src.replace("*GIT_SAFE, ", "")
        self.assertEqual(len(unguarded_git_calls(mutated)), 4)

    def test_no_shipped_git_call_lacks_the_override(self):
        self.assertIn(PLUGIN / "bin" / "deadweight", SHIPPED)
        self.assertTrue(any(f.name == "session-audit.py" for f in SHIPPED))
        found = {str(f.relative_to(PLUGIN)): unguarded_git_calls(f.read_text(encoding="utf-8"))
                 for f in SHIPPED}
        self.assertEqual({f: lines for f, lines in found.items() if lines}, {})


if __name__ == "__main__":
    unittest.main()
