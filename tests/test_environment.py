"""`deadweight --environment`: what the account, the plugins and the MCP servers add.

    python3 -m unittest discover -s tests

A fictional shop: a project `shop-api`, a fake user configuration directory (CLAUDE_CONFIG_DIR,
HOME and USERPROFILE all point into the temporary folder), and a fake `claude` on PATH for
`--measure`. No test runs the real `claude`, and no test needs the execute bit on Windows.
"""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "skills" / "config-auditor" / "scripts"
ENVIRONMENT = SCRIPTS / "environment.py"
sys.path.insert(0, str(SCRIPTS))

import environment  # noqa: E402

SECRET = "sk-shop-not-a-real-token"
BUCKET = "bucket-0001"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def skill(name: str, description: str, extra: str = "") -> str:
    return f"---\nname: {name}\ndescription: {description}\n{extra}---\n\nBody of {name}.\n"


def build(tmp: Path) -> tuple[Path, Path, dict]:
    """(project root, config dir, environment variables) for the shop."""
    home = tmp / "home"
    cfg = home / ".claude"
    root = tmp / "shop-api"
    # The project.
    write(root / "CLAUDE.md", "# shop-api\n\nRun the tests before a change.\n")
    write(root / ".claude" / "rules" / "shop-style.md", "Prices are integers in cents.\n")
    write(root / ".claude" / "rules" / "shop-db.md", "---\npaths:\n  - src/db/**\n---\nUse migrations.\n")
    write(root / ".claude" / "skills" / "shop-i18n" / "SKILL.md",
          skill("shop-i18n", "Translate the shop storefront. Do not use for refunds or invoices, ever."))
    write(root / ".claude" / "skills" / "shop-long" / "SKILL.md",
          skill("shop-long", "a" * 1400, "when_to_use: " + "b" * 400 + "\n"))
    write(root / ".claude" / "skills" / "shop-hidden" / "SKILL.md",
          skill("shop-hidden", "Withheld from the listing by its own frontmatter, so it costs nothing.",
                "disable-model-invocation: true\n"))
    write(root / ".claude" / "agents" / "shop-reviewer.md",
          "---\nname: shop-reviewer\ndescription: Review a pull request of the shop.\n---\nReview.\n")
    write(root / ".claude" / "settings.json", json.dumps({
        "enabledPlugins": {"shop-tools@shop-market": True, "shop-off@shop-market": False}}))
    write(root / ".mcp.json", json.dumps({"mcpServers": {
        "shop-db": {"command": "shop-db-server", "env": {"TOKEN": SECRET}},
        "shop-search": {"url": "https://search.shop.example/mcp"}}}))
    # A plugin enabled by the project, with a mod.
    plug = tmp / "cache" / "shop-tools"
    write(plug / ".claude-plugin" / "plugin.json", json.dumps({"name": "shop-tools"}))
    write(plug / "skills" / "shop-deploy" / "SKILL.md", skill("shop-deploy", "Deploy the shop to staging."))
    write(plug / "agents" / "shop-checker.md",
          "---\nname: shop-checker\ndescription: Check a deploy.\n---\nCheck.\n")
    write(plug / ".mcp.json", json.dumps({"mcpServers": {"shop-metrics": {"command": "m"}}}))
    write(plug / "hooks" / "hooks.json", json.dumps({
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
        "modules": ["./register.js"]}))
    write(plug / "hooks" / "register.js", "export function register(on) {}\n")
    off = tmp / "cache" / "shop-off"
    write(off / "skills" / "shop-off-skill" / "SKILL.md", skill("shop-off-skill", "Disabled, never counted."))
    by_default = tmp / "cache" / "shop-user"
    write(by_default / "skills" / "shop-user-skill" / "SKILL.md", skill("shop-user-skill", "Enabled by default."))
    # The user configuration directory.
    write(cfg / "skills" / "shop-notes" / "SKILL.md", skill("shop-notes", "Take notes about the shop."))
    write(cfg / "skills" / "synced" / BUCKET / "shop-sync" / "SKILL.md", skill("shop-sync", "A synced skill."))
    write(cfg / "skills" / "synced" / BUCKET / "shop-sync" / "nested" / "SKILL.md",
          skill("shop-nested", "Inside another skill: not a skill of its own."))
    write(cfg / "agents" / "shop-helper.md", "---\nname: shop-helper\ndescription: Help.\n---\nHelp.\n")
    kit = cfg / "plugins" / "synced" / BUCKET / "shop-kit"
    write(kit / ".claude-plugin" / "plugin.json", json.dumps({"name": "shop-kit"}))
    write(kit / "skills" / "shop-kit-skill" / "SKILL.md", skill("shop-kit-skill", "A synced plugin's skill."))
    write(kit / ".mcp.json", json.dumps({"mcpServers": {"shop-crm": {"url": "https://crm.example/mcp"}}}))
    write(cfg / "plugins" / "installed_plugins.json", json.dumps({"version": 2, "plugins": {
        "shop-tools@shop-market": [{"scope": "project", "projectPath": str(root), "installPath": str(plug)}],
        "shop-off@shop-market": [{"scope": "user", "installPath": str(off)}],
        "shop-user@shop-market": [{"scope": "user", "installPath": str(by_default)}],
        "shop-elsewhere@shop-market": [{"scope": "project", "projectPath": str(tmp / "shop-web"),
                                        "installPath": str(by_default)}],
    }}))
    # Traps: files that hold secrets, which must never be opened.
    traps = [write(home / ".claude.json", json.dumps({"mcpServers": {"x": {"env": {"K": SECRET}}}})),
             write(cfg / ".claude.json", json.dumps({"mcpServers": {"y": {"env": {"K": SECRET}}}})),
             write(cfg / ".credentials.json", json.dumps({"token": SECRET}))]
    for t in traps:
        try:
            t.chmod(0)
        except OSError:
            pass
    env = {"CLAUDE_CONFIG_DIR": str(cfg), "HOME": str(home), "USERPROFILE": str(home)}
    return root, cfg, env


