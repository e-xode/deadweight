"""Check 22 tests a rule's glob against the disk AND git's list - where the corpus cannot reach.

    python3 -m unittest discover -s tests

The corpus writes UTF-8 names at the root of one fresh `git init`, with no commit. These
situations need a Latin-1 file name, a submodule, a nested repository, an enclosing
repository that ignores the audited folder, and a user's global excludes file. Testing the
glob against `git ls-files` alone reported each of them as a rule that never loads, or
crashed the check (external audit of 0.24.0: ag-00, ag-02, ag-03, se-01, te-01). A path rule
loads when Claude reads a matching file (memory), whether git tracks it or not.
Fictional shop throughout.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))

from deadweight_audit.cli import main  # noqa: E402

CLAUDE_MD = "# shop-api\n\nRun `make test` before any change.\n"


def run(root: Path) -> list[dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main(["--root", str(root), "--json", "--all"])
    return json.loads(out.getvalue())["findings"]


def of(findings: list[dict], *checks: str) -> list[str]:
    return [f"{f['check']} {f['message']}" for f in findings if f["check"] in checks]


def git(where: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(where), "-c", "user.email=shop@example.invalid",
                    "-c", "user.name=shop", "-c", "protocol.file.allow=always", *args],
                   check=True, capture_output=True)


def project(root: Path, glob: str) -> None:
    (root / ".claude" / "rules").mkdir(parents=True)
    (root / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")
    (root / ".claude" / "rules" / "scope.md").write_text(
        f"---\npaths:\n  - \"{glob}\"\n---\nKeep it typed.\n", encoding="utf-8")


@unittest.skipUnless(shutil.which("git"), "needs git")
class RuleScopeOnDisk(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "shop-api"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "needs a file system that stores raw bytes")
    def test_latin1_file_name_does_not_crash_the_check(self) -> None:
        # ag-00: `ls-files` decoded strictly raised UnicodeDecodeError, and the true dead glob
        # below was lost under a 00-check-crashed.
        project(self.root, "deploy/**")
        (self.root / "docs").mkdir()
        with open(os.path.join(os.fsencode(self.root), b"docs", b"caf\xe9.md"), "wb") as f:
            f.write(b"menu\n")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "shop")
        found = run(self.root)
        self.assertEqual(of(found, "00-check-crashed"), [])
        self.assertEqual(len(of(found, "22-rule-glob-match")), 1, of(found, "22-rule-glob-match"))

    def test_checked_out_submodule_files_match(self) -> None:
        # ag-02, se-01: git lists a submodule as one gitlink entry.
        lib = self.base / "shop-theme"
        lib.mkdir()
        (lib / "theme.scss").write_text("a { color: red; }\n", encoding="utf-8")
        git(lib, "init", "-q")
        git(lib, "add", "-A")
        git(lib, "commit", "-qm", "theme")
        project(self.root, "vendor/shop-theme/**/*.scss")
        git(self.root, "init", "-q")
        git(self.root, "submodule", "add", "-q", str(lib), "vendor/shop-theme")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "shop")
        self.assertEqual(of(run(self.root), "22-rule-glob-match", "00-check-crashed"), [])

    def test_nested_repository_files_match(self) -> None:
        # te-01: an independently cloned service shows up as one `services/api/` entry.
        project(self.root, "services/api/**/*.go")
        api = self.root / "services" / "api"
        api.mkdir(parents=True)
        (api / "handler.go").write_text("package api\n", encoding="utf-8")
        git(api, "init", "-q")
        git(self.root, "init", "-q")
        self.assertEqual(of(run(self.root), "22-rule-glob-match", "00-check-crashed"), [])

    def test_folder_ignored_by_the_enclosing_repository(self) -> None:
        # se-01: `ls-files` succeeds with an empty list when the audited folder is ignored above.
        git(self.base, "init", "-q")
        (self.base / ".gitignore").write_text("shop-api/\n", encoding="utf-8")
        project(self.root, "src/**/*.ts")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.ts").write_text("export {};\n", encoding="utf-8")
        self.assertEqual(of(run(self.root), "22-rule-glob-match", "00-check-crashed"), [])

    def test_tracked_file_under_a_walk_pruned_folder_matches(self) -> None:
        # te-00 (external audit of 0.24.0, 2nd pass): the walk prunes every folder named
        # `build`, so only git's list can supply this match. Without it the rule is reported
        # as matching nothing - as 0.23.0 did.
        project(self.root, "docker/build/**/*.conf")
        (self.root / "docker" / "build").mkdir(parents=True)
        (self.root / "docker" / "build" / "shop.conf").write_text("server { listen 80; }\n",
                                                                   encoding="utf-8")
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "shop")
        self.assertEqual(of(run(self.root), "22-rule-glob-match", "00-check-crashed"), [])

    def test_global_excludes_file_does_not_change_the_verdict(self) -> None:
        # ag-03: the same commit warned on the machine whose personal ignore file held '*.yml'.
        # te-01: under a walk-pruned folder (`build`), so the disk walk cannot supply the match
        # and only git's list - read with the repository's own ignore rules - decides.
        project(self.root, "docker/build/**/*.yml")
        (self.root / "docker" / "build").mkdir(parents=True)
        (self.root / "docker" / "build" / "prod.yml").write_text("replicas: 2\n", encoding="utf-8")
        git(self.root, "init", "-q")
        ignore = self.base / "global-ignore"
        ignore.write_text("*.yml\n", encoding="utf-8")
        config = self.base / "global-config"
        config.write_text(f"[core]\n\texcludesFile = {ignore.as_posix()}\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)}):
            found = run(self.root)
        self.assertEqual(of(found, "22-rule-glob-match", "00-check-crashed"), [])

if __name__ == "__main__":
    unittest.main()
