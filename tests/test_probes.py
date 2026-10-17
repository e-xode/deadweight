"""The probe runner, held in place without calling `claude`.

    python3 -m unittest tests.test_probes

Every probe must replay an entry that evidence.json records, and a machine without the
binary must get SKIP for every probe and exit 0. No real subprocess is started here:
`subprocess.run` is replaced by FakeClaude, which plays the binary - either as it behaved
when the evidence was recorded ("recorded"), or the opposite way ("opposite") - and
records every call. The safety and cost properties the README promises are asserted on
those calls: nothing written outside the probe's temporary folder, nothing under HOME, a
temporary CLAUDE_CONFIG_DIR for every local call, a bounded timeout on every call, no
billed call under --no-model, no more calls than each probe declares.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "probes"))

import run_probes as probes  # noqa: E402

EVIDENCE = json.loads(probes.EVIDENCE.read_text(encoding="utf-8"))["checks"]
FAKE = "/fake/shop-cli/claude"
REAL_MKDTEMP = tempfile.mkdtemp   # probes.tempfile is the module itself: patched below


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with mock.patch.object(probes.subprocess, "run", side_effect=AssertionError("subprocess")), \
            mock.patch.object(probes.shutil, "which", return_value=None), \
            contextlib.redirect_stdout(out):
        code = probes.main(list(argv))
    return code, out.getvalue()


# ---------- a fake binary ----------

@dataclass
class Call:
    cmd: list[str]
    cwd: str
    env: dict
    timeout: object

    @property
    def claude(self) -> bool:
        return self.cmd[0] == FAKE and self.cmd[1:2] != ["--version"]

    @property
    def model(self) -> bool:
        return self.claude and "-p" in self.cmd


def done(stdout: str = "", stderr: str = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def stream(*events: dict) -> str:
    return "".join(json.dumps(e) + "\n" for e in events)


def init(skills=(), agents=()) -> dict:
    return {"type": "system", "subtype": "init", "skills": list(skills), "agents": list(agents)}


def tool_use(name: str, **inputs: object) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "input": inputs}]}}


def tool_result(text: str, error: bool = False) -> dict:
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "is_error": error, "content": text}]}}


def result(text: str = "done", denials: list | None = None) -> dict:
    return {"type": "result", "result": text, "permission_denials": denials or []}


def run_hook(command: str, payload: dict) -> None:
    """What the binary does with the probe's logging hook: argv is [python, script, label, log]."""
    _py, _script, label, log = shlex.split(command)
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"label": label, **payload}) + "\n")


def frontmatter(text: str) -> dict[str, str]:
    """As the fake binary reads it: `opposite` cannot see past a byte order mark."""
    if not text.startswith("---\n"):
        return {}
    head = text[4:].split("\n---\n", 1)[0]
    return dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)


