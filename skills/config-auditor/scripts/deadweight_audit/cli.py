"""Command line: arguments, the passes over a dual-role repository, output."""
from __future__ import annotations

import argparse
import json
import os
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
    # A missing or non-directory root raised FileNotFoundError / NotADirectoryError with a
    # traceback (user report on 0.23.0, 2026-10-09): one line, and a non-zero exit.
    if not root.is_dir():
        what = "is not a directory" if root.exists() else "does not exist"
        print(f"audit.py: --root {args.root} {what}; give the root of a project or plugin.",
              file=sys.stderr)
        return 2
    # The user configuration directory (`CLAUDE_CONFIG_DIR`, else ~/.claude) and anything
    # under it is USER scope. Audited as a project it read "nothing to audit" beside a
    # settings.json, or advised that skills in ~/.claude/skills "load nowhere" - they load
    # in every project (user report on 0.23.0, 2026-10-09). This auditor checks
    # projects and plugins only, and says so instead of reporting. An installed plugin
    # (`plugins/` below that directory) is a plugin, and stays audited. A `--layout` given
    # explicitly is honoured there: the user asked for that reading (personal skills checked
    # as a library lost a true 04 description-length WARN, external audit of 0.24.0, cl-00).
    user_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser().resolve()
    user_scope = ((root == user_dir or user_dir in root.parents)
                  and not (root == user_dir / "plugins" or user_dir / "plugins" in root.parents))
    layout = detect_layout(root) if args.layout == "auto" else args.layout
    user_forced = user_scope and args.layout != "auto"
    user_scope = user_scope and not user_forced
    if user_scope:
        layout = "none"
    # The home directory is not a project: ~/.claude holds USER-scope configuration, and the
    # project rules applied to it gave 8 errors and 6 warnings on one machine, such as
    # `defaultMode` "ignored at project scope" in user settings, where it is honoured
    # (reported from anthropics/claude-code#93109, 2026-10-08). Said, not guessed at.
    home = args.layout == "auto" and root == Path.home().resolve()
    if home:
        layout = "none"
    # A repository that ships a plugin or a marketplace AND is itself worked on with
    # Claude Code is both. Detection answered one role, and the project it also is went
    # unaudited: 11 of 13 non-project repositories in a 150-repository sample
    # (2026-09-27), 43 skills never read, and a message saying "a plugin has no CLAUDE.md"
    # beside the one it had.
    dual = args.layout == "auto" and layout in ("plugin", "marketplace") and has_project_config(root)
    ctx = AuditContext(root=root, runtime=Path(args.runtime).resolve() if args.runtime else None)
    ctx.dual_library = (args.layout == "auto" and layout == "project" and not user_scope
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
    if layout == "none" and (root / ".mcp.json").is_file():
        # Project-scoped MCP servers live in a root `.mcp.json` (mcp, Project scope): check
        # 43 reads it whatever the layout, so "nothing to audit" would be false here. Auto
        # detection classes such a repository `project`; only a forced `none` lands here,
        # and there check_security does not run: "are audited" read as a clean security
        # pass on an unpinned npx server (external audit 3, g8-04).
        detail["none"] = ("no CLAUDE.md, no .claude/, no skills/, no manifest - only a "
                          ".mcp.json. Its servers' definitions are checked (43-mcp-*), not "
                          "their security (50-security-mcp-*): drop `--layout none` for that.")
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
    if user_scope:
        msg = (f"Layout `none`: {root} is in your user configuration directory ({user_dir}), "
               "which holds USER-scope configuration (settings, agents, skills, hooks) whose rules "
               "differ from a project's. This auditor checks project and plugin configuration "
               "only, so nothing here is audited. To audit a project, run it from the project's root; "
               "to check these files anyway, pass a layout explicitly (`--layout library` for "
               "skills), knowing that some findings assume project scope.")
    elif home:
        msg = ("Layout `none` (detected): this is your home directory. `~/.claude` holds USER-scope "
               "configuration (settings, agents, skills), whose rules differ from a project's: this "
               "auditor checks project and plugin configuration only, so nothing here is audited. "
               "To audit a project, run it from the project's root.")
    elif layout == "none":
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
    if user_forced:
        msg += (f" {root} is in your user configuration directory ({user_dir}): the layout was "
                "requested explicitly, so it is audited as asked, but USER-scope rules differ from "
                "a project's - a finding about where a file loads, or about a setting's scope, may "
                "not apply here.")
    if ctx.dual_library:
        msg += (f" It is also a skills library: {len(root_level_skills(root))} skill(s) at the "
                "root, audited as one in a second pass.")
    report.add("00-layout", "INFO", msg, str(root))

    if not user_scope:
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

    if args.set_floor and user_scope:
        print("\nNo floor set: user-scope configuration is not audited.", file=sys.stderr)
    elif args.set_floor:
        written = set_floor(root, report, layout)
        print(f"\nFloor set in {written}" if written
              else "\nCould not write the floor (unwritable path).", file=sys.stderr)

    return 1 if (report.has_errors() or floor_rc) else 0