class EnvironmentEstimate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root, self.cfg, self.env = build(Path(self.tmp.name))

    def tearDown(self):
        for p in Path(self.tmp.name).rglob("*.json"):
            with contextlib.suppress(OSError):
                p.chmod(0o600)
        self.tmp.cleanup()

    def run_main(self, *args: str) -> tuple[str, list[str]]:
        """Run in-process, recording every file opened."""
        opened: list[str] = []
        real_open, real_io_open = builtins.open, io.open

        def spy(real):
            def wrapper(file, *a, **k):
                opened.append(os.fspath(file) if not isinstance(file, int) else str(file))
                return real(file, *a, **k)
            return wrapper

        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, self.env), \
                unittest.mock.patch("builtins.open", spy(real_open)), \
                unittest.mock.patch("io.open", spy(real_io_open)), \
                contextlib.redirect_stdout(out):
            code = environment.main(["--root", str(self.root), *args])
        self.assertEqual(code, 0)
        return out.getvalue(), opened

    def test_counts_by_origin(self):
        text, _ = self.run_main("--json")
        d = json.loads(text)
        p = d["project"]
        self.assertEqual((p["skills"], p["skills_withheld"], p["agents"]), (2, 1, 1))
        self.assertEqual(sorted(p["memory_files"]), [".claude/rules/shop-style.md", "CLAUDE.md"])
        self.assertEqual(p["mcp_servers"], ["shop-db", "shop-search"])
        a = d["account"]
        self.assertEqual((a["skills"], a["agents"]), (2, 1))  # shop-notes and shop-sync, not the nested one
        self.assertEqual([s["name"] for s in a["synced_plugins"]], ["shop-kit"])
        self.assertEqual(d["mcp"]["servers_found"], 4)
        self.assertEqual(d["chars_per_token_rough"], 2.85)

    def test_listing_cap_applies(self):
        d = json.loads(self.run_main("--json")[0])
        short = len("Translate the shop storefront. Do not use for refunds or invoices, ever.")
        self.assertEqual(d["project"]["skill_chars"], short + 1536)

    def test_enabled_plugins(self):
        d = json.loads(self.run_main("--json")[0])
        ids = {p["id"]: p["enabled_by"] for p in d["plugins"]}
        self.assertEqual(ids["shop-tools@shop-market"], "project")
        self.assertIn("default", ids["shop-user@shop-market"])
        self.assertNotIn("shop-off@shop-market", ids)          # disabled by the project
        self.assertNotIn("shop-elsewhere@shop-market", ids)    # installed for another project

    def test_mod_detected(self):
        text, _ = self.run_main()
        self.assertIn("MODS  1 found in the files read; time and token cost not measured", text)
        self.assertIn("shop-tools@shop-market: ./register.js", text)
        self.assertIn("events: none found", text)
        d = json.loads(self.run_main("--json")[0])
        tools = next(p for p in d["plugins"] if p["id"] == "shop-tools@shop-market")
        self.assertEqual((tools["mods"], tools["mcp_servers"], tools["context_hooks"]),
                         (["./register.js"], ["shop-metrics"], 1))

    def test_text_says_estimate_and_what_is_not_read(self):
        text, _ = self.run_main()
        self.assertIn("estimate from file sizes, not a measurement", text)
        self.assertIn("`--measure` measures it", text)
        self.assertIn("not read", text)
        self.assertNotIn("ERROR", text)
        self.assertNotIn("WARN", text)

    def test_secrets_never_opened_nor_printed(self):
        for args in ((), ("--json",)):
            text, opened = self.run_main(*args)
            self.assertNotIn(SECRET, text)
            names = {Path(f).name for f in opened}
            self.assertNotIn(".claude.json", names)
            self.assertNotIn(".credentials.json", names)

    def test_not_part_of_the_auditor(self):
        from deadweight_audit.identity import instrument_files
        self.assertNotIn(ENVIRONMENT, instrument_files())


