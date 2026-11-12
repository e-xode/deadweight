"""Portability smoke test: the three things a user runs, on the OS the runner provides.

The plugin's only dependency is Python, but its hook ran through bash and GNU
coreutils until 0.14.1, and failed on every macOS session with its errors discarded.
No check caught it because every check ran on Linux. This one runs the pieces the
way the harness does - `deadweight --setup-statusline`, the hook command it writes
into the project's settings, `deadweight --fresh`, the status line fed a JSON payload -
on a throwaway project, and fails on the first piece that does not produce what the
next one reads. Since 0.34.0 the plugin declares no hook (the plugin directory refuses
a hook of type `command` from an unverified organization): the hook lives in the
project's settings, written by the setup, so that is the command tested here.

    python3 .github/smoke/portability.py [plugin_root]
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]).resolve()


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    work = Path(tempfile.mkdtemp())
    project = work / "shop-api"
    (project / ".git").mkdir(parents=True)
    (project / "CLAUDE.md").write_text("# shop-api\n\nRun `make test` before any change.\n", encoding="utf-8")
    cache_home = work / "cache"
    # A Claude Code home that knows where the plugin is installed, as the launcher looks it up;
    # no Copilot home, so the setup writes only the Claude Code side. No CLAUDE_PLUGIN_ROOT: a hook
    # in a project's settings does not get one.
    claude_home = work / "claude"
    (claude_home / "plugins").mkdir(parents=True)
    (claude_home / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {"deadweight@e-xode": [{"scope": "user", "installPath": str(PLUGIN)}]}}), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    env.update(CLAUDE_PROJECT_DIR=str(project), XDG_CACHE_HOME=str(cache_home),
               CLAUDE_CONFIG_DIR=str(claude_home), COPILOT_HOME=str(work / "no-copilot"))

    # 0. The setup, which writes the status line, its launcher and the hook into the project.
    setup = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "deadweight"), "--setup-statusline"], env=env,
                           cwd=project, capture_output=True, text=True, timeout=60)
    print(f"deadweight --setup-statusline: exit {setup.returncode}")
    if setup.returncode != 0:
        fail(f"the setup failed: {setup.stdout[:300]} {setup.stderr[:300]}")
    settings = json.loads((project / ".claude" / "settings.json").read_text(encoding="utf-8"))

    # 1. The hook, through the exact command the setup wrote, in a shell.
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    # The shell the harness uses. On Windows that is Git Bash (CLAUDE_CODE_GIT_BASH_PATH, or
    # the first bash on PATH), not the WSL launcher that CreateProcess finds in System32
    # BEFORE the PATH - which a bare "bash" here resolved to, and which fails on a
    # machine with no WSL distribution for a reason that says nothing about the plugin.
    bash = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH") or shutil.which("bash") or "bash"
    run = subprocess.run([bash, "-c", command], env=env, capture_output=True, text=True, timeout=60)
    print(f"hook: {command}\n  exit {run.returncode}, stdout {len(run.stdout)} chars, stderr: {run.stderr.strip()[:300]}")
    if run.stdout.strip():
        fail(f"the hook printed to stdout, which a SessionStart hook pays in context:\n{run.stdout.strip()[:600]}")
    key = f"shop-api-{hashlib.md5(str(project).encode()).hexdigest()[:8]}.json"
    cached = cache_home / "claude-audit" / key
    found = sorted(p.name for p in (cache_home / "claude-audit").glob("*")) if (cache_home / "claude-audit").is_dir() else []
    if not cached.is_file():
        fail(f"no cache at {key}; the cache holds {found}")
    sha = json.loads(cached.read_text(encoding="utf-8")).get("audit_sha")
    # The identity normalises line endings, and .gitattributes checks out LF: two defences,
    # this one says whether the first is still needed on this runner.
    scripts = PLUGIN / "skills" / "config-auditor" / "scripts"
    crlf = [f.name for f in [scripts / "audit.py", *sorted((scripts / "deadweight_audit").rglob("*.py"))]
            if b"\r\n" in f.read_bytes()]
    print(f"  cache: {key}, audit_sha {sha}, auditor files with CRLF: {crlf or 'none'}")
    if crlf:
        fail(f"the auditor was checked out with CRLF ({', '.join(crlf[:5])}): .gitattributes no longer "
             "holds, and only the identity's normalisation keeps floors comparable across machines")

    # 2. The command a user runs to see the detail and to measure again.
    fresh = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "deadweight"), "--fresh"], env=env,
                           cwd=project, capture_output=True, text=True, timeout=60)
    print(f"deadweight --fresh: exit {fresh.returncode}\n  {fresh.stdout.strip().splitlines()[0] if fresh.stdout.strip() else '(nothing)'}")
    if fresh.returncode != 0 or "shop-api" not in fresh.stdout:
        fail(f"deadweight --fresh did not show the project: {fresh.stdout[:300]} {fresh.stderr[:300]}")

    # 3. The status line, fed the payload the host sends.
    line = subprocess.run([sys.executable, str(PLUGIN / "skills" / "config-auditor" / "templates" / "statusline.py")],
                          input=json.dumps({"cwd": str(project)}), env=env, capture_output=True, text=True, timeout=30)
    print(f"status line: {line.stdout!r}")
    if "deadweight" not in line.stdout:
        fail(f"the status line printed nothing for a project that was just measured; stderr: {line.stderr.strip()[-600:]}")

    shutil.rmtree(work, ignore_errors=True)
    print("OK")


if __name__ == "__main__":
    main()
