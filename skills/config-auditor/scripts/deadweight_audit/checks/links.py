"""Links and cross-references: relative links, `See skill:` targets, symlinks."""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..context import AuditContext
from ..parsing.markdown import iter_relative_links
from ..repo import readable_files, git_ignored, exists_from_root, leaves_repo
from ..report import Report


def check_unreadable(ctx: AuditContext, report: Report) -> None:
    """Files under .claude/ the auditor could not open.

    Until 2026-09-22 nine call sites caught only `UnicodeDecodeError`, so a file
    the process may not read raised `PermissionError` and took the whole audit
    down - found when an eval sandbox masked `.claude/loop.md` to mode 000 and
    the run reported "the audit script crashes". The catches now include OSError,
    which turns a crash into a skip; this check exists so the skip is not silent.
    An auditor that says nothing about what it could not read is claiming a
    coverage it does not have.
    """
    root = ctx.root
    base = root / ctx.claude_dir
    if not base.is_dir():
        return
    silent: list[str] = []
    for f in readable_files(base.rglob("*")):
        if not f.is_file():
            continue
        try:
            with f.open("rb"):
                pass
        except OSError:
            silent.append(str(f.relative_to(root)))
    if silent:
        report.add(
            "38-unreadable",
            "WARN",
            f"{len(silent)} file(s) under {ctx.claude_dir}/ could not be opened and were not "
            f"audited: {', '.join(silent[:5])}"
            + (f" and {len(silent) - 5} more" if len(silent) > 5 else "")
            + ". Every check that would have read them reported nothing, which is not "
            "the same as reporting that they are sound.",
            str(base),
        )