# Hooks modules of fictional shop mods, read as text and never run. Each `$.fs.write` names the
# witness file: if anything executed a module, the file would exist.
MODS = {
    "shop-mod-draws": """export function register(on) {
  // a comment that names $.process.run and prompt.submit must not count
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    return { type: 'Text', props: {}, children: ['shop: 3 orders waiting'] }
  })
}
""",
    "shop-mod-injects": """export function register(on) {
  on('prompt.submit', async ($, e, next) => {
    return next({ ...e, context: [...(e.context ?? []), 'Prices are integers in cents.'] })
  })
}
""",
    "shop-mod-guard": """export function register(on) {
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (String(e.command).includes('rm -rf')) return { deny: 'Not in the shop repository.' }
    return next(e)
  })
}
""",
    "shop-mod-slow": """export function register(on) {
  on('tool.call', async ($, e, next) => {
    const status = await $.process.run(['git', 'status'])
    $.ui.status('shop: ' + status.exitCode)
    return next(e)
  })
  on('session.start', async ($, e, next) => {
    await $.fs.write(WITNESS, 'ran')
    return next(e)
  })
}
""",
    "shop-mod-opaque": """export function register(on) {
  const ev = ['tool', 'call'].join('.')
  on(ev, async ($, e, next) => next(e))
  on('session.start', async ($, e, next) => { await $.fs.write(WITNESS, 'ran'); return next(e) })
}
""",
}


def build_mods(tmp: Path) -> tuple[Path, dict, Path]:
    """A project that enables five mods and one plugin without a mod."""
    home = tmp / "home"
    cfg = home / ".claude"
    root = tmp / "shop-web"
    witness = tmp / "witness-module-ran.txt"
    write(root / "CLAUDE.md", "# shop-web\n")
    installed, enabled = {}, {}
    for name, source in MODS.items():
        plug = tmp / "cache" / name
        write(plug / ".claude-plugin" / "plugin.json", json.dumps({"name": name}))
        write(plug / "hooks" / "hooks.json", json.dumps({"modules": ["./register.js"]}))
        write(plug / "hooks" / "register.js", source.replace("WITNESS", json.dumps(str(witness))))
        installed[f"{name}@shop-market"] = [{"scope": "user", "installPath": str(plug)}]
        enabled[f"{name}@shop-market"] = True
    plain = tmp / "cache" / "shop-plain"
    write(plain / ".claude-plugin" / "plugin.json", json.dumps({"name": "shop-plain"}))
    write(plain / "skills" / "shop-plain-skill" / "SKILL.md", skill("shop-plain-skill", "No mod here."))
    write(plain / "hooks" / "hooks.json", json.dumps({"hooks": {}}))
    installed["shop-plain@shop-market"] = [{"scope": "user", "installPath": str(plain)}]
    enabled["shop-plain@shop-market"] = True
    write(cfg / "settings.json", json.dumps({"enabledPlugins": enabled}))
    write(cfg / "plugins" / "installed_plugins.json", json.dumps({"version": 2, "plugins": installed}))
    return root, {"CLAUDE_CONFIG_DIR": str(cfg), "HOME": str(home), "USERPROFILE": str(home)}, witness