class FakeClaude:
    """`subprocess.run` for run_probes: the binary as recorded, or the opposite."""

    def __init__(self, mode: str = "recorded") -> None:
        self.mode = mode
        self.calls: list[Call] = []
        self.timeout_on: str | None = None   # a substring of the command line that times out

    def __call__(self, cmd, cwd=None, env=None, timeout=None, **_kw) -> subprocess.CompletedProcess:
        cmd = [str(c) for c in cmd]
        self.calls.append(Call(cmd, str(cwd or ""), dict(env or os.environ), timeout))
        if cmd[0] == "git":
            Path(cmd[-1], ".git").mkdir(parents=True, exist_ok=True)
            return done()
        if self.timeout_on and self.timeout_on in " ".join(cmd):
            raise subprocess.TimeoutExpired(cmd, timeout or 0)
        if cmd[1:2] == ["--version"]:
            return done("9.9.9 (Shop CLI fake)\n")
        if cmd[1:3] == ["plugin", "validate"]:
            return self.plugin_validate(Path(cmd[3]))
        if cmd[1:3] == ["mcp", "list"]:
            return self.mcp_list()
        if cmd[1] == "-p":
            return self.ask(Path(cwd), cmd[2])
        return done(stderr="error: unknown command\n", code=1)

    @property
    def recorded(self) -> bool:
        return self.mode == "recorded"

    # -- local subcommands --
    def plugin_validate(self, root: Path) -> subprocess.CompletedProcess:
        manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        errors = []
        if self.recorded:
            themes = manifest.get("experimental", {}).get("themes")
            if themes and not themes.startswith("./"):
                errors.append('experimental.themes: Invalid string: must start with "./"')
            if ".." in str(manifest.get("monitors", "")):
                errors.append('monitors: Path contains ".." which could be a path traversal attempt')
            if any(not w.startswith("./") for w in manifest.get("workflows", [])):
                errors.append('workflows.0: Invalid string: must start with "./"')
        if errors:
            return done(stderr="\n".join(errors) + "\n", code=1)
        return done("Validation passed\n")

    def mcp_list(self) -> subprocess.CompletedProcess:
        if self.recorded:
            return done('[Warning] [shop-sdk] Skipped - MCP server "shop-sdk" declares type "sdk", '
                        "which only an SDK host application can register\nshop-stdio: true - pending\n")
        return done("shop-sdk: sdk\nshop-stdio: true - pending\n")

    # -- model runs --
    def ask(self, cwd: Path, prompt: str) -> subprocess.CompletedProcess:
        settings_file = cwd / ".claude" / "settings.json"
        settings = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.is_file() else {}
        if prompt == probes.MATCHER_PROMPT:
            return self.matcher(settings)
        if "shop-refunds" in prompt:
            return self.bom(cwd, settings)
        if "shop-orders" in prompt:
            return self.skill_hooks_empty(cwd)
        if prompt == "Reply with the single word OK." and (cwd / "docs" / "h1.md").is_file():
            return self.import_syntax(cwd, settings)
        if "shop-reader" in prompt:
            text = ("Agent 'shop-reader' would be spawned with zero tools - refusing. Its tools list "
                    "resolved to nothing: unrecognized [TaskOutput].") if self.recorded else "Read"
            return done(stream(init(), tool_use("Agent", subagent_type="shop-reader"),
                               tool_result(text, error=self.recorded), result()))
        if "`ls`" in prompt:
            hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
            blocks = hook.get("onFailure") == "block" and self.recorded
            text = ('PreToolUse:Bash hook error: failed; blocking because onFailure is "block"'
                    if blocks else "README.md")
            return done(stream(init(), tool_use("Bash", command="ls"),
                               tool_result(text, error=blocks), result()))
        if "git status" in prompt:
            rule = settings["permissions"]["deny"][0]
            denied = (rule == "Bash(git status)") if self.recorded else True
            events = [init(), tool_use("Bash", command="git status")]
            events += [tool_result("denied", error=True)] if denied else [tool_result("clean")]
            return done(stream(*events, result(denials=[{"tool_name": "Bash"}] if denied else [])))
        return done(stream(init(), result("I do not know this probe")))

    def matcher(self, settings: dict) -> subprocess.CompletedProcess:
        def fires(matcher: str, tool: str) -> bool:
            if matcher == "Bash|Write":
                return True
            if matcher == "Bash(git *)|Write":
                return tool == "Write"
            return tool == "Write" and not self.recorded    # Write|Edit(*.ts)
        for tool in ("Bash", "Write"):
            for group in settings["hooks"]["PreToolUse"]:
                if fires(group["matcher"], tool):
                    run_hook(group["hooks"][0]["command"],
                             {"hook_event_name": "PreToolUse", "tool_name": tool})
        return done(stream(init(), tool_use("Bash", command="git status"), tool_result("clean"),
                           tool_use("Write", file_path="note.txt"), tool_result("ok"), result()))

    def bom(self, cwd: Path, settings: dict) -> subprocess.CompletedProcess:
        def read(path: Path) -> dict[str, str]:
            text = path.read_text(encoding="utf-8")
            return frontmatter(text.removeprefix(probes.BOM) if self.recorded else text)
        skills, agents, descriptions = [], [], {}
        for skill in sorted((cwd / ".claude" / "skills").glob("*/SKILL.md")):
            fields = read(skill)
            descriptions[skill.parent.name] = fields.get("description", "---")
            if fields.get("user-invocable") != "false":
                skills.append(skill.parent.name)
        for agent in sorted((cwd / ".claude" / "agents").glob("*.md")):
            name = read(agent).get("name")
            if name:
                agents.append(name)
        command = settings["hooks"]["InstructionsLoaded"][0]["hooks"][0]["command"]

        def load(path: Path, reason: str) -> None:
            run_hook(command, {"hook_event_name": "InstructionsLoaded", "file_path": str(path),
                               "load_reason": reason})
        rules = cwd / ".claude" / "rules"
        load(cwd / "CLAUDE.md", "session_start")
        for rule in sorted(rules.glob("*.md")):
            if "paths" not in read(rule) and "paths:" not in rule.read_text(encoding="utf-8")[:20]:
                load(rule, "session_start")
        if not self.recorded:
            load(rules / "payments.md", "session_start")
        load(rules / "web.md", "path_glob_match")
        load(rules / "payments.md", "path_glob_match")
        return done(stream(init(skills, agents),
                           tool_use("Read", file_path=str(cwd / "src/web/page.ts")), tool_result("1"),
                           tool_use("Read", file_path=str(cwd / "src/payments/amount.ts")),
                           tool_result("1"), result(descriptions["shop-refunds"])))

    def skill_hooks_empty(self, cwd: Path) -> subprocess.CompletedProcess:
        skills = sorted(p.parent.name for p in (cwd / ".claude" / "skills").glob("*/SKILL.md")
                        if self.recorded or "hooks:" not in p.read_text(encoding="utf-8"))
        if "shop-orders" not in skills:
            return done(stream(init(skills), result("There is no skill shop-orders.")))
        return done(stream(init(skills), tool_use("Skill", skill="shop-orders"),
                           tool_result("Launching skill: shop-orders"), result("plover-12")))


    def import_syntax(self, cwd: Path, settings: dict) -> subprocess.CompletedProcess:
        """Loads what 2.1.302 loaded; `opposite` loads every file a form names."""
        command = settings["hooks"]["InstructionsLoaded"][0]["hooks"][0]["command"]
        loads = ["CLAUDE.md"]
        loads += [t for _l, _x, t, want in probes.import_forms() if want or not self.recorded]
        loads += [t for t, want in probes.IMPORT_CHAIN.items() if want or not self.recorded]
        for rel in loads:
            run_hook(command, {"hook_event_name": "InstructionsLoaded",
                               "file_path": str(cwd / rel), "load_reason": "include"})
        return done(stream(init(), result("OK")))


