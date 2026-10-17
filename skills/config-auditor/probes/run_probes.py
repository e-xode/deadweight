"""Replay, against the local `claude` binary, facts the auditor records as tested.

    python3 skills/config-auditor/probes/run_probes.py            # every probe
    python3 skills/config-auditor/probes/run_probes.py --list     # what exists, runs nothing
    python3 skills/config-auditor/probes/run_probes.py --only 35-hooks-shape --no-model

Each probe replays one `tested*` entry of skills/config-auditor/evidence.json, with the
method written there, and prints PASS (the recorded result still holds), FAIL (it does
not: the reference may be stale), ERROR (the probe could not run as written - no evidence
either way: a timeout, empty output, an unknown subcommand, calls the model did not make,
or more claude calls than the probe declares) or SKIP, next to `claude --version`. Exit 1
on any FAIL or ERROR, 2 when --only names no probe.

Safety. Every probe runs in its own `tempfile.mkdtemp()` directory, removed afterwards;
every file it writes is under it. Probes that need no model also point CLAUDE_CONFIG_DIR
there, so the binary's own state stays in the temporary folder. Probes that call a model
(`claude -p --model haiku`, each one billed run) use the configuration the binary finds
by itself - this script never reads, copies or prints credentials - and pass
--no-session-persistence, --strict-mcp-config and --setting-sources project so that no
transcript is kept and no user setting, plugin or MCP server joins the run; the binary
may still update its own state files. --isolate-config gives model probes a temporary
CLAUDE_CONFIG_DIR as well (it then needs credentials in the environment, as in CI).
Without `claude` on PATH, every probe is SKIP and the exit status is 0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent / "evidence.json"
TIMEOUT = 180          # seconds, per claude invocation
BUDGET = "0.25"        # --max-budget-usd, per model run
MODEL = "haiku"


class ProbeError(Exception):
    """The probe itself could not run as written: not evidence either way."""


@dataclass
class Context:
    claude: str
    tmp: Path
    isolate_config: bool
    runs: list[str]    # one line per claude invocation, for the cost report
    limit: int = 0     # the probe's declared invocations; one more raises ProbeError
    used: int = 0

    def env(self, model: bool) -> dict[str, str]:
        env = dict(os.environ)
        if not model or self.isolate_config:
            config = self.tmp / "claude-config"
            config.mkdir(exist_ok=True)
            env["CLAUDE_CONFIG_DIR"] = str(config)
        return env

    def run(self, args: list[str], cwd: Path, *, model: bool) -> subprocess.CompletedProcess:
        if self.limit and self.used >= self.limit:
            raise ProbeError(f"the probe tried more than its declared {self.limit} claude call(s)")
        self.used += 1
        self.runs.append(("model  " if model else "local  ") + " ".join(args[:3]))
        return subprocess.run([self.claude, *args], cwd=cwd, env=self.env(model),
                              capture_output=True, text=True, timeout=TIMEOUT,
                              stdin=subprocess.DEVNULL)

    def ask(self, cwd: Path, prompt: str, *extra: str) -> list[dict]:
        """One `claude -p --model haiku` run in stream-json; the parsed events (kept in cwd)."""
        # The prompt goes first: --allowedTools is variadic and would swallow it.
        done = self.run(["-p", prompt, "--model", MODEL, "--setting-sources", "project",
                         "--output-format", "stream-json", "--verbose",
                         "--no-session-persistence", "--strict-mcp-config",
                         "--max-budget-usd", BUDGET, *extra], cwd, model=True)
        (cwd / "probe-stream.jsonl").write_text(done.stdout, encoding="utf-8")
        if not done.stdout.strip():
            raise ProbeError(f"claude printed nothing (exit {done.returncode}): "
                             f"{done.stderr.strip()[-200:]}")
        events = []
        for line in done.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def git_init(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True,
                   timeout=30)
    return path


def tool_results(events: list[dict]) -> list[tuple[bool, str]]:
    """(is_error, text) of every tool_result block in the stream."""
    found = []
    for event in events:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if event.get("type") != "user" or not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                found.append((bool(block.get("is_error")), str(body)))
    return found


def denials(events: list[dict]) -> list:
    final = next((e for e in reversed(events) if e.get("type") == "result"), {})
    return final.get("permission_denials") or []


def init_event(events: list[dict]) -> dict:
    """The `system`/`init` event: the skills, agents and tools the session started with."""
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"),
                None)
    if init is None:
        raise ProbeError("no init event in the stream")
    return init


def tool_uses(events: list[dict]) -> list[tuple[str, dict]]:
    """(tool name, input) of every tool_use block the model sent."""
    found = []
    for event in events:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if event.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                found.append((str(block.get("name")), block.get("input") or {}))
    return found


def final_text(events: list[dict]) -> str:
    final = next((e for e in reversed(events) if e.get("type") == "result"), {})
    return str(final.get("result") or "")


HOOK_LOGGER = """import json, sys
event = json.load(sys.stdin)
keep = ("hook_event_name", "tool_name", "file_path", "load_reason")
line = {"label": sys.argv[1], **{k: event.get(k) for k in keep}}
with open(sys.argv[2], "a", encoding="utf-8") as log:
    log.write(json.dumps(line) + "\\n")
