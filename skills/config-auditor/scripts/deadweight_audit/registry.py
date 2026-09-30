"""Which check runs on which container, and the dispatcher that runs them."""
from __future__ import annotations


from .checks.agents import check_agent_frontmatter_validity, check_agents, check_agents_dir_skills
from .checks.budget import (
    check_always_loaded_budget,
    check_listing_budget_derived,
    check_plugin_cost,
)
from .checks.claude_md import check_claude_md, check_cross_refs, check_skill_index
from .checks.descriptions import check_agent_descriptions, check_description_overlap
from .checks.doctrine import check_doctrine_copy
from .checks.evals import check_eval_quality, check_evals
from .checks.hooks import check_frontmatter_hooks, check_hooks
from .checks.language import check_english_only, check_no_code_comments_in_skills
from .checks.links import (
    check_all_relative_links,
    check_dangling_symlinks,
    check_foreign_skill_mentions,
    check_see_skill_targets,
    check_unreadable,
)
from .checks.mcp import check_mcp
from .checks.other_agents import check_other_tools
from .checks.overlay import check_project_overlay
from .checks.plugin import (
    check_companions,
    check_documented_flags,
    check_plugin_manifest,
    check_plugin_vars_in_project,
)
from .checks.reality import check_repository_reality, check_skill_anchors
from .checks.rules import check_rule_globs, check_rules
from .checks.runtime import check_runtime_loads
from .checks.security import check_security
from .checks.settings import check_settings_scope, check_settings_semantics
from .checks.skills import (
    check_frontmatter_quoting,
    check_no_global_scripts,
    check_orphan_references,
    check_reference_sizes,
    check_skill_names,
    check_skills,
    check_unloadable_skills,
)
from .checks.twins import check_twin_division_tables
from .context import AuditContext
from .report import Report


# Checks whose subject exists only in a project. Named by function, because the
# dispatch in main() reads this tuple: a project-only check added later and not
# listed here runs against a plugin and reports a missing file that cannot exist.
PROJECT_ONLY = (
    "check_other_tools",
    "check_repository_reality",
    "check_agents_dir_skills",
    "check_plugin_vars_in_project",
    "check_claude_md",
    "check_cross_refs",
    "check_no_global_scripts",
    "check_rules",
    "check_rule_globs",
    "check_skill_index",
    "check_settings_scope",
    "check_always_loaded_budget",
    "check_listing_budget_derived",
    "check_settings_semantics",
    "check_companions",
    "check_runtime_loads",
)


PLUGIN_ONLY = ("check_plugin_cost", "check_plugin_manifest")


# The only things worth saying about a marketplace repository: what it is, and
# whether its own catalogue is coherent. Everything else has no subject here.
MARKETPLACE_CHECKS = ("check_skills", "check_agents")   # both were called outside the dispatch until 0.17.0


# A library is skills and nothing else: judge their content, and say where they
# would load. A repository with no Claude configuration gets the second only.
LIBRARY_CHECKS = ("check_skills", "check_skill_names", "check_description_overlap",
                  "check_unloadable_skills")


NONE_CHECKS = ("check_unloadable_skills",)


def run_checks(ctx: AuditContext, report: Report) -> None:
    """Every check, dispatched for one container. Called twice for a dual-role repository."""
    def run(fn, *a):
        """Dispatch, skipping checks whose subject the current container lacks."""
        name = fn.__name__
        layout = ctx.layout
        if layout != "project" and name in PROJECT_ONLY:
            return None
        if layout != "plugin" and name in PLUGIN_ONLY:
            return None
        # A marketplace holds a catalogue. Everything that inspects a configuration -
        # skills, agents, rules, references, budget - has no subject here, and running
        # it reports the auditor's own ignorance as the repository's defect.
        if layout == "marketplace" and name not in MARKETPLACE_CHECKS:
            return None
        if layout == "library" and name not in LIBRARY_CHECKS:
            return None
        if layout == "none" and name not in NONE_CHECKS:
            return None
        # Every check goes through here. Until 2026-09-22 half of them were called
        # directly, so PROJECT_ONLY and PLUGIN_ONLY governed only the half that
        # happened to be wrapped - a dispatch that decides for some of its subjects
        # is not a dispatch, and the hole was invisible because the two lists were
        # written for checks that were wrapped.
        try:
            return fn(*a)
        except Exception as exc:  # noqa: BLE001 - one check, not the whole report
            # A check that dies took the whole report with it, and the CI step read a
            # traceback as the verdict. Now its findings are missing and it says so.
            report.add("00-check-crashed", "WARN",
                       f"{name} stopped on {type(exc).__name__}: {exc}. Its findings are "
                       "missing from this report; the rest ran. Please report it.", str(ctx.root))
            return None

    run(check_dangling_symlinks, ctx, report)
    run(check_claude_md, ctx, report)
    skills = run(check_skills, ctx, report) or {}
    agents = (run(check_agents, ctx, report) or {}) if ctx.layout not in ("library", "none") else {}
    run(check_agent_descriptions, ctx, report, agents)
    run(check_cross_refs, ctx, report, skills, agents)
    run(check_english_only, ctx, report)
    run(check_no_code_comments_in_skills, ctx, report)
    run(check_no_global_scripts, ctx, report)
    run(check_rules, ctx, report)
    run(check_skill_index, ctx, report, skills)
    run(check_reference_sizes, ctx, report)
    run(check_always_loaded_budget, ctx, report, skills, agents)
    run(check_unreadable, ctx, report)
    run(check_see_skill_targets, ctx, report, skills)
    run(check_foreign_skill_mentions, ctx, report, skills)
    run(check_documented_flags, ctx, report)
    run(check_frontmatter_quoting, ctx, report)
    run(check_all_relative_links, ctx, report)
    run(check_rule_globs, ctx, report)
    run(check_agent_frontmatter_validity, ctx, report, skills)
    run(check_settings_scope, ctx, report)
    run(check_hooks, ctx, report)
    run(check_frontmatter_hooks, ctx, report)
    run(check_security, ctx, report)
    run(check_repository_reality, ctx, report)
    run(check_agents_dir_skills, ctx, report)
    run(check_plugin_vars_in_project, ctx, report)
    run(check_other_tools, ctx, report)
    run(check_orphan_references, ctx, report)
    run(check_evals, ctx, report)
    run(check_doctrine_copy, ctx, report)
    run(check_eval_quality, ctx, report)
    run(check_twin_division_tables, ctx, report, skills)

    run(check_skill_anchors, ctx, report)
    run(check_listing_budget_derived, ctx, report, skills)
    run(check_plugin_cost, ctx, report, skills, agents)
    run(check_project_overlay, ctx, report, ctx.local)
    run(check_skill_names, ctx, report, skills)
    run(check_description_overlap, ctx, report, skills)
    run(check_unloadable_skills, ctx, report)
    run(check_settings_semantics, ctx, report)
    run(check_mcp, ctx, report)
    run(check_plugin_manifest, ctx, report)
    run(check_companions, ctx, report, skills)
    run(check_runtime_loads, ctx, report)