class ModInventory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root, self.env, self.witness = build_mods(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *args: str) -> str:
        """In-process, with every way of starting a program replaced by a failure."""
        def refuse(*a, **k):
            raise AssertionError(f"something was started: {a!r}")

        before = set(sys.modules)
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, self.env), \
                unittest.mock.patch("subprocess.Popen", refuse), \
                unittest.mock.patch("subprocess.run", refuse), \
                unittest.mock.patch("os.system", refuse), \
                contextlib.redirect_stdout(out):
            code = environment.main(["--root", str(self.root), *args])
        self.assertEqual(code, 0)
        self.assertFalse(self.witness.exists(), "a hooks module was executed")
        new = {m for m in set(sys.modules) - before if "register" in m or "shop" in m}
        self.assertEqual(new, set(), "a hooks module was imported")
        return out.getvalue()

    def inventory(self) -> dict:
        d = json.loads(self.run_main("--json"))
        return {m["plugin"].split("@")[0]: m for m in d["mod_inventory"]}

    @staticmethod
    def cats(m: dict) -> list[str]:
        return [c["id"] for c in m["categories"]]

    def test_json_lists_every_mod_and_only_mods(self):
        inv = self.inventory()
        self.assertEqual(sorted(inv), sorted(MODS))           # shop-plain has no mod
        for m in inv.values():
            self.assertEqual(m["basis"], "static reading of the source; not a measurement")
            self.assertEqual(m["module"], "./register.js")

    def test_draws_only(self):
        m = self.inventory()["shop-mod-draws"]
        self.assertEqual((m["events"], self.cats(m)), (["ui.render"], ["draws"]))

    def test_injects(self):
        m = self.inventory()["shop-mod-injects"]
        self.assertEqual((m["events"], self.cats(m)), (["prompt.submit"], ["context"]))

    def test_guard(self):
        m = self.inventory()["shop-mod-guard"]
        self.assertEqual((m["events"], self.cats(m)), (["tool.call"], ["guard"]))

    def test_slow(self):
        m = self.inventory()["shop-mod-slow"]
        self.assertEqual(m["events"], ["tool.call", "session.start"])
        self.assertEqual(self.cats(m), ["guard", "reach", "waits"])
        self.assertIn("process.run", m["calls"])

    def test_unreadable_is_unclassified(self):
        m = self.inventory()["shop-mod-opaque"]
        self.assertIn("unclassified", self.cats(m))
        self.assertNotIn("draws", self.cats(m))
        why = next(c["why"] for c in m["categories"] if c["id"] == "unclassified")
        self.assertIn("an event name computed at run time", why)

    def test_text_labels_and_cross_check(self):
        text = self.run_main()
        self.assertIn("MODS  5 found in the files read; time and token cost not measured", text)
        self.assertEqual(text.count("[static reading of the source; not a measurement]"), 8)
        self.assertIn("- draws only [static reading", text)
        self.assertIn("measured", text.split("- draws only", 1)[1].split("shop-mod-guard")[0])
        self.assertIn("cc-plugin-diff", text)
        self.assertIn("are not in your files and are not counted", text)
        self.assertIn("mod active", text)
        self.assertNotIn(" ms", text)

    def test_missing_module_is_unclassified(self):
        (Path(self.tmp.name) / "cache" / "shop-mod-guard" / "hooks" / "register.js").unlink()
        m = self.inventory()["shop-mod-guard"]
        self.assertEqual(self.cats(m), ["unclassified"])

    def test_package_import_is_unclassified(self):
        f = Path(self.tmp.name) / "cache" / "shop-mod-draws" / "hooks" / "register.js"
        f.write_text("import { helper } from 'shop-helpers'\n" + f.read_text(encoding="utf-8"), encoding="utf-8")
        m = self.inventory()["shop-mod-draws"]
        self.assertEqual(self.cats(m), ["unclassified"])

    def test_local_import_is_followed(self):
        hooks = Path(self.tmp.name) / "cache" / "shop-mod-draws" / "hooks"
        write(hooks / "lib.js", "export async function fetchOrders($) { return $.http.fetch('https://shop.example/o') }\n")
        f = hooks / "register.js"
        f.write_text("import { fetchOrders } from './lib.js'\n" + f.read_text(encoding="utf-8"), encoding="utf-8")
        m = self.inventory()["shop-mod-draws"]
        self.assertEqual(m["files_read"], ["hooks/register.js", "hooks/lib.js"])
        self.assertEqual(self.cats(m), ["reach", "waits"])


