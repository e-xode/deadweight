"""`deadweight --environment`: what the external audit of 0.25.0 found in it.

    python3 -m unittest discover -s tests

The fictional shop of test_environment.py. Every credential file here is a FAKE `.claude.json` in a
temporary HOME (HOME, USERPROFILE and CLAUDE_CONFIG_DIR all point into it), and `claude` is a fake
script first on PATH: no test reads a real credential or runs the real `claude`. A test that needs a
symbolic link, a hard link or a terminal skips cleanly where the system refuses one.
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import select
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SCRIPTS = PLUGIN / "skills" / "config-auditor" / "scripts"
ENVIRONMENT = SCRIPTS / "environment.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))

import environment  # noqa: E402
from test_environment import FAKE_CLAUDE, build, skill, write  # noqa: E402

DECOY_SERVER = "shop-private-db"
DECOY = json.dumps({"mcpServers": {DECOY_SERVER: {"env": {"PGPASSWORD": "not-a-real-password"}}}})


def link(target: Path, name: Path, hard: bool = False) -> None:
    name.parent.mkdir(parents=True, exist_ok=True)
    try:
        (os.link if hard else os.symlink)(target, name)
    except (OSError, NotImplementedError, AttributeError) as e:
        raise unittest.SkipTest(f"{'hard' if hard else 'symbolic'} link refused here: {e}")


class Shop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.root, self.cfg, self.env = build(self.t)
        self.home = self.t / "home"
        # A readable fake: what the old version opened, it opened for real.
        self.decoy = self.home / ".claude.json"
        self.decoy.chmod(0o600)
        self.decoy.write_text(DECOY, encoding="utf-8")

    def tearDown(self):
        for p in self.t.rglob("*.json"):
            with contextlib.suppress(OSError):
                p.chmod(0o600)
        self.tmp.cleanup()

    def run_main(self, *args: str) -> tuple[str, list[str]]:
        """In-process, recording every file actually opened."""
        opened: list[str] = []

        def spy(real):
            def wrapper(file, *a, **k):
                if not isinstance(file, int):
                    opened.append(os.fspath(file))
                return real(file, *a, **k)
            return wrapper

        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, self.env), \
                unittest.mock.patch("builtins.open", spy(builtins.open)), \
                unittest.mock.patch("io.open", spy(io.open)), \
                contextlib.redirect_stdout(out):
            code = environment.main(["--root", str(self.root), *args])
        self.assertEqual(code, 0)
        return out.getvalue(), opened

    def assert_decoy_never_opened(self, opened: list[str], text: str) -> None:
        for f in opened:
            with contextlib.suppress(OSError):
                self.assertFalse(os.path.samefile(f, self.decoy), f"opened {f}, which is .claude.json")
            self.assertNotEqual(os.path.basename(os.path.realpath(f)), ".claude.json", f)
        self.assertNotIn(DECOY_SERVER, text)


class SecretFilesRefused(Shop):
    """co-00 / do-00: the guarantee held by name only."""

    def test_symbolic_links_to_the_state_file(self):
        (self.root / ".mcp.json").unlink()
        link(self.decoy, self.root / ".mcp.json")                       # project .mcp.json
        link(self.decoy, self.cfg / "rules" / "shop-notes.md")          # account rule
        link(self.decoy, self.root / ".claude" / "skills" / "shop-x" / "SKILL.md")   # a skill, read by the auditor's helper
        for args in ((), ("--json",)):
            text, opened = self.run_main(*args)
            self.assert_decoy_never_opened(opened, text)
        d = json.loads(self.run_main("--json")[0])
        self.assertEqual(d["project"]["mcp_servers"], [])
        self.assertNotIn("rules/shop-notes.md", d["account"]["memory_files"])
        self.assertIn(str(self.root / ".mcp.json"), d["refused"])

    def test_imports_that_reach_the_state_file(self):
        write(self.root / "CLAUDE.md", "# shop-api\n\n@../home/.claude.json\n@docs/shop-notes.md\n")
        link(self.decoy, self.root / "docs" / "shop-notes.md")          # an import that is a link to it
        write(self.cfg / "CLAUDE.md", "Personal notes.\n\n@~/.claude.json\n")
        text, opened = self.run_main("--json")
        self.assert_decoy_never_opened(opened, text)
        d = json.loads(text)
        self.assertEqual(d["project"]["memory_files"], ["CLAUDE.md", ".claude/rules/shop-style.md"])
        self.assertEqual(d["account"]["memory_files"], ["CLAUDE.md"])

    def test_relative_import_that_climbs_to_it(self):
        write(self.root / "CLAUDE.md", "# shop-api\n\n@../home/.claude.json\n")
        text, opened = self.run_main("--json")
        self.assert_decoy_never_opened(opened, text)
        self.assertNotIn("../home/.claude.json", json.loads(text)["project"]["memory_files"])

    def test_hard_link_under_another_name(self):
        link(self.decoy, self.root / ".claude" / "rules" / "shop-linked.md", hard=True)
        text, opened = self.run_main("--json")
        self.assert_decoy_never_opened(opened, text)
        self.assertNotIn(".claude/rules/shop-linked.md", json.loads(text)["project"]["memory_files"])


class AccountImports(Shop):
    """co-03: the account's memory imports load at launch."""

    def test_imports_followed_four_hops_outside_code(self):
        write(self.cfg / "CLAUDE.md", "Me.\n\n@shop-notes.md\n\n```\n@shop-fenced.md\n```\n\n@~/shop-extra.md\n")
        write(self.cfg / "shop-notes.md", "n" * 3000 + "\n@hop2.md\n")
        write(self.cfg / "shop-fenced.md", "f" * 500)
        write(self.home / "shop-extra.md", "e" * 200)
        write(self.cfg / "hop2.md", "@hop3.md\n")
        write(self.cfg / "hop3.md", "@hop4.md\n")
        write(self.cfg / "hop4.md", "@hop5.md\n")
        write(self.cfg / "hop5.md", "too deep\n")
        write(self.cfg / "rules" / "shop-rule.md", "A rule.\n@../shop-rule-detail.md\n")
        write(self.cfg / "shop-rule-detail.md", "d" * 100)
        d = json.loads(self.run_main("--json")[0])
        names = d["account"]["memory_files"]
        for n in ("shop-notes.md", "hop2.md", "hop3.md", "hop4.md", "shop-rule-detail.md",
                  str(self.home / "shop-extra.md")):
            self.assertIn(n, names)
        self.assertNotIn("hop5.md", names)
        self.assertNotIn("shop-fenced.md", names)
        self.assertGreater(d["account"]["memory_bytes"], 3300)


