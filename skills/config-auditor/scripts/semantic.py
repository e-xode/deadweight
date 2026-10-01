#!/usr/bin/env python3
"""What a reader sees and a parser does not: contradictions and duplicates, read by a model.

    python3 semantic.py                                   # contradictions + duplicates between files
    python3 semantic.py --also internal-duplicates,untestable
    python3 semantic.py --json --model claude-sonnet-5-5 --max-requests 40

A separate command, not an option of audit.py: its findings come from a model and two runs agree
on about three in four, so they are never counted and never reach a floor - and the auditor that
counts (audit.py and deadweight_audit/) is not touched by it, so its sha, and every floor taken
with it, stays as it is. See references/semantic-layer.md, which also says what is sent where.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deadweight_audit.context import AuditContext  # noqa: E402
from deadweight_audit.layout import apply_layout, detect_layout  # noqa: E402
from deadweight_semantic import transport  # noqa: E402
from deadweight_semantic.families import ON_REQUEST  # noqa: E402
from deadweight_semantic.run import run_semantic  # noqa: E402


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Contradictions and duplicates a reader sees, read by a model.")
    parser.add_argument("--root", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--model", default="claude-sonnet-5-5",
                        help="Pinned model id (default: claude-sonnet-5-5); aliases are refused")
    parser.add_argument("--also", default="", metavar="LIST",
                        help="Also report (comma-separated): " + ", ".join(ON_REQUEST))
    parser.add_argument("--max-requests", type=int, default=100, metavar="N",
                        help="Upper bound on requests (default: 100)")
    args = parser.parse_args(argv)
    if args.model in transport.ALIASES:
        print(f"--model {args.model} is an alias: give a model id (claude-sonnet-5-5, ...). "
              "An alias changes target between releases.", file=sys.stderr)
        return 2
    also = tuple(x.strip() for x in args.also.split(",") if x.strip())
    unknown = [x for x in also if x not in ON_REQUEST]
    if unknown:
        print(f"--also: unknown {', '.join(unknown)}; known: {', '.join(ON_REQUEST)}", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    ctx = AuditContext(root=root)
    apply_layout(ctx, detect_layout(root))
    result = run_semantic(ctx, args.model, args.max_requests, also)
    if args.json:
        print(json.dumps(result.as_json(), indent=2, ensure_ascii=False))
    else:
        print(result.render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