FAKE_CLAUDE = r'''
import json, sys
args = sys.argv[1:]
if "--setting-sources" in args:
    source = args[args.index("--setting-sources") + 1]
    tokens = {"": 1000, "project": 1600}[source]
elif "--strict-mcp-config" in args:
    tokens = 1900
else:
    tokens = 2300
mcp = [] if "--strict-mcp-config" in args else [{"name": "shop-db", "status": "connected"}]
print(json.dumps({"type": "system", "subtype": "init", "skills": ["a"] * (tokens // 100),
                  "agents": ["x"], "plugins": [], "mcp_servers": mcp, "tools": ["Bash"]}))
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "MODEL-SAID-THIS"}]}}))
print(json.dumps({"type": "result", "result": "MODEL-SAID-THIS",
                  "usage": {"input_tokens": tokens - 300, "cache_creation_input_tokens": 200,
                            "cache_read_input_tokens": 100}}))
'''


class EnvironmentMeasure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.root, _, env = build(tmp)
        bindir = tmp / "fakebin"
        script = write(bindir / "fake_claude.py", FAKE_CLAUDE)
        if os.name == "nt":
            write(bindir / "claude.bat", f'@"{sys.executable}" "{script}" %*\r\n')
        else:
            write(bindir / "claude", f"#!{sys.executable}\n" + FAKE_CLAUDE)
            (bindir / "claude").chmod(0o755)
        self.env = {**os.environ, **env, "PYTHONDONTWRITEBYTECODE": "1",
                    "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}

    def tearDown(self):
        for p in Path(self.tmp.name).rglob("*.json"):
            with contextlib.suppress(OSError):
                p.chmod(0o600)
        self.tmp.cleanup()

    def run_script(self, *args: str, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ENVIRONMENT), "--root", str(self.root), *args],
                              env=self.env, capture_output=True, text=True, encoding="utf-8",
                              input=stdin, timeout=120)

    def test_measure_differences(self):
        done = self.run_script("--measure", "--yes", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        m = json.loads(done.stdout)["measured"]
        self.assertEqual([r["input_tokens"] for r in m["runs"]], [1000, 1600, 1900, 2300])
        self.assertEqual(m["differences"]["project"], 600)
        self.assertEqual(m["differences"]["account_and_user_plugins"], 300)
        self.assertEqual(m["differences"]["mcp"], 400)
        self.assertEqual(m["runs"][3]["mcp_servers"], 1)

    def test_measure_text_hides_model_output(self):
        done = self.run_script("--measure", "--yes")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("one run per condition, so noisy", done.stdout)
        self.assertIn("project adds 600", done.stdout)
        self.assertNotIn("MODEL-SAID-THIS", done.stdout)

    def test_measure_refuses_without_yes_outside_a_terminal(self):
        done = self.run_script("--measure")
        self.assertEqual(done.returncode, 2)
        self.assertIn("--yes", done.stderr)


if __name__ == "__main__":
    unittest.main()
