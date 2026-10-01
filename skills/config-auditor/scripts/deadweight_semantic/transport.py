"""How a request reaches a model: `claude -p` in a minimal context, with a pinned model.

No API key and no dependency: the user's own Claude Code session answers, with no tools, no MCP
server and no settings - the files in the prompt are all it sees. A model id, never an alias:
`sonnet` changed target between two Claude Code releases (2.1.284, 2026-09-29) and with it what
was measured. Set DEADWEIGHT_SEMANTIC_RESPONSE to a file to replay a fixed answer offline (tests).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass

ALIASES = ("sonnet", "opus", "haiku", "fable", "default", "best")
RETRIES = 3
RETRY_WAIT = 20          # seconds: an npm reinstall of Claude Code takes about that long


@dataclass
class Answer:
    text: str
    cost_usd: float
    model_served: str
    error: str = ""


def ask(system: str, prompt: str, model: str, timeout: int = 600) -> Answer:
    replay = os.environ.get("DEADWEIGHT_SEMANTIC_RESPONSE")
    if replay:
        with open(replay, encoding="utf-8") as f:
            return Answer(f.read(), 0.0, f"replay:{os.path.basename(replay)}")
    cmd = ["claude", "-p", "--model", model, "--system-prompt", system, "--tools", "",
           "--strict-mcp-config", "--setting-sources", "", "--output-format", "json"]
    # The prompt goes on stdin: a command line is capped at 32,767 characters on Windows.
    # A Claude Code update replaces the `claude` executable in place: for a few seconds it is
    # missing, or half written ("Exec format error"). Measured twice on 2026-10-01: 98 and 173
    # requests lost in one run each. Those two errors are retried; nothing else is.
    for attempt in range(RETRIES + 1):
        try:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8")
            break
        except OSError as exc:
            if attempt == RETRIES or not (isinstance(exc, FileNotFoundError) or exc.errno == 8):
                return Answer("", 0.0, model, f"{type(exc).__name__}: {exc}")
            time.sleep(RETRY_WAIT)
        except subprocess.TimeoutExpired as exc:
            return Answer("", 0.0, model, f"{type(exc).__name__}: {exc}")
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return Answer("", 0.0, model, (r.stderr or r.stdout).strip()[:300] or f"exit {r.returncode}")
    served = ",".join(sorted((d.get("modelUsage") or {}).keys())) or model
    return Answer(str(d.get("result", "")), float(d.get("total_cost_usd") or 0.0), served,
                  "" if not d.get("is_error") else str(d.get("result", ""))[:300])


def harness_version() -> str:
    """The Claude Code release that answers: the same model through another release is another instrument."""
    if os.environ.get("DEADWEIGHT_SEMANTIC_RESPONSE"):
        return "replay"
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True,
                              timeout=60).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
