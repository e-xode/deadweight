"""Command line: arguments, the passes over a dual-role repository, output."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .catalog import CHECKS
from .context import AuditContext
from .floor import check_floor, set_floor
from .identity import audit_sha
from .layout import (
    LIBRARY_MIN_SKILLS,
    apply_layout,
    detect_layout,
    has_project_config,
    root_level_skills,
)
from .overlay import apply_overlay, apply_thresholds, load_local_config
from .registry import PROJECT_ONLY, run_checks
from .repo import tracked_paths
from .report import ROLLUP_AFTER, Report, print_text_report


def main(argv: list[str]) -> int:
    # Windows writes a piped stdout in the ANSI code page (cp1252), which has no
    # `➜` a finding may quote from an audited file: the first one raised UnicodeEncodeError and the text report died on it. Measured on a
    # Windows runner, 2026-09-24. Every reader of this output - the host, an agent's
    # shell tool, a modern terminal - decodes UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Audit Claude configuration.")
    parser.add_argument("--root", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--all", action="store_true",
                        help="Show every finding; by default a check that fires more than "
                             f"{ROLLUP_AFTER} times is rolled up")
    parser.add_argument(
        "--layout",
        choices=("auto", "project", "plugin", "library", "none"),
        default="auto",
        help="Container being audited (default: auto, from .claude-plugin/plugin.json)",
    )
    parser.add_argument(
        "--set-floor",
        action="store_true",
        help="Freeze the current counts in .claude/audit/floor.json as the ratchet",
    )
    parser.add_argument(
        "--check-floor",
        action="store_true",
        help="Fail when the counts rose above the recorded floor (for CI)",
    )
    parser.add_argument(
        "--runtime",
        metavar="LOG",
        help="An InstructionsLoaded log (JSONL) to compare with the files: what never loaded, "
             "what loaded unscoped. See references/runtime-data.md",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    layout = detect_layout(root) if args.layout == "auto" else args.layout
    # A repository that ships a plugin or a marketplace AND is itself worked on with
    # Claude Code is both. Detection answered one role, and the project it also is went
    # unaudited: 11 of 13 non-project repositories in a 150-repository sample
    # (2026-09-27), 43 skills never read, and a message saying "a plugin has no CLAUDE.md"
    # beside the one it had.
    dual = args.layout == "auto" and layout in ("plugin", "marketplace") and has_project_config(root)
    ctx = AuditContext(root=root, runtime=Path(args.runtime).resolve() if args.runtime else None)
    ctx.dual_library = (args.layout == "auto" and layout == "project"
                        and len(root_level_skills(root)) >= LIBRARY_MIN_SKILLS)
    apply_layout(ctx, layout)

    ctx.local = load_local_config(root)
    ctx.profile = "house" if str(ctx.local.get("profile", "")).strip().lower() == "house" else "doc"
    report = Report()
    # Before any check runs: a moved threshold must move for EVERY check that
    # reads it, not only for the ones that happen to run afterwards.
    apply_thresholds(ctx, report)
    detail = {
        "library": "skills kept at the repository root, no project and no manifest: "
                   "their content is audited, and where they would load is said.",
        "none": "no Claude Code configuration here - no CLAUDE.md, no .claude/, no "
                "skills/, no manifest. Nothing to audit, and nothing is missing.",
    }
    if layout in detail:
        msg = f"Layout `{layout}`{'' if args.layout != 'auto' else ' (detected)'}: {detail[layout]}"
    else:
        msg = (f"Layout `{layout}`{'' if args.layout != 'auto' else ' (detected)'}: "
               f"skills at `{ctx.skills_dir}/`, agents at `{ctx.agents_dir}/`."
               + ("" if layout == "project" else
                  f" {len(PROJECT_ONLY)} project-only check(s) skipped - a plugin has no "
                  "CLAUDE.md, settings, rules or skills index.")
               + (" No manifest: the plugin is named after its folder, which the manifest "
                  "is optional for." if layout == "plugin"
                  and not (root / ".claude-plugin" / "plugin.json").is_file() else ""))
    if layout == "none":
        # "Nothing to audit, and nothing is missing" was said beside a `symfony/CLAUDE.md`:
        # a subdirectory's CLAUDE.md "loads on demand when Claude reads files in those
        # directories" (memory). 1 of 2 `none` repositories on a public sample, 2026-09-27.
        nested = sorted(t for t in tracked_paths(root)
                           if t.endswith("/CLAUDE.md") and "node_modules/" not in t)
        if nested:
            shown = ", ".join(nested[:5]) + (f" (+{len(nested) - 5})" if len(nested) > 5 else "")
            msg = (f"Layout `none`{'' if args.layout != 'auto' else ' (detected)'}: no configuration "
                   f"at the root, but {len(nested)} CLAUDE.md in subdirectories, loaded when "
                   f"Claude reads a file there (memory): {shown}. Audit each with --root <its directory>.")
    if dual:
        msg = (f"Layout `{layout}` (detected), and a project as well: this repository also carries "
               "a CLAUDE.md or a .claude/ configuration, so it is audited twice - as a "
               f"{layout} (skills at `{ctx.skills_dir}/`) and as a project (`.claude/`).")
    if ctx.dual_library:
        msg += (f" It is also a skills library: {len(root_level_skills(root))} skill(s) at the "
                "root, audited as one in a second pass.")
    report.add("00-layout", "INFO", msg, str(root))

    run_checks(ctx, report)
    if ctx.dual_library:
        apply_layout(ctx, "library")
        run_checks(ctx, report)
        apply_layout(ctx, layout)
        report.findings = list({(f.check, f.severity, f.message, f.location): f
                                for f in report.findings}.values())
    if dual:
        # Second pass, same report: the project this repository also is. Checks that
        # do not depend on the layout run twice and say the same thing twice - kept once.
        apply_layout(ctx, "project")
        run_checks(ctx, report)
        apply_layout(ctx, layout)
        report.findings = list({(f.check, f.severity, f.message, f.location): f
                                for f in report.findings}.values())

    apply_overlay(ctx, report, ctx.local)
    floor_rc = check_floor(root, report) if args.check_floor else 0

    if args.json:
        out = {
            "checks_executed": len(CHECKS),
            "layout": layout,
            "audit_sha": audit_sha(),
            "counts": report.counts(),
            "findings": [asdict(f) for f in report.findings],
        }
        print(json.dumps(out, indent=2))
    else:
        print_text_report(report, show_all=args.all, profile=ctx.profile)

    if args.set_floor:
        written = set_floor(root, report, layout)
        print(f"\nFloor set in {written}" if written
              else "\nCould not write the floor (unwritable path).", file=sys.stderr)

    return 1 if (report.has_errors() or floor_rc) else 0