"""


def hook_logger(ctx: Context, project: Path) -> tuple[Callable[[str], str], Path]:
    """A command hook that appends {label, event, tool, file, reason} to project/hook-log.jsonl.

    The script and its log stay in the probe's temporary folder; it is run by the Python
    running this script, so no other interpreter is assumed."""
    script = write(ctx.tmp / "hook_log.py", HOOK_LOGGER)
    log = project / "hook-log.jsonl"
    return (lambda label: shlex.join([sys.executable, str(script), label, str(log)])), log


def read_log(log: Path) -> list[dict]:
    if not log.is_file():
        return []
    lines = []
    for raw in log.read_text(encoding="utf-8").splitlines():
        try:
            lines.append(json.loads(raw))
        except ValueError:
            continue
    return lines


def local_output(done: subprocess.CompletedProcess, what: str) -> str:
    """stdout + stderr of a local command; ProbeError when it says nothing or is not a command."""
    output = (done.stdout or "") + (done.stderr or "")
    if not output.strip():
        raise ProbeError(f"`claude {what}` printed nothing (exit {done.returncode})")
    if re.search(r"unknown (command|subcommand|option)|unrecognized (command|argument)",
                 output, re.I):
        raise ProbeError(f"`claude {what}` is not understood by this binary: "
                         f"{output.strip()[-200:]}")
    return output


Verdict = tuple[str, str]   # ("PASS" | "FAIL" | "ERROR" | "SKIP", detail)


# ---------- probes ----------

def probe_plugin_path(ctx: Context) -> Verdict:
    """44-plugin-path: three manifest paths refused by `claude plugin validate`, a control passes."""
    cases = {
        "themes": ({"experimental": {"themes": "themes/"}},
                   'experimental.themes: Invalid string: must start with "./"'),
        "monitors": ({"monitors": "./../shared/monitors.json"}, 'Path contains ".."'),
        "workflows": ({"workflows": ["workflows/refund.js"]},
                      'workflows.0: Invalid string: must start with "./"'),
        "control": ({"experimental": {"themes": "./themes/"}}, None),
    }
    missed = []
    for name, (fields, expected) in cases.items():
        root = ctx.tmp / f"shop-plugin-{name}"
        (root / "themes").mkdir(parents=True)
        write(root / ".claude-plugin" / "plugin.json",
              json.dumps({"name": "shop-plugin", "version": "0.0.1",
                          "description": "Probe plugin of an invented shop.", **fields}))
        done = ctx.run(["plugin", "validate", str(root)], ctx.tmp, model=False)
        output = local_output(done, "plugin validate")
        if expected is None:
            if done.returncode != 0:
                missed.append(f"control exited {done.returncode}")
        elif expected not in output:
            missed.append(f"{name}: no '{expected}'")
    return ("FAIL", "; ".join(missed)) if missed else ("PASS", "3 refused, control passed")


def probe_mcp_sdk(ctx: Context) -> Verdict:
    """43-mcp-shape: `claude mcp list` skips a type sdk server in .mcp.json, lists the stdio one."""
    repo = git_init(ctx.tmp / "shop-repo")
    write(repo / ".mcp.json", json.dumps({"mcpServers": {
        "shop-sdk": {"type": "sdk"}, "shop-stdio": {"command": "true"}}}))
    done = ctx.run(["mcp", "list"], repo, model=False)
    output = local_output(done, "mcp list")
    expected = 'declares type "sdk", which only an SDK host application can register'
    if expected not in output:
        return "FAIL", f"no '{expected}'"
    if "shop-stdio" not in output:
        return "FAIL", "the stdio server is not listed"
    return "PASS", "sdk server skipped, stdio server listed"


def probe_onfailure_block(ctx: Context) -> Verdict:
    """35-hooks-shape: a PreToolUse hook that cannot start blocks `ls` only with onFailure block."""
    outcome = {}
    for name, extra in (("block", {"onFailure": "block"}), ("default", {})):
        project = ctx.tmp / f"shop-{name}"
        hook = {"type": "command", "command": "node",
                "args": [str(project / "missing-check.js")], "timeout": 10, **extra}
        write(project / ".claude" / "settings.json", json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}}))
        events = ctx.ask(project, "Run the shell command `ls` with the Bash tool, then reply "
                                  "with the single word done.", "--allowedTools", "Bash")
        results = tool_results(events)
        if not results:
            raise ProbeError(f"{name}: no tool call in the stream ({len(events)} events)")
        outcome[name] = results
    blocked = any(err and 'blocking because onFailure is "block"' in text
                  for err, text in outcome["block"])
    ran = any(not err for err, _ in outcome["default"])
    if blocked and ran:
        return "PASS", "blocked with onFailure block; ran without it"
    return "FAIL", f"blocked with block: {blocked}; ran without: {ran}"


def probe_taskoutput_agent(ctx: Context) -> Verdict:
    """23-agent-tools: an agent whose only tool is TaskOutput is refused, zero tools."""
    repo = git_init(ctx.tmp / "shop-repo")
    write(repo / ".claude" / "agents" / "shop-reader.md",
          "---\nname: shop-reader\ndescription: Reads the files of the shop project.\n"
          "tools: TaskOutput\n---\nYou read files and list what you find.\n")
    events = ctx.ask(repo, "Call the Agent tool with subagent_type shop-reader and the prompt "
                           "'List the tools you have.' Then report what the tool returned.")
    text = json.dumps(events)
    if "would be spawned with zero tools" in text and "unrecognized [TaskOutput]" in text:
        return "PASS", "refused: zero tools, unrecognized [TaskOutput]"
    return "FAIL", "no refusal naming TaskOutput in the stream"


def probe_colon_star(ctx: Context) -> Verdict:
    """42-permissions-rule: deny Bash(git:* status) does not stop `git status`; Bash(git status) does."""
    seen = {}
    for name, rule in (("colon", "Bash(git:* status)"), ("control", "Bash(git status)")):
        repo = git_init(ctx.tmp / f"shop-{name}")
        write(repo / ".claude" / "settings.json",
              json.dumps({"permissions": {"deny": [rule]}}))
        events = ctx.ask(repo, "Run exactly the shell command `git status` with the Bash tool, "
                               "once, then reply with the single word done.",
                         "--allowedTools", "Bash")
        if not tool_results(events) and not denials(events):
            raise ProbeError(f"{name}: no tool call in the stream ({len(events)} events)")
        seen[name] = bool(denials(events))
    if not seen["colon"] and seen["control"]:
        return "PASS", "git:* status let git status run; the control rule denied it"
    return "FAIL", f"denied with git:* status: {seen['colon']}; with the control: {seen['control']}"


MATCHER_PROMPT = ("Run exactly the shell command `git status` with the Bash tool, once. Then create "
                  "the file note.txt containing the word ok with the Write tool. Then reply with "
                  "the single word done.")


def probe_matcher_alternatives(ctx: Context) -> Verdict:
    """35-hooks-matcher: a permission rule as one `|` alternative of a PreToolUse matcher.

    Two projects, each with a `Bash|Write` control group: `Bash(git *)|Write` (a valid regular
    expression) and `Write|Edit(*.ts)` (not one: `(*` repeats nothing)."""
    fired: dict[str, dict[str, set[str]]] = {}
    for name, matcher in (("valid", "Bash(git *)|Write"), ("invalid", "Write|Edit(*.ts)")):
        project = git_init(ctx.tmp / f"shop-{name}")
        command, log = hook_logger(ctx, project)
        groups = [{"matcher": matcher, "hooks": [{"type": "command", "command": command("probe")}]},
                  {"matcher": "Bash|Write",
                   "hooks": [{"type": "command", "command": command("control")}]}]
        write(project / ".claude" / "settings.json", json.dumps({"hooks": {"PreToolUse": groups}}))
        ctx.ask(project, MATCHER_PROMPT, "--allowedTools", "Bash", "Write")
        seen: dict[str, set[str]] = {"probe": set(), "control": set()}
        for line in read_log(log):
            if line.get("hook_event_name") == "PreToolUse" and line.get("label") in seen:
                seen[line["label"]].add(str(line.get("tool_name")))
        if not {"Bash", "Write"} <= seen["control"]:
            raise ProbeError(f"{name}: the control group saw {sorted(seen['control'])}, not Bash "
                             "and Write - the model did not make both calls")
        fired[name] = seen
    facts = (f"`Bash(git *)|Write` fired on {sorted(fired['valid']['probe']) or 'nothing'}; "
             f"`Write|Edit(*.ts)` fired on {sorted(fired['invalid']['probe']) or 'nothing'}; "
             "control `Bash|Write` fired on Bash and Write in both projects")
    if fired["valid"]["probe"] == {"Write"} and not fired["invalid"]["probe"]:
        return "PASS", facts
    return "FAIL", facts


BOM = "\ufeff"


def probe_bom_frontmatter(ctx: Context) -> Verdict:
    """frontmatter-bom: a UTF-8 byte order mark before the opening `---` of a skill, an agent, a rule.

    Each file with a mark has a twin without one. Read from the init event: the agent is listed
    under its frontmatter `name` (not its file name); a skill with `user-invocable: false` is
    left out of the session's skills (the field was read). From the InstructionsLoaded hook: the
    rule with `paths:` loads on reading a matching file, never at session start. From the
    model's reply: the skill's description as the listing gives it (the model's own account)."""
    repo = git_init(ctx.tmp / "shop-repo")
    command, log = hook_logger(ctx, repo)
    write(repo / ".claude" / "settings.json", json.dumps({"hooks": {"InstructionsLoaded": [
        {"hooks": [{"type": "command", "command": command("loads")}]}]}}))
    write(repo / "CLAUDE.md", "# shop-api\n\nRun `make test` before any change.\n")
    skill = repo / ".claude" / "skills"
    write(skill / "shop-refunds" / "SKILL.md", BOM + "---\nname: shop-refunds\ndescription: "
          "Handle refund requests in the shop checkout. Marker kestrel-41.\n---\n\n"
          "Body marker heron-77.\n")
    write(skill / "shop-invoices" / "SKILL.md", "---\nname: shop-invoices\ndescription: "
          "Handle invoices in the shop.\n---\n\nBody.\n")
    write(skill / "shop-coupons" / "SKILL.md", BOM + "---\nname: shop-coupons\ndescription: "
          "Handle shop coupons.\nuser-invocable: false\n---\n\nBody.\n")
    write(skill / "shop-discounts" / "SKILL.md", "---\nname: shop-discounts\ndescription: "
          "Handle shop discounts.\nuser-invocable: false\n---\n\nBody.\n")
    agents = repo / ".claude" / "agents"
    write(agents / "shop-reviewer.md", BOM + "---\nname: shop-reviewer-bom\ndescription: Review "
          "shop code changes before merge.\n---\n\nReview.\n")
    write(agents / "shop-tester.md", "---\nname: shop-tester-plain\ndescription: Test shop "
          "code.\n---\n\nTest.\n")
    rules = repo / ".claude" / "rules"
    write(rules / "payments.md", BOM + "---\npaths:\n  - \"src/payments/**\"\n---\n\n"
          "Validate amounts.\n")
    write(rules / "web.md", "---\npaths:\n  - \"src/web/**\"\n---\n\nKeep pages small.\n")
    write(rules / "always.md", "Answer in English.\n")
    write(repo / "src" / "payments" / "amount.ts", "export const amount = 1;\n")
    write(repo / "src" / "web" / "page.ts", "export const page = 1;\n")
    events = ctx.ask(repo, "Read the file src/web/page.ts with the Read tool, then read the file "
                           "src/payments/amount.ts with the Read tool. Then, with no other tool "
                           "call, reply with one line: the description of the skill shop-refunds "
                           "exactly as your list of available skills gives it.",
                     "--allowedTools", "Read")
    init = init_event(events)
    skills, agents_seen = set(init.get("skills") or []), set(init.get("agents") or [])
    loads: dict[str, set[str]] = {}
    for line in read_log(log):
        if line.get("hook_event_name") == "InstructionsLoaded":
            loads.setdefault(Path(str(line.get("file_path"))).name, set()).add(
                str(line.get("load_reason")))
    reads = [str(i.get("file_path", "")) for t, i in tool_uses(events) if t == "Read"]
    if not any(r.endswith("amount.ts") for r in reads) or "always.md" not in loads:
        raise ProbeError(f"the model read {reads}; rules logged {sorted(loads)}")
    if "shop-invoices" not in skills or "shop-discounts" in skills \
            or "shop-tester-plain" not in agents_seen or "path_glob_match" not in loads.get("web.md", ()):
        raise ProbeError("a control without a mark did not behave as expected: "
                         f"skills {sorted(s for s in skills if s.startswith('shop'))}, agents "
                         f"{sorted(a for a in agents_seen if a.startswith('shop'))}, web.md {loads.get('web.md')}")
    skill_read = any("SKILL.md" in str(i) for _t, i in tool_uses(events))
    reply = final_text(events)
    checks = {
        "skill listed": "shop-refunds" in skills,
        "skill field read (user-invocable: false hides it)": "shop-coupons" not in skills,
        "agent under its frontmatter name": "shop-reviewer-bom" in agents_seen,
        "rule paths read (loads on match only)": loads.get("payments.md") == {"path_glob_match"},
        "description quoted": "kestrel-41" in reply and "heron-77" not in reply
                              and "name:" not in reply and not skill_read,
    }
    facts = "; ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in checks.items()) \
        + f"; payments.md load reasons {sorted(loads.get('payments.md', ()))}"
    return ("PASS" if all(checks.values()) else "FAIL"), facts


def probe_skill_hooks_empty(ctx: Context) -> Verdict:
    """35-hooks-shape: a skill whose frontmatter holds `hooks: []` is listed and can be invoked."""
    repo = git_init(ctx.tmp / "shop-repo")
    write(repo / ".claude" / "skills" / "shop-orders" / "SKILL.md",
          "---\nname: shop-orders\ndescription: Handle shop orders.\nhooks: []\n---\n\n"
          "When this skill is invoked, reply with the word plover-12 and nothing else.\n")
    write(repo / ".claude" / "skills" / "shop-carts" / "SKILL.md",
          "---\nname: shop-carts\ndescription: Handle shop carts.\n---\n\nBody.\n")
    events = ctx.ask(repo, "Call the Skill tool with the skill shop-orders, follow what it says, "
                           "and reply with what it tells you to reply.", "--allowedTools", "Skill")
    skills = set(init_event(events).get("skills") or [])
    if "shop-carts" not in skills:
        raise ProbeError(f"the control skill is not listed: {sorted(skills)}")
    called = any(t == "Skill" and "shop-orders" in json.dumps(i) for t, i in tool_uses(events))
    errors = [text for err, text in tool_results(events) if err]
    listed = "shop-orders" in skills
    body = "plover-12" in final_text(events)
    facts = (f"listed: {'yes' if listed else 'NO'}; Skill call: {'yes' if called else 'no'}; "
             f"tool errors: {len(errors)}; body followed: {'yes' if body else 'no'}")
    if listed and called and not errors and body:
        return "PASS", facts
    if listed and not called:
        raise ProbeError(facts + " - the model did not call the skill")
    return "FAIL", facts


# The `@path` forms of 01-claude-md-import-syntax: (label, text written in CLAUDE.md, the file
# whose InstructionsLoaded event means "imported"). Each target is its own file under docs/,
# so one event names one form. `True`/`False` is what 2.1.302 did (evidence.json).
IMPORT_FORMS: tuple[tuple[str, str, str, bool], ...] = (
    ("space after", "See @docs/space.md for the shop.", "docs/space.md", True),
    ("end of line", "Line end: @docs/eol.md", "docs/eol.md", True),
    ("colon after", "Colon: @docs/colon.md: then text.", "docs/colon.md", False),
    ("colon after, file named with the colon", "Named colon: @docs/colonfile.md: then text.",
     "docs/colonfile.md:", False),
    ("comma after", "Comma: @docs/comma.md, then text.", "docs/comma.md", False),
    ("comma after, file named with the comma", "Named comma: @docs/commafile.md, then text.",
     "docs/commafile.md,", False),
    ("period after", "Period: @docs/period.md. Then text.", "docs/period.md", False),
    ("double quote after", 'Quote after: @docs/dqafter.md" then text.', "docs/dqafter.md", False),
    ("semicolon after", "Semicolon: @docs/semi.md; then text.", "docs/semi.md", False),
    ("exclamation after", "Bang: @docs/bang.md! Then text.", "docs/bang.md", False),
    ("question mark after", "Question: @docs/quest.md? Then text.", "docs/quest.md", False),
    ("closing parenthesis after", "Paren after: @docs/pafter.md) then text.", "docs/pafter.md",
     False),
    ("opening parenthesis before", "Paren before: (@docs/pbefore.md then text.",
     "docs/pbefore.md", False),
    ("double quote before", 'Quote before: "@docs/dqbefore.md then text.', "docs/dqbefore.md",
     False),
    ("wrapped in double quotes", 'Wrapped: "@docs/wrapped.md" then text.', "docs/wrapped.md",
     False),
    ("single quote before", "Single quote before: '@docs/sqbefore.md then text.",
     "docs/sqbefore.md", False),
    ("lone backtick before", "Lone backtick before: `@docs/tickbefore.md then text.",
     "docs/tickbefore.md", False),
    ("word character before", "Word before: shop@docs/wordbefore.md then text.",
     "docs/wordbefore.md", False),
    ("code span", "Code span: `@docs/span.md` then text.", "docs/span.md", False),
    ("fenced block", "```\n@docs/fence.md\n```", "docs/fence.md", False),
    ("./ prefix", "Dot slash: @./docs/dotrel.md then text.", "docs/dotrel.md", True),
    ("trailing slash after a file", "Slash after: @docs/slash.md/ then text.", "docs/slash.md",
     True),
    ("trailing slash on a folder", "Folder: @docs/folder/ then text.", "docs/folder/inner.md",
     False),
    ("no extension", "No extension: @docs/NOTES then text.", "docs/NOTES", True),
    ("end of file, no newline", "Last: @docs/eof.md", "docs/eof.md", True),
)
# Windows refuses these characters in a file name, and a name ending with a period or a space
# (Microsoft, "Naming Files, Paths, and Namespaces"): `docs/colonfile.md:` cannot be created
# there - open() raised OSError [Errno 22] and the probe ended in ERROR (external audit of
# 0.27.0, D-03, emulated). Such a form is left out where its file cannot exist, and said so; the
# auditor's reading of it is tested on the string, with no file (tests/test_probes.py).
WINDOWS_RESERVED = '<>:"|?*'
IS_WINDOWS = os.name == "nt"


def creatable(rel: str, windows: bool | None = None) -> bool:
    """False for a relative path this system cannot create (Windows only: reserved characters,
    or a part ending with a period or a space)."""
    if not (IS_WINDOWS if windows is None else windows):
        return True
    return not any(c in WINDOWS_RESERVED for c in rel) and not any(
        part.endswith((".", " ")) for part in rel.split("/"))


def import_forms(windows: bool | None = None) -> tuple[tuple[str, str, str, bool], ...]:
    """IMPORT_FORMS whose file this system can create."""
    return tuple(f for f in IMPORT_FORMS if creatable(f[2], windows))


# The nested chain: CLAUDE.md -> docs/h1.md -> h2 -> ... -> h6, each import relative to the
# importing file (`@h2.md` inside docs/h1.md). docs/h1.md also imports `@docs/rootrel.md`,
# which exists only relative to the repository root.
IMPORT_CHAIN: dict[str, bool] = {"docs/h1.md": True, "docs/h2.md": True, "docs/h3.md": True,
                                 "docs/h4.md": True, "docs/h5.md": False, "docs/h6.md": False,
                                 "docs/rootrel.md": False}


def import_syntax_project(ctx: Context) -> tuple[Path, Path]:
    """The probe repository of 01-claude-md-import-syntax and its InstructionsLoaded log."""
    repo = git_init(ctx.tmp / "shop-repo")
    command, log = hook_logger(ctx, repo)
    write(repo / ".claude" / "settings.json", json.dumps({"hooks": {"InstructionsLoaded": [
        {"hooks": [{"type": "command", "command": command("loads")}]}]}}))
    lines = ["# shop-api", "", "Chain: @docs/h1.md then text.", ""]
    for _label, text, target, _loaded in import_forms():
        write(repo / target, f"# {target}\n")
        lines += [text, ""]
    write(repo / "docs" / "h1.md", "# h1\n\nNext: @h2.md then text.\n\nRoot: @docs/rootrel.md then text.\n")
    for n in range(2, 7):
        write(repo / "docs" / f"h{n}.md", f"# h{n}\n" + (f"\nNext: @h{n + 1}.md then text.\n" if n < 6 else ""))
    write(repo / "docs" / "rootrel.md", "# docs/rootrel.md\n")
    # The last form is at the end of the file, with no newline after it.
    (repo / "CLAUDE.md").write_text("\n".join(lines).rstrip("\n"), encoding="utf-8")
    return repo, log


def probe_import_syntax(ctx: Context) -> Verdict:
    """01-claude-md-import-syntax: which `@path` spellings of a CLAUDE.md load the file they name.

    Read from an InstructionsLoaded hook: one event per file loaded, with its path."""
    repo, log = import_syntax_project(ctx)
    ctx.ask(repo, "Reply with the single word OK.")
    loaded = set()
    for line in read_log(log):
        if line.get("hook_event_name") == "InstructionsLoaded":
            try:
                loaded.add(Path(str(line.get("file_path"))).resolve().relative_to(
                    repo.resolve()).as_posix())
            except ValueError:
                continue
    if "CLAUDE.md" not in loaded:
        raise ProbeError(f"CLAUDE.md itself did not load: {sorted(loaded)}")
    forms = import_forms()
    observed = {label: target in loaded for label, _t, target, _l in forms}
    observed.update({f"chain {t}": t in loaded for t in IMPORT_CHAIN})
    expected = {label: want for label, _t, _target, want in forms}
    expected.update({f"chain {t}": want for t, want in IMPORT_CHAIN.items()})
    differ = [f"{k}: {'loaded' if observed[k] else 'not loaded'}" for k in expected
              if observed[k] != expected[k]]
    if differ:
        return "FAIL", "differs from the record: " + "; ".join(differ)
    left_out = [f[0] for f in IMPORT_FORMS if f not in forms]
    return "PASS", (f"{sum(observed.values())} of {len(observed)} named files loaded, "
                    "as recorded" + (f"; left out, no such file on this system: {', '.join(left_out)}"
                                     if left_out else ""))


@dataclass(frozen=True)
class Probe:
    check: str          # key under "checks" in evidence.json
    entry: str          # the `tested*` entry it replays
    model: bool         # True: billed `claude -p` runs
    runs: int           # claude invocations
    func: Callable[[Context], Verdict]
    scope: str = ""     # what of the recorded method is replayed, when not all of it


PROBES: tuple[Probe, ...] = (
    Probe("44-plugin-path", "tested", False, 4, probe_plugin_path),
    Probe("43-mcp-shape", "tested", False, 1, probe_mcp_sdk),
    Probe("35-hooks-shape", "tested", True, 2, probe_onfailure_block),
    Probe("23-agent-tools", "tested_taskoutput", True, 1, probe_taskoutput_agent,
          "the `tools: TaskOutput` agent only; the two others are judged on the model's report"),
    Probe("42-permissions-rule", "tested_mid_colon_star", True, 2, probe_colon_star,
          "`git status` against Bash(git:* status) and the control; not `git -C`, not echo:*"),
    Probe("35-hooks-matcher", "tested", True, 2, probe_matcher_alternatives),
    Probe("frontmatter-bom", "tested", True, 1, probe_bom_frontmatter),
    Probe("35-hooks-shape", "tested_skill_hooks_empty", True, 1, probe_skill_hooks_empty),
    Probe("01-claude-md-import-syntax", "tested", True, 1, probe_import_syntax),
)

# Recorded tests left out, and why. Each key is an evidence.json entry.
NOT_IMPLEMENTED: dict[tuple[str, str], str] = {
    ("01-claude-md-case", "tested"): "the verdict is the model recalling a codeword, Linux only",
    ("23-agent-tools", "tested"): "the method does not record the prompt or the settings layout",
    ("43-mcp-credential-var", "tested"): "needs credential-named variables and a header-logging "
                                         "server; this script does not handle credentials",
    ("42-permissions-rule", "tested"): "the prompt and the pass signal of a delegation are not "
                                       "recorded precisely enough",
    ("42-permissions-rule", "tested_home_variable"): "moves HOME, which hides the login the "
                                                     "binary needs",
    ("manual-rule-guards-creation", "tested"): "part of the result is the model's own account",
}


# ---------- running ----------

def claude_version(claude: str) -> str:
    try:
        done = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL)
        return done.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def recorded(evidence: dict, probe: Probe) -> str:
    entry = evidence.get("checks", {}).get(probe.check, {}).get(probe.entry, {})
    return entry.get("claude_code", "?")