def check_see_skill_targets(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    root = ctx.root
    if not skills:
        return
    # "A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md`
    # both create `/deploy` and work the same way" (skills): a command file is a valid
    # target. Until 0.23.0 only skill folders were, and a pointer to a command was an
    # ERROR (external audit, 2026-10-08).
    commands = root / ctx.claude_dir / "commands"
    # A nested command is named by its path: `commands/ops/lint-all.md` is `/ops:lint-all`
    # (skills, "How a skill gets its command name"), never `lint-all` (audit externe 3, g7-00).
    command_names = ({p.relative_to(commands).with_suffix("").as_posix().replace("/", ":")
                      for p in readable_files(commands.rglob("*.md"))}
                     if commands.is_dir() else set())
    targets: list[Path] = []
    for sub in ("skills", "agents", "rules"):
        base = root / ctx.claude_dir / sub
        if base.is_dir():
            targets.extend(readable_files(base.rglob("*.md")))
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(
            r"➜\s*See skill:\s*([a-z0-9][a-z0-9-]*(?::[a-z0-9][a-z0-9-]*)?)", text
        ):
            name = m.group(1)
            # `plugin:skill` names a skill that lives outside this repository. Whether
            # it resolves depends on what the reader has installed, and nothing on disk
            # says. Until 2026-09-22 the pattern stopped at the `:`, captured the plugin
            # name alone, and reported it missing - so a project routing to this very
            # plugin (`➜ See skill: deadweight:config-auditor`, the convention this
            # plugin prescribes) earned an ERROR for following the doctrine it ships.
            # Skipping is the same call made for a link that climbs above the root:
            # claiming it is broken states an opinion the auditor cannot hold.
            if ":" in name:
                continue
            if name not in skills and name not in command_names:
                report.add(
                    "18-see-skill-target",
                    "ERROR",
                    f"Cross-reference '➜ See skill: {name}' points to a non-existent skill.",
                    str(path),
                )


def check_foreign_skill_mentions(ctx: AuditContext, report: Report, skills: dict[str, dict]) -> None:
    """A plugin must not route to skills it does not ship.

    A reference to a skill the reader does not have is a dangling reference, and a
    dangling reference costs a model more than a human: a human shrugs, a model goes
    looking - Glob, Grep, wrong files read. Bounded cost for one, unbounded for the
    other. In a PROJECT that risk is local and check 18 already covers the formal
    `➜ See skill:` form. In a PLUGIN the same sentence ships to every consumer, and
    in most of them the target does not exist.

    Two shapes are legitimate and are not flagged: the declared fictional example
    domain (a plugin's references need a worked example), and an angle-bracket
    placeholder. What is flagged is a bare backticked skill name that the plugin
    does not ship - it reads as a routing instruction and is not one.

    The fix is never to delete the sentence: it is to say that absent is a valid
    state, or to move the name into the example domain.
    """
    root = ctx.root
    if ctx.layout != "plugin":
        return
    # ROUTING CONTEXTS ONLY. A first version matched any backticked kebab-case
    # token and returned 21 findings, of which some fifteen were frontmatter keys
    # (`disable-model-invocation`, `allowed-tools`), eval vocabulary
    # (`anti-trigger`, `near-miss`) and built-in commands. A detector that is
    # wrong seven times out of ten is one people learn to skip, which is worse
    # than not having it. What makes a name a routing instruction is the arrow in
    # front of it, not its shape.
    example_prefixes = ("shop-", "ui-", "api-", "data-")
    # A hyphen is not mandatory in a skill name: a first version required one and
    # missed `hooks`, `review`, `translate`, `release`. The arrow is what qualifies
    # the context; the shape of the name does not have to.
    #
    # A generic `→ `name`` was accepted here until 2026-09-22 and had to go. Measured
    # on 15 third-party public repositories it produced 140 findings of which some
    # 130 were false, because a bare arrow is how everyone writes a state table:
    # `running → `success``, `→ `not-started``, `→ `8867-4``. An arrow means
    # transition far more often than it means routing. `➜ See skill:` is a stated
    # convention and carries the intent; `→` carries none.
    routing = re.compile(
        r"➜\s*See skill:\s*([a-z0-9]+(?:-[a-z0-9]+)*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?)"
    )
    seen: dict[str, list[str]] = {}
    base = root / ctx.skills_dir
    if not base.is_dir():
        return
    for path in readable_files(base.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in routing.finditer(text):
            name = m.group(1)
            # A `plugin:skill` reference already tells the reader the target is
            # external and where it comes from - which is the very remediation this
            # check asks for. It is the bare name, readable as local, that misleads.
            if ":" in name:
                continue
            if name in skills or name.startswith(example_prefixes):
                continue
            # An agent this plugin ships is a legitimate routing target, and half
            # the composite names the old regex caught were agents: `code-implementer`,
            # `test-writer`, `design-reviewer`, `session-reviewer`.
            if (root / "agents" / f"{name}.md").is_file():
                continue
            seen.setdefault(name, []).append(str(path.relative_to(root)))
    for name, where in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        report.add(
            "36-foreign-skill",
            "WARN",
            f"`{name}` reads as a skill name but this plugin does not ship it "
            f"({len(where)} mention(s), e.g. {where[0]}). In a consuming project it may "
            "not exist: say that absent is a valid state, or move it to the example domain.",
            str(root / ctx.skills_dir),
        )


def check_all_relative_links(ctx: AuditContext, report: Report) -> None:
    """Every relative markdown link under .claude/ resolves to a real file.

    Check 07 only inspects SKILL.md and only follows links that stay inside the
    skill folder, so a reference linking to a sibling skill — or any link at
    all from a reference file — went unverified. Moving a section one directory
    deeper is exactly how those break, silently.
    """
    root = ctx.root
    base = root / ctx.claude_dir
    if not base.is_dir():
        return
    skills_root = root / ctx.skills_dir
    # A plugin's configuration is its components, not the whole repository: with
    # CLAUDE_DIR at ".", an application that ships a plugin had its README and its
    # generated CLI docs audited as Claude configuration (2026-09-27).
    homes = ([root / d for d in (ctx.skills_dir, ctx.agents_dir, "commands", "hooks")]
             if ctx.layout == "plugin" else [base])
    files = readable_files({md for h in homes if h.is_dir() for md in h.rglob("*.md")})
    seen: set[tuple[Path, str]] = set()
    ignored = git_ignored(root)
    for md in files:
        into_ignored: list[str] = []
        # A template's links point at what the reader will create.
        if "template" in md.name.lower() or "templates" in md.parent.parts:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for link, _ in iter_relative_links(text):
            if leaves_repo(md.parent, link, root):
                continue
            # A SKILL.md link that stays in its skill folder is check 07's: reporting
            # it here too counted one broken link as two ERRORs.
            if md.name == "SKILL.md" and md.parent.parent == skills_root \
                    and md.parent.resolve() in (md.parent / link).resolve().parents:
                continue
            key = (md, link[2:] if link.startswith("./") else link)
            if exists_from_root(root, link):
                continue
            if not (md.parent / link).exists() and key not in seen:
                seen.add(key)            # one dead link, one finding - not one per mention or spelling
                # A target under a path git ignores exists where a script installed it and
                # nowhere in a clone: the verdict depends on the machine, not the commit -
                # the class 22 already reads through git (100 false ERRORs in one fresh
                # public repository, 2026-09-27, `.claude/skills/ext/` filled by a script).
                rel_target = os.path.relpath(os.path.normpath(md.parent / link.split("#")[0]),
                                             root).replace(os.sep, "/")
                if not rel_target.startswith("..") and ignored(rel_target):
                    into_ignored.append(link)
                    continue
                report.add(
                    "20-relative-links",
                    "ERROR",
                    f"'{md.relative_to(base)}' links to non-existent '{link}'",
                    str(md),
                )
        if into_ignored:
            report.add(
                "20-relative-links",
                "NOTICE",
                f"'{md.relative_to(base)}' has {len(into_ignored)} link(s) into paths git ignores "
                f"(e.g. '{into_ignored[0]}'): they resolve only where those untracked files were "
                "installed, so whether they are dead depends on the machine. Not counted.",
                str(md),
            )


# --- Dangling symbolic links ---------------------------------------------------
def check_dangling_symlinks(ctx: AuditContext, report: Report) -> None:
    """A committed link to a file only its author has.

    `SKILL.md -> /home/<author>/project/...` or `-> ../../.<tool>/skills/x/SKILL.md` (a
    directory nobody commits) works on one machine. Everyone who clones gets a name and
    no file: the skill, agent or command does not load, and nothing says why. Until
    2026-09-27 this auditor read the link and died on it - 3 of 150 public repositories
    in a second sample, with no report at all.
    """
    root = ctx.root
    homes = ([root / ctx.claude_dir] if ctx.layout == "project"
             else [root / d for d in (ctx.skills_dir, ctx.agents_dir, "commands", "hooks")])
    seen: set[Path] = set()
    for home in homes:
        if not home.is_dir():
            continue
        # sorted, not existants(): the links this check exists for are exactly what
        # existants() drops - a bulk replace made it blind once (2026-09-27).
        for p in sorted(home.rglob("*")):
            if p in seen or not p.is_symlink() or p.exists():
                continue
            seen.add(p)
            target = os.readlink(p)
            report.add("47-dangling-symlink", "WARN",
                       f"'{p.relative_to(root)}' is a symbolic link to '{target}', which does not "
                       "exist in this checkout: whoever clones the repository gets the name and "
                       "not the file, and what it declares does not load.", str(p))
