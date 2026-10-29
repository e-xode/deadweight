"""`deadweight --setup-statusline` writes its launcher only once the settings line is set.

    python3 -m unittest discover -s tests

Until 0.27.0 the launcher was written first, then `wire` ran: a settings file that already had
another `statusLine` was left alone, but a file already at the launcher's path had been
replaced. The 0.28.0 candidate wrote it after `wire` and crashed there when the launcher's path
was a folder, a dangling link or a read-only file, with the `statusLine` already set (external
audit of 0.28.0, C-00): the settings file must then be put back as it was. Fictional shop
throughout.
"""
from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MINE = "#!/usr/bin/env python3\nprint('shop-api status')\n"


def command():
    """bin/deadweight has no .py suffix: load it by path."""
    loader = importlib.machinery.SourceFileLoader("deadweight_bin", str(ROOT / "bin" / "deadweight"))
    spec = importlib.util.spec_from_loader("deadweight_bin", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class LauncherAfterWire(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = command()
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def quiet(self, fn, *args):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    def project(self, settings: str) -> Path:
        root = self.base / "shop-api"
        (root / ".claude").mkdir(parents=True)
        (root / ".claude" / "settings.json").write_text(settings, encoding="utf-8")
        (root / ".claude" / "statusline.py").write_text(MINE, encoding="utf-8")
        return root

    def test_claude_other_status_line_keeps_the_file(self):
        root = self.project(json.dumps({"statusLine": {"type": "command", "command": "shop-status"}}))
        self.assertEqual(self.quiet(self.mod.setup_claude, root), 1)
        self.assertEqual((root / ".claude" / "statusline.py").read_text(encoding="utf-8"), MINE)

    def test_claude_unreadable_settings_keeps_the_file(self):
        root = self.project('{ // shop-api\n "statusLine": {} }\n')
        self.assertEqual(self.quiet(self.mod.setup_claude, root), 2)
        self.assertEqual((root / ".claude" / "statusline.py").read_text(encoding="utf-8"), MINE)

    def test_claude_success_writes_the_launcher(self):
        # The control: when the line is set, the launcher is (re)written.
        root = self.project("{}\n")
        self.assertEqual(self.quiet(self.mod.setup_claude, root), 0)
        self.assertEqual((root / ".claude" / "statusline.py").read_text(encoding="utf-8"),
                         self.mod.LAUNCHER.read_text(encoding="utf-8"))

    def test_copilot_other_status_line_keeps_the_file(self):
        home = self.base / "copilot"
        home.mkdir()
        (home / "settings.json").write_text(json.dumps({"statusLine": {"type": "command",
                                                                       "command": "shop-status"}}),
                                            encoding="utf-8")
        (home / "deadweight-statusline.py").write_text(MINE, encoding="utf-8")
        with mock.patch.dict(os.environ, {"COPILOT_HOME": str(home)}):
            self.assertEqual(self.quiet(self.mod.setup_copilot), 1)
        self.assertEqual((home / "deadweight-statusline.py").read_text(encoding="utf-8"), MINE)


    def test_copilot_success_writes_the_launcher(self):
        # C-01: no test held the Copilot success path; removing its launcher write passed them all.
        home = self.base / "copilot"
        home.mkdir()
        (home / "settings.json").write_text("{}\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"COPILOT_HOME": str(home)}):
            self.assertEqual(self.quiet(self.mod.setup_copilot), 0)
        self.assertEqual((home / "deadweight-statusline.py").read_text(encoding="utf-8"),
                         self.mod.LAUNCHER.read_text(encoding="utf-8"))
        self.assertIn("deadweight-statusline.py",
                      json.loads((home / "settings.json").read_text(encoding="utf-8"))["statusLine"]["command"])

    def bare_project(self, settings: str | None) -> Path:
        root = self.base / "shop-web"
        (root / ".claude").mkdir(parents=True)
        if settings is not None:
            (root / ".claude" / "settings.json").write_text(settings, encoding="utf-8")
        return root

    def assert_failed_cleanly(self, fn, *args) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(fn(*args), 3)
        self.assertIn("could not be written", err.getvalue())
        self.assertIn("left as they were", err.getvalue())

    def test_claude_launcher_path_is_a_folder(self):
        settings = '{\n  "model": "sonnet"\n}\n'
        root = self.bare_project(settings)
        (root / ".claude" / "statusline.py").mkdir()
        self.assert_failed_cleanly(self.mod.setup_claude, root)
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), settings)
        self.assertTrue((root / ".claude" / "statusline.py").is_dir())

    def test_claude_launcher_path_is_a_folder_no_settings_before(self):
        root = self.bare_project(None)
        (root / ".claude" / "statusline.py").mkdir()
        self.assert_failed_cleanly(self.mod.setup_claude, root)
        self.assertFalse((root / ".claude" / "settings.json").exists())

    @unittest.skipUnless(os.name == "posix", "symbolic links need privileges on Windows")
    def test_claude_launcher_path_is_a_dangling_link(self):
        root = self.bare_project("{}\n")
        target = self.base / "elsewhere" / "shop-status.py"
        (self.base / "elsewhere").mkdir()
        os.symlink(target, root / ".claude" / "statusline.py")
        self.assert_failed_cleanly(self.mod.setup_claude, root)
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{}\n")
        self.assertFalse(target.exists(), "the launcher was written through the link")

    @unittest.skipUnless(os.name == "posix", "symbolic links need privileges on Windows")
    def test_claude_settings_is_a_dangling_link(self):
        root = self.bare_project(None)
        target = self.base / "dotfiles" / "settings.json"
        (self.base / "dotfiles").mkdir()
        link = root / ".claude" / "settings.json"
        os.symlink(target, link)
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.mod.setup_claude(root), 2)
        self.assertTrue(link.is_symlink(), "the user's link was deleted")
        self.assertFalse(target.exists(), "the settings were written through the link")

    @unittest.skipUnless(os.name == "posix", "symbolic links need privileges on Windows")
    def test_claude_settings_is_a_dangling_link_and_the_launcher_fails(self):
        root = self.bare_project(None)
        target = self.base / "dotfiles" / "settings.json"
        (self.base / "dotfiles").mkdir()
        link = root / ".claude" / "settings.json"
        os.symlink(target, link)
        (root / ".claude" / "statusline.py").mkdir()
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(self.mod.setup_claude(root), 0)
        self.assertTrue(link.is_symlink(), "the user's link was deleted")
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == "posix", "symbolic links need privileges on Windows")
    def test_claude_settings_is_a_link_to_a_file_and_the_launcher_fails(self):
        root = self.bare_project(None)
        target = self.base / "dotfiles" / "settings.json"
        (self.base / "dotfiles").mkdir()
        target.write_text('{\n  "model": "sonnet"\n}\n', encoding="utf-8")
        link = root / ".claude" / "settings.json"
        os.symlink(target, link)
        (root / ".claude" / "statusline.py").mkdir()
        self.assert_failed_cleanly(self.mod.setup_claude, root)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), '{\n  "model": "sonnet"\n}\n')

    @unittest.skipUnless(os.name == "posix", "file modes are POSIX")
    def test_claude_launcher_is_executable_and_replaces_atomically(self):
        root = self.project("{}\n")
        launcher = root / ".claude" / "statusline.py"
        launcher.chmod(0o644)
        self.assertEqual(self.quiet(self.mod.setup_claude, root), 0)
        self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o755)
        self.assertNotEqual(launcher.read_text(encoding="utf-8"), MINE)
        self.assertEqual([p.name for p in (root / ".claude").iterdir() if p.name.startswith(".statusline-")], [],
                         "a temporary file was left behind")

    @unittest.skipUnless(os.name == "posix", "file modes are POSIX")
    def test_a_failing_chmod_leaves_the_old_launcher(self):
        root = self.project("{}\n")
        launcher = root / ".claude" / "statusline.py"
        with mock.patch.object(self.mod.os, "chmod", side_effect=PermissionError("denied")):
            self.assert_failed_cleanly(self.mod.setup_claude, root)
        self.assertEqual(launcher.read_text(encoding="utf-8"), MINE, "the old launcher was replaced")
        self.assertEqual([p.name for p in (root / ".claude").iterdir() if p.name.startswith(".statusline-")], [])
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{}\n")

    def test_a_write_that_fails_after_opening_puts_the_bytes_back(self):
        # A full disk: the file was opened and truncated, then the write raised (0.29.0 audit, E-00).
        settings_text = '{\n  "model": "sonnet"\n}\n'
        root = self.project(settings_text)
        real = Path.write_text

        def failing(self_path, data, *a, **k):
            if self_path.name == "settings.json":
                real(self_path, "", encoding="utf-8")        # what open(..., "w") already did
                raise OSError(28, "No space left on device")
            return real(self_path, data, *a, **k)

        err = io.StringIO()
        with mock.patch.object(Path, "write_text", failing), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.mod.setup_claude(root), 2)
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), settings_text)
        self.assertIn("left as they were", err.getvalue())

    def test_an_interruption_during_the_settings_write_puts_the_bytes_back(self):
        # Ctrl-C after the file was opened and truncated (0.29.0 re-audit, E-01).
        settings_text = '{\n  "model": "sonnet"\n}\n'
        root = self.project(settings_text)
        real = Path.write_text

        def interrupted(self_path, data, *a, **k):
            if self_path.name == "settings.json":
                real(self_path, "", encoding="utf-8")
                raise KeyboardInterrupt
            return real(self_path, data, *a, **k)

        with mock.patch.object(Path, "write_text", interrupted), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                self.mod.setup_claude(root)
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), settings_text)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "read-only needs POSIX permissions and a user other than root")
    def test_a_read_only_settings_file_is_not_reported_as_damaged(self):
        # Nothing was written, so nothing needs putting back: the message must not say "check its content"
        # (0.29.0 re-audit, C-01).
        root = self.project("{}\n")
        settings = root / ".claude" / "settings.json"
        settings.chmod(stat.S_IRUSR)
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.mod.setup_claude(root), 2)
        finally:
            settings.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.assertNotIn("could not be put back", err.getvalue())
        self.assertIn("left as they were", err.getvalue())

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "read-only needs POSIX permissions and a user other than root")
    def test_a_failure_in_the_in_place_branch_puts_the_old_launcher_back(self):
        # A read-only folder over a writable launcher, and the chmod fails after the write (0.29.0 re-audit, E-00).
        root = self.project("{}\n")
        folder = root / ".claude"
        real = Path.chmod

        def failing(self_path, mode, *a, **k):
            if self_path.name == "statusline.py":
                raise PermissionError("denied")
            return real(self_path, mode, *a, **k)

        folder.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            with mock.patch.object(Path, "chmod", failing):
                self.assertEqual(self.quiet(self.mod.setup_claude, root), 3)
        finally:
            folder.chmod(stat.S_IRWXU)
        self.assertEqual((folder / "statusline.py").read_text(encoding="utf-8"), MINE)
        self.assertEqual((folder / "settings.json").read_text(encoding="utf-8"), "{}\n")

    def test_a_failing_replace_leaves_the_old_launcher(self):
        # A launcher written in place instead of beside and moved never calls os.replace (E-02).
        root = self.project("{}\n")
        launcher = root / ".claude" / "statusline.py"
        with mock.patch.object(self.mod.os, "replace", side_effect=OSError("denied")):
            self.assert_failed_cleanly(self.mod.setup_claude, root)
        self.assertEqual(launcher.read_text(encoding="utf-8"), MINE)
        self.assertEqual([p.name for p in (root / ".claude").iterdir() if p.name.startswith(".statusline-")], [])

    def test_an_interruption_puts_the_settings_back(self):
        # Ctrl-C while the launcher is written: the settings do not keep a line that runs nothing (E-03).
        root = self.project("{}\n")
        with mock.patch.object(self.mod.os, "replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt), \
                    contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.mod.setup_claude(root)
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{}\n")
        self.assertEqual((root / ".claude" / "statusline.py").read_text(encoding="utf-8"), MINE)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "read-only needs POSIX permissions and a user other than root")
    def test_a_read_only_folder_over_writable_files_is_written_in_place(self):
        # Before 0.29.0 this gave 0; the temporary file made it 3 (0.29.0 audit, E-01).
        root = self.project("{}\n")
        folder = root / ".claude"
        folder.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            self.assertEqual(self.quiet(self.mod.setup_claude, root), 0)
        finally:
            folder.chmod(stat.S_IRWXU)
        self.assertNotEqual((folder / "statusline.py").read_text(encoding="utf-8"), MINE)
        self.assertEqual(stat.S_IMODE((folder / "statusline.py").stat().st_mode), 0o755)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "read-only needs POSIX permissions and a user other than root")
    def test_claude_settings_is_read_only(self):
        root = self.project("{}\n")
        settings = root / ".claude" / "settings.json"
        settings.chmod(stat.S_IRUSR)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.mod.setup_claude(root), 2)
        finally:
            settings.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.assertIn("could not be written", err.getvalue())
        self.assertEqual((root / ".claude" / "statusline.py").read_text(encoding="utf-8"), MINE)

    def test_claude_dotclaude_is_a_file(self):
        root = self.base / "shop-web"
        root.mkdir()
        (root / ".git").mkdir()
        (root / ".claude").write_text("not a folder", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.mod.setup_claude(root), 2)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
                         "read-only needs POSIX permissions and a user other than root")
    def test_claude_launcher_path_is_read_only(self):
        root = self.project("{}\n")
        launcher = root / ".claude" / "statusline.py"
        launcher.chmod(stat.S_IRUSR)
        try:
            self.assert_failed_cleanly(self.mod.setup_claude, root)
        finally:
            launcher.chmod(stat.S_IRUSR | stat.S_IWUSR)
        self.assertEqual(launcher.read_text(encoding="utf-8"), MINE)
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{}\n")

    def test_copilot_launcher_path_is_a_folder(self):
        home = self.base / "copilot"
        home.mkdir()
        (home / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
        (home / "deadweight-statusline.py").mkdir()
        with mock.patch.dict(os.environ, {"COPILOT_HOME": str(home)}):
            self.assert_failed_cleanly(self.mod.setup_copilot)
        self.assertEqual((home / "settings.json").read_text(encoding="utf-8"), '{"theme": "dark"}')

    def test_a_failed_claude_launcher_does_not_skip_copilot(self):
        # The crash also skipped the Copilot setup (both copies, external audit of 0.28.0).
        root = self.bare_project("{}\n")
        (root / ".claude" / "statusline.py").mkdir()
        claude_home, home = self.base / "claude-home", self.base / "copilot"
        claude_home.mkdir()
        home.mkdir()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(claude_home), "COPILOT_HOME": str(home)}):
            self.assertEqual(self.quiet(self.mod.setup_statusline, root), 3)
        self.assertTrue((home / "deadweight-statusline.py").is_file())
        self.assertEqual((root / ".claude" / "settings.json").read_text(encoding="utf-8"), "{}\n")


if __name__ == "__main__":
    unittest.main()
