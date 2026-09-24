#!/usr/bin/env python3
"""Portability smoke test: the three things a user runs, on the OS the runner provides.

The plugin's only dependency is Python, but its hook ran through bash and GNU
coreutils until 0.14.1, and failed on every macOS session with its errors discarded.
No check caught it because every check ran on Linux. This one runs the pieces the
way the harness does - the hook command from hooks.json, `deadweight --fresh`, the
status line fed a JSON payload - on a throwaway project, and fails on the first
piece that does not produce what the next one reads.

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
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project), CLAUDE_PLUGIN_ROOT=str(PLUGIN),
               XDG_CACHE_HOME=str(cache_home))

    # 1. The hook, through the exact command the harness runs, in a shell.
    command = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = command["hooks"]["SessionStart"][0]["hooks"][0]["command"]
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
    crlf = b"\r\n" in (PLUGIN / "skills" / "config-auditor" / "scripts" / "audit.py").read_bytes()
    print(f"  cache: {key}, audit_sha {sha}, audit.py has CRLF: {crlf}")
    if crlf:
        fail("audit.py was checked out with CRLF: its sha differs from the one Linux and macOS "
             "compute, and a floor set on one machine refuses to compare on another")

    # 2. The command a user runs to see the detail and to measure again.
    fresh = subprocess.run([sys.executable, str(PLUGIN / "bin" / "deadweight"), "--fresh"], env=env,
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