def run_one(probe: Probe, claude: str, isolate: bool, runs: list[str],
            keep: bool = False) -> Verdict:
    tmp = Path(tempfile.mkdtemp(prefix="deadweight-probe-"))
    try:
        return probe.func(Context(claude, tmp, isolate, runs, limit=probe.runs))
    except ProbeError as error:
        return "ERROR", str(error)
    except subprocess.TimeoutExpired:
        return "ERROR", f"timed out after {TIMEOUT}s: no evidence either way"
    except (OSError, subprocess.SubprocessError) as error:
        return "ERROR", f"could not run: {type(error).__name__}: {error}"
    finally:
        if keep:
            print(f"      kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--claude", default=None, help="the binary (default: `claude` on PATH)")
    p.add_argument("--only", action="append", default=[], metavar="CHECK",
                   help="run only the probes of this check id (repeatable)")
    p.add_argument("--no-model", action="store_true", help="skip the billed `claude -p` probes")
    p.add_argument("--isolate-config", action="store_true",
                   help="a temporary CLAUDE_CONFIG_DIR for model probes too")
    p.add_argument("--list", action="store_true", help="list the probes, run nothing")
    p.add_argument("--keep", action="store_true",
                   help="keep each temporary folder (streams in probe-stream.jsonl) and print it")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    unknown = sorted(set(args.only) - {p.check for p in PROBES})
    if unknown:
        print(f"--only: no probe for {', '.join(unknown)}; probes: "
              + ", ".join(sorted({p.check for p in PROBES})), file=sys.stderr)
        return 2
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    claude = args.claude or shutil.which("claude")
    if claude and not Path(claude).exists() and not shutil.which(claude):
        claude = None
    version = claude_version(claude) if claude and not args.list else "not run"
    print(f"claude --version: {version if claude else 'claude not found'}")
    failed = 0
    runs: list[str] = []
    for probe in PROBES:
        label = f"{probe.check} ({probe.entry}, recorded on {recorded(evidence, probe)})"
        if args.list:
            verdict, detail = "LIST", f"{probe.runs} run(s), " + ("model" if probe.model else "local")
        elif args.only and probe.check not in args.only:
            continue
        elif not claude:
            verdict, detail = "SKIP", "claude not found"
        elif probe.model and args.no_model:
            verdict, detail = "SKIP", "--no-model"
        else:
            verdict, detail = run_one(probe, claude, args.isolate_config, runs, args.keep)
        failed += verdict in ("FAIL", "ERROR")
        print(f"{verdict:5} {label}: {detail}" + (f" [scope: {probe.scope}]" if probe.scope else ""))
    print("\nNot implemented:")
    for (check, entry), why in NOT_IMPLEMENTED.items():
        print(f"  {check} ({entry}): {why}")
    if runs:
        model_runs = sum(r.startswith("model") for r in runs)
        print(f"\nclaude invocations: {len(runs)}, of which billed model runs: {model_runs}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