class Sandbox:
    """mkdtemp under a sandbox, HOME moved into it, and every Path write checked against the
    probe's own temporary folders."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = Path(REAL_MKDTEMP(prefix="shop-sandbox-"))
        test.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.home = self.root / "home"
        self.home.mkdir()
        self.tmp = self.root / "tmp"
        self.tmp.mkdir()
        self.made: list[Path] = []
        self.outside: list[str] = []

    def mkdtemp(self, prefix: str = "", **_kw: object) -> str:
        made = Path(REAL_MKDTEMP(prefix=prefix, dir=self.tmp))
        self.made.append(made)
        return str(made)

    def inside(self, path: Path) -> bool:
        resolved = Path(path).resolve()
        return any(resolved == m.resolve() or m.resolve() in resolved.parents for m in self.made)

    @contextlib.contextmanager
    def active(self, fake: FakeClaude):
        guarded = {}
        for name in ("write_text", "write_bytes", "mkdir", "touch"):
            original = getattr(Path, name)

            def guard(path, *a, _original=original, **kw):
                if not self.inside(path):
                    self.outside.append(str(path))
                return _original(path, *a, **kw)
            guarded[name] = guard
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {"HOME": str(self.home),
                                                             "USERPROFILE": str(self.home)}))
            stack.enter_context(mock.patch.object(probes.tempfile, "mkdtemp", side_effect=self.mkdtemp))
            stack.enter_context(mock.patch.object(probes.subprocess, "run", side_effect=fake))
            stack.enter_context(mock.patch.object(probes.shutil, "which", return_value=FAKE))
            for name, guard in guarded.items():
                stack.enter_context(mock.patch.object(Path, name, guard))
            yield


def replay(test: unittest.TestCase, probe: probes.Probe, mode: str = "recorded",
           isolate: bool = False) -> tuple[probes.Verdict, FakeClaude, Sandbox]:
    fake, box = FakeClaude(mode), Sandbox(test)
    with box.active(fake), contextlib.redirect_stdout(io.StringIO()):
        verdict = probes.run_one(probe, FAKE, isolate, [])
    return verdict, fake, box


def main_with_fake(test: unittest.TestCase, fake: FakeClaude, *argv: str) -> tuple[int, str]:
    box, out = Sandbox(test), io.StringIO()
    with box.active(fake), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = probes.main(list(argv))
    return code, out.getvalue()


# ---------- tests ----------

class Evidence(unittest.TestCase):
    def test_every_probe_replays_a_recorded_test(self) -> None:
        for probe in probes.PROBES:
            with self.subTest(probe=probe.check):
                self.assertIn(probe.check, EVIDENCE)
                entry = EVIDENCE[probe.check].get(probe.entry)
                self.assertIsInstance(entry, dict, f"{probe.check}.{probe.entry}")
                self.assertTrue(probe.entry.startswith("tested"))
                self.assertIn("claude_code", entry)

    def test_every_left_out_test_is_recorded_and_not_also_a_probe(self) -> None:
        implemented = {(p.check, p.entry) for p in probes.PROBES}
        for check, entry in probes.NOT_IMPLEMENTED:
            self.assertIn(entry, EVIDENCE.get(check, {}), f"{check}.{entry}")
            self.assertNotIn((check, entry), implemented)

    def test_every_recorded_test_is_a_probe_or_says_why_not(self) -> None:
        accounted = {(p.check, p.entry) for p in probes.PROBES} | set(probes.NOT_IMPLEMENTED)
        recorded = {(check, key) for check, entry in EVIDENCE.items() for key in entry
                    if key.startswith("tested") and isinstance(entry[key], dict)}
        self.assertEqual(recorded - accounted, set())


class MissingBinary(unittest.TestCase):
    def test_all_skip_and_exit_0(self) -> None:
        code, out = run()
        self.assertEqual(code, 0)
        self.assertIn("claude --version: claude not found", out)
        verdicts = [line.split()[0] for line in out.splitlines()
                    if line.split() and line.split()[0] in ("PASS", "FAIL", "SKIP", "ERROR")]
        self.assertEqual(verdicts, ["SKIP"] * len(probes.PROBES))
        self.assertIn("Not implemented:", out)

    def test_a_named_binary_that_does_not_exist_is_missing(self) -> None:
        code, out = run("--claude", "/nonexistent/shop-cli/claude")
        self.assertEqual(code, 0)
        self.assertNotIn("PASS", out)


class Verdicts(unittest.TestCase):
    """Each probe tells the recorded behaviour from its opposite: a probe that always says
    PASS, or reads the wrong signal, fails here."""

    def test_each_probe_passes_on_the_recorded_behaviour(self) -> None:
        for probe in probes.PROBES:
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                (verdict, detail), _fake, _box = replay(self, probe)
                self.assertEqual(verdict, "PASS", detail)

    def test_each_probe_fails_on_the_opposite_behaviour(self) -> None:
        for probe in probes.PROBES:
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                (verdict, detail), _fake, _box = replay(self, probe, "opposite")
                self.assertEqual(verdict, "FAIL", detail)


class ImportFormsOnWindows(unittest.TestCase):
    """`docs/colonfile.md:` cannot be created on Windows (external audit of 0.27.0, D-03): the probe
    leaves that form out there, and what the form shows is checked on the string, with no file."""

    def test_windows_leaves_out_only_the_forms_it_cannot_create(self) -> None:
        left_out = [f[2] for f in probes.IMPORT_FORMS if f not in probes.import_forms(windows=True)]
        self.assertEqual(left_out, ["docs/colonfile.md:"])
        self.assertEqual(probes.import_forms(windows=False), probes.IMPORT_FORMS)
        self.assertTrue(probes.creatable("docs/commafile.md,", windows=True))

    def test_the_probe_still_tells_the_two_behaviours_apart_without_that_form(self) -> None:
        probe = next(p for p in probes.PROBES if p.check == "01-claude-md-import-syntax")
        written: list[str] = []
        real_write = probes.write

        def spy(path: Path, text: str) -> Path:
            written.append(path.name)
            return real_write(path, text)
        with mock.patch.object(probes, "IS_WINDOWS", True), mock.patch.object(probes, "write", spy):
            (verdict, detail), _fake, _box = replay(self, probe)
            self.assertEqual(verdict, "PASS", detail)
            self.assertIn("left out, no such file on this system: colon after, file named with the colon", detail)
            self.assertIn("commafile.md,", written)
            self.assertNotIn("colonfile.md:", written)
            (verdict, detail), _fake, _box = replay(self, probe, "opposite")
            self.assertEqual(verdict, "FAIL", detail)

    def test_the_auditor_reads_each_left_out_form_from_the_string(self) -> None:
        sys.path.insert(0, str(HERE.parent / "skills" / "config-auditor" / "scripts"))
        from deadweight_audit.parsing.markdown import import_tokens, memory_imports
        for label, text, target, loaded in probes.IMPORT_FORMS:
            if probes.creatable(target, windows=True):
                continue
            with self.subTest(form=label):
                self.assertFalse(loaded, "recorded as not loaded on 2.1.302")
                (token,) = import_tokens(text)
                self.assertEqual((token.ref, token.stop_after), ("docs/colonfile.md", ":"))
                self.assertEqual(memory_imports(text), [])


class Safety(unittest.TestCase):
    def test_nothing_is_written_outside_the_probe_folder_which_is_removed(self) -> None:
        for probe in probes.PROBES:
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                _verdict, fake, box = replay(self, probe)
                self.assertEqual(box.outside, [])
                self.assertTrue(box.made, "no mkdtemp folder")
                for call in fake.calls:
                    if call.claude:
                        self.assertTrue(box.inside(Path(call.cwd)), f"cwd {call.cwd}")
                    elif call.cmd[0] == "git":
                        self.assertTrue(box.inside(Path(call.cmd[-1])), f"git {call.cmd}")
                self.assertEqual(list(box.tmp.iterdir()), [], "the temporary folder is left behind")

    def test_nothing_under_home_and_local_calls_get_a_temporary_config(self) -> None:
        for probe in probes.PROBES:
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                _verdict, fake, box = replay(self, probe)
                self.assertEqual(list(box.home.iterdir()), [], "something was written under HOME")
                for call in fake.calls:
                    self.assertNotIn(str(box.home), " ".join(call.cmd))
                    config = call.env.get("CLAUDE_CONFIG_DIR")
                    if call.claude and not call.model:
                        self.assertIsNotNone(config, f"local call without CLAUDE_CONFIG_DIR: {call.cmd}")
                    if config:
                        self.assertTrue(box.inside(Path(config)), f"CLAUDE_CONFIG_DIR {config}")

    def test_isolate_config_gives_model_calls_a_temporary_config(self) -> None:
        for probe in (p for p in probes.PROBES if p.model):
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                _verdict, fake, box = replay(self, probe, isolate=True)
                for call in (c for c in fake.calls if c.model):
                    config = call.env.get("CLAUDE_CONFIG_DIR", "")
                    self.assertTrue(config and box.inside(Path(config)), config)

    def test_every_call_has_a_bounded_timeout(self) -> None:
        self.assertLessEqual(probes.TIMEOUT, 600)
        for probe in probes.PROBES:
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                _verdict, fake, _box = replay(self, probe)
                for call in fake.calls:
                    self.assertIsNotNone(call.timeout, call.cmd)
                    self.assertLessEqual(call.timeout, probes.TIMEOUT, call.cmd)

    def test_a_timeout_is_an_error_not_a_failure(self) -> None:
        probe = next(p for p in probes.PROBES if p.check == "43-mcp-shape")
        fake, box = FakeClaude(), Sandbox(self)
        fake.timeout_on = "mcp list"
        with box.active(fake):
            verdict, detail = probes.run_one(probe, FAKE, False, [])
        self.assertEqual(verdict, "ERROR", detail)


class Cost(unittest.TestCase):
    def test_no_probe_calls_claude_more_than_it_declares(self) -> None:
        for probe in probes.PROBES:
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                _verdict, fake, _box = replay(self, probe)
                claude = [c for c in fake.calls if c.claude]
                self.assertEqual(len(claude), probe.runs)
                self.assertEqual(any(c.model for c in claude), probe.model)

    def test_a_probe_past_its_declared_calls_is_stopped(self) -> None:
        def greedy(ctx: probes.Context) -> probes.Verdict:
            for _ in range(3):
                ctx.run(["mcp", "list"], ctx.tmp, model=False)
            return "PASS", "three calls"
        probe = probes.Probe("43-mcp-shape", "tested", False, 2, greedy)
        fake, box = FakeClaude(), Sandbox(self)
        with box.active(fake):
            verdict, _detail = probes.run_one(probe, FAKE, False, [])
        self.assertEqual(verdict, "ERROR")
        self.assertEqual(len([c for c in fake.calls if c.claude]), 2)

    def test_model_calls_carry_the_budget_and_isolation_flags(self) -> None:
        for probe in (p for p in probes.PROBES if p.model):
            with self.subTest(probe=f"{probe.check} {probe.entry}"):
                _verdict, fake, _box = replay(self, probe)
                for call in (c for c in fake.calls if c.model):
                    budget = call.cmd[call.cmd.index("--max-budget-usd") + 1]
                    self.assertLessEqual(float(budget), float(probes.BUDGET))
                    self.assertLessEqual(float(probes.BUDGET), 0.25)
                    for flag in ("--no-session-persistence", "--strict-mcp-config"):
                        self.assertIn(flag, call.cmd)
                    self.assertEqual(call.cmd[call.cmd.index("--setting-sources") + 1], "project")
                    self.assertEqual(call.cmd[call.cmd.index("--model") + 1], "haiku")

    def test_no_model_makes_no_billed_call(self) -> None:
        fake = FakeClaude()
        code, out = main_with_fake(self, fake, "--no-model")
        self.assertEqual([c.cmd for c in fake.calls if c.model], [])
        self.assertEqual(code, 0, out)
        skipped = [line for line in out.splitlines() if line.startswith("SKIP") and "--no-model" in line]
        self.assertEqual(len(skipped), sum(p.model for p in probes.PROBES))


class CouldNotRun(unittest.TestCase):
    def test_a_binary_that_prints_nothing_is_an_error(self) -> None:
        silent = mock.Mock(side_effect=lambda cmd, **kw: done())
        for probe in (p for p in probes.PROBES if not p.model):
            with self.subTest(probe=probe.check):
                box = Sandbox(self)
                with box.active(FakeClaude()), mock.patch.object(probes.subprocess, "run", silent):
                    verdict, detail = probes.run_one(probe, FAKE, False, [])
                self.assertEqual(verdict, "ERROR", detail)

    def test_an_unknown_subcommand_is_an_error(self) -> None:
        old = mock.Mock(side_effect=lambda cmd, **kw: done(stderr="error: unknown command 'mcp'\n", code=1))
        probe = next(p for p in probes.PROBES if p.check == "43-mcp-shape")
        box = Sandbox(self)
        with box.active(FakeClaude()), mock.patch.object(probes.subprocess, "run", old):
            verdict, _detail = probes.run_one(probe, FAKE, False, [])
        self.assertEqual(verdict, "ERROR")

    def test_a_model_that_makes_no_call_is_an_error(self) -> None:
        probe = next(p for p in probes.PROBES if p.check == "35-hooks-matcher")
        idle = mock.Mock(side_effect=lambda cmd, **kw: done(stream(init(), result("no"))))
        box = Sandbox(self)
        with box.active(FakeClaude()), mock.patch.object(probes.subprocess, "run", idle):
            verdict, _detail = probes.run_one(probe, FAKE, False, [])
        self.assertEqual(verdict, "ERROR")

    def test_a_misspelt_only_exits_non_zero_and_runs_nothing(self) -> None:
        fake = FakeClaude()
        code, out = main_with_fake(self, fake, "--only", "44-plugin-paths")
        self.assertEqual(code, 2)
        self.assertIn("no probe for 44-plugin-paths", out)
        self.assertEqual(fake.calls, [])


class StreamParsing(unittest.TestCase):
    def test_tool_results_and_denials(self) -> None:
        events = [
            {"type": "system", "message": "a string, not a message"},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": True, "content": "denied"}]}},
            {"type": "result", "permission_denials": [{"tool_name": "Bash"}]},
        ]
        self.assertEqual(probes.tool_results(events), [(True, "denied")])
        self.assertEqual(len(probes.denials(events)), 1)


if __name__ == "__main__":
    unittest.main()