class MeasureConsent(Shop):
    """co-01 and do-01: what --measure runs, and where the question goes."""

    def setUp(self):
        super().setUp()
        bindir = self.t / "fakebin"
        self.calls = self.t / "calls.log"
        fake = FAKE_CLAUDE + "\nopen(" + repr(str(self.calls)) + ", 'a').write('call\\n')\n"
        script = write(bindir / "fake_claude.py", fake)
        if os.name == "nt":
            write(bindir / "claude.bat", f'@"{sys.executable}" "{script}" %*\r\n')
        else:
            write(bindir / "claude", f"#!{sys.executable}\n" + fake)
            (bindir / "claude").chmod(0o755)
        # Two project hooks for the consent text to count.
        write(self.root / ".claude" / "settings.json", json.dumps({
            "enabledPlugins": {"shop-tools@shop-market": True, "shop-off@shop-market": False},
            "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "shop-check"},
                                                {"type": "command", "command": "shop-log"}]}]}}))
        self.penv = {**os.environ, **self.env, "PYTHONDONTWRITEBYTECODE": "1",
                     "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}

    def n_calls(self) -> int:
        return len(self.calls.read_text().splitlines()) if self.calls.exists() else 0

    def on_terminal(self, *args: str, answer: str = "y\n") -> tuple[int, str, str]:
        """stdin and stderr on a terminal, stdout redirected to a pipe (`> out.json`)."""
        try:
            import pty
            master, slave = pty.openpty()
        except (ImportError, OSError) as e:
            self.skipTest(f"no pseudo-terminal here: {e}")
        try:
            proc = subprocess.Popen([sys.executable, str(ENVIRONMENT), "--root", str(self.root), *args],
                                    stdin=slave, stderr=slave, stdout=subprocess.PIPE, env=self.penv)
            os.close(slave)
            os.write(master, answer.encode())
            out, _ = proc.communicate(timeout=120)
            seen = b""
            while select.select([master], [], [], 0.3)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                seen += chunk
        finally:
            os.close(master)
        return proc.returncode, out.decode("utf-8", "replace"), seen.decode("utf-8", "replace")

    def test_json_redirected_refuses_without_yes(self):
        code, out, term = self.on_terminal("--measure", "--json")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")                          # nothing but JSON, and here nothing
        self.assertEqual(self.n_calls(), 0)
        self.assertIn("--yes", term)

    def test_question_on_the_terminal_and_says_what_runs(self):
        code, out, term = self.on_terminal("--measure")
        self.assertEqual(code, 0, term)
        self.assertNotIn("Go on?", out)
        self.assertIn("Go on?", term)
        self.assertIn("2 hook(s) of the project's settings", term)
        self.assertIn("2 server(s) of the project's .mcp.json", term)
        self.assertIn("1 mod(s)", term)
        self.assertIn("without the workspace trust dialog", term)
        self.assertEqual(self.n_calls(), 4)

    def test_json_with_yes_stays_json(self):
        done = subprocess.run([sys.executable, str(ENVIRONMENT), "--root", str(self.root), "--measure",
                               "--yes", "--json"], env=self.penv, capture_output=True, text=True,
                              encoding="utf-8", stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        d = json.loads(done.stdout)
        self.assertNotIn("nothing here runs a mod", d["mod_notes"]["cost"])
        self.assertIn("--measure", d["mod_notes"]["cost"])

    def test_help_and_default_note_say_mods_and_hooks_run(self):
        done = subprocess.run([sys.executable, str(ENVIRONMENT), "--help"], env=self.penv,
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertIn("trust dialog", done.stdout)
        self.assertIn("mods", done.stdout)
        text, _ = self.run_main()
        self.assertNotIn("nothing here runs a mod", text)


class EnvironmentAlone(unittest.TestCase):
    """do-02: --environment with another report dropped that report silently."""

    def test_combinations_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for other in ("--semantic", "--both", "--fresh", "--setup-statusline"):
                done = subprocess.run([sys.executable, str(PLUGIN / "bin" / "deadweight"), "--environment",
                                       other, tmp], capture_output=True, text=True, encoding="utf-8",
                                      stdin=subprocess.DEVNULL, timeout=60,
                                      env={**os.environ, "HOME": tmp, "USERPROFILE": tmp,
                                           "CLAUDE_CONFIG_DIR": str(Path(tmp) / ".claude")})
                self.assertEqual(done.returncode, 2, other)
                self.assertIn(other, done.stderr)


class Buckets(Shop):
    """co-02, co-04, co-05, co-06."""

    def test_local_plugin_counted_with_user_settings(self):
        write(self.root / ".claude" / "settings.local.json",
              json.dumps({"enabledPlugins": {"shop-user@shop-market": True}}))
        d = json.loads(self.run_main("--json")[0])
        local = next(p for p in d["plugins"] if p["id"] == "shop-user@shop-market")
        self.assertEqual(local["enabled_by"], "local")
        tools = next(p for p in d["plugins"] if p["id"] == "shop-tools@shop-market")
        self.assertEqual(d["comparable_to_measure_chars"]["project_setting_source"],
                         d["chars"]["project"] + environment.chars_of(tools))

    def test_manifest_path_outside_the_plugin_not_counted(self):
        outside = self.t / "shop-outside"
        write(outside / "shop-far" / "SKILL.md", skill("shop-far", "x" * 900))
        write(outside / "cmds" / "shop-cmd.md", "---\ndescription: " + "c" * 700 + "\n---\n")
        plug = self.t / "cache" / "shop-tools"
        write(plug / ".claude-plugin" / "plugin.json",
              json.dumps({"name": "shop-tools", "skills": "../../shop-outside", "commands": "../../shop-outside/cmds"}))
        s = environment.plugin_summary(plug)
        self.assertEqual((s["skills"] - 1, s.get("commands", 0)), (0, 0))   # only skills/shop-deploy
        self.assertEqual(s["outside_root"], ["../../shop-outside", "../../shop-outside/cmds"])

    def test_model_call_is_not_context(self):
        info = environment.classify_mod(["export function register(on) {\n"
                                         "  on('turn.complete', async ($, e, next) => {\n"
                                         "    const r = await $.model.complete({ prompt: 'shop' })\n"
                                         "    return next(e)\n  })\n}\n"])
        ids = [c["id"] for c in info["categories"]]
        self.assertNotIn("context", ids)
        self.assertIn("model", ids)

    def test_nested_skill_left_out_whatever_its_case(self):
        base = self.t / "shop-skills"
        for rel in ("shop-a/SKILL.md", "shop-a/Examples/SKILL.md", "shop-a/9tpl/SKILL.md",
                    "shop-a/examples2/SKILL.md", "zeta/SKILL.md"):
            write(base / rel, skill(rel.split("/")[0], "d"))
        got = [p.relative_to(base).as_posix() for p in environment.skill_files(base)]
        self.assertEqual(sorted(got), ["shop-a/SKILL.md", "zeta/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
