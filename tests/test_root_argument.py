"""What `--root` accepts: an existing directory, outside the user configuration directory.

    python3 -m unittest discover -s tests

A missing root or a file raised a traceback; a root in ~/.claude (or CLAUDE_CONFIG_DIR) was
audited as a project, said "nothing to audit" beside a settings.json, and advised that a user
skill "loads nowhere" (user report on 0.23.0, 2026-10-09). A fake home throughout:
HOME and USERPROFILE (Windows), CLAUDE_CONFIG_DIR removed or set. Fictional shop.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AUDIT = Path(__file__).resolve().parent.parent / "skills" / "config-auditor" / "scripts" / "audit.py"
SKILL = ("---\nname: shop-refunds\ndescription: Handle shop refunds for customers. "
         "Do not use for invoices.\n---\n\nCheck the refund window first.\n")


def audit(root: Path, home: Path, config_dir: Path | None = None,
          extra: tuple = ()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
    env.update(HOME=str(home), USERPROFILE=str(home))
    if config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return subprocess.run([sys.executable, str(AUDIT), "--root", str(root), "--json", *extra],
                          capture_output=True, text=True, env=env)


class RootArgument(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.user = self.home / ".claude"
        (self.user / "skills" / "shop-refunds").mkdir(parents=True)
        (self.user / "agents").mkdir()
        (self.user / "skills" / "shop-refunds" / "SKILL.md").write_text(SKILL, encoding="utf-8")
        (self.user / "settings.json").write_text('{"permissions": {"defaultMode": "plan"}}\n',
                                                 encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_root_is_one_line_and_non_zero(self) -> None:
        r = audit(self.home / "no-such-project", self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("does not exist", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)

    def test_file_root_is_one_line_and_non_zero(self) -> None:
        r = audit(self.user / "settings.json", self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("is not a directory", r.stderr)

    def _user_scope(self, r: subprocess.CompletedProcess) -> None:
        findings = json.loads(r.stdout)["findings"]
        self.assertEqual([f["check"] for f in findings], ["00-layout"], findings)
        self.assertIn("user configuration directory", findings[0]["message"])

    def test_user_configuration_directory_and_below_are_not_audited(self) -> None:
        for root in (self.user, self.user / "agents", self.user / "skills"):
            with self.subTest(root=root.name):
                self._user_scope(audit(root, self.home))

    def test_claude_config_dir_is_the_user_directory(self) -> None:
        alt = self.home / "claude-config"
        (alt / "skills" / "shop-refunds").mkdir(parents=True)
        (alt / "skills" / "shop-refunds" / "SKILL.md").write_text(SKILL, encoding="utf-8")
        self._user_scope(audit(alt / "skills", self.home, config_dir=alt))

    def test_explicit_layout_is_honoured_in_the_user_directory(self) -> None:
        # cl-00: `--layout library` on ~/.claude/skills was overridden to `none`, and a
        # description cut by the listing (> 1,536 characters) went unreported.
        long_desc = "Handle shop refunds for customers. " * 50 + "Do not use for invoices."
        (self.user / "skills" / "shop-refunds" / "SKILL.md").write_text(
            f"---\nname: shop-refunds\ndescription: {long_desc}\n---\n\nCheck the window.\n",
            encoding="utf-8")
        r = audit(self.user / "skills", self.home, extra=("--layout", "library"))
        out = json.loads(r.stdout)
        self.assertEqual(out["layout"], "library")
        checks = [f["check"] for f in out["findings"]]
        self.assertIn("04-skill-description-length", checks, out["findings"])
        layout_msg = next(f["message"] for f in out["findings"] if f["check"] == "00-layout")
        self.assertIn("requested explicitly", layout_msg)
        # Without --layout, the same folder is still not audited.
        self._user_scope(audit(self.user / "skills", self.home))

    def test_installed_plugin_is_still_audited(self) -> None:
        plugin = self.user / "plugins" / "cache" / "shop-market" / "shop-tools" / "1.0.0"
        (plugin / "skills" / "shop-refunds").mkdir(parents=True)
        (plugin / "skills" / "shop-refunds" / "SKILL.md").write_text(SKILL, encoding="utf-8")
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "shop-tools"}\n', encoding="utf-8")
        self.assertEqual(json.loads(audit(plugin, self.home).stdout)["layout"], "plugin")


if __name__ == "__main__":
    unittest.main()
