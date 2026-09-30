"""The audited repository as files: walking it, git's view of it, specimen directories."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


WALK_PRUNE_DIRS = {
    ".git", "node_modules", "dist", "build", "coverage", ".venv", "venv",
    "__pycache__", ".cache", ".output", ".next", ".nuxt", "out",
}


def exists_from_root(root: Path, link: str) -> bool:
    """A bare link (`docs/x.md`, no `./` or `../`) that exists from the repository root.

    The model reads a command, an agent or a skill from the working directory, which is
    the root: `docs/infra-guide.md` cited in `.claude/commands/plan.md` is a file it
    finds. Resolving it from the file's folder called 27 live links dead on a second
    public sample (2026-09-27). `./` and `../` say "next to me" and stay strict.
    """
    return not link.startswith(("./", "../")) and (root / link).exists()


def leaves_repo(origin: Path, link: str, root: Path) -> bool:
    """True when `link` climbs above the repository root.

    `../../../-/issues/174` is a GitLab issue reference that resolves on the
    forge, never on disk. Nothing outside the repository can be checked here,
    so claiming it is broken states an opinion the auditor cannot hold.
    """
    try:
        target = (origin / link).resolve()
        resolved_root = root.resolve()
    except OSError:
        return True
    return resolved_root != target and resolved_root not in target.parents


def repo_files(root: Path) -> list[str]:
    """Every repo-relative file path, minus build output and vendored trees.

    Dependency and build directories are pruned deliberately: a rule glob whose
    only matches live in `node_modules/` guards nothing the project writes, so
    counting those matches would hide exactly the inert globs check 22 exists
    to find.
    """
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in WALK_PRUNE_DIRS)
        rel = os.path.relpath(dirpath, root)
        prefix = "" if rel == "." else rel.replace(os.sep, "/") + "/"
        for name in sorted(filenames):
            files.append(prefix + name)
    return files


def claude_md_path(root: Path) -> Path:
    """The project CLAUDE.md: `./CLAUDE.md` or `./.claude/CLAUDE.md`, both official.

    "A project CLAUDE.md can be stored in either ./CLAUDE.md or ./.claude/CLAUDE.md"
    (memory, 2026-09-23). Looking only at the root reported "CLAUDE.md not found" as
    an ERROR on a project that had one.
    """
    for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md"):
        if p.is_file():
            return p
    return root / "CLAUDE.md"


def is_vendored_skill(skill_dir: Path) -> bool:
    """A skill shipping its own LICENSE is upstream code vendored verbatim.

    Project size and split budgets do not apply to files we must be able to
    re-sync from upstream; a table of contents is still required so the file
    stays navigable.
    """
    return (skill_dir / "LICENSE.txt").is_file() or (skill_dir / "LICENSE").is_file()


def readable_files(paths) -> list[Path]:
    """The files of a glob that can be read, sorted: a dangling link is listed and cannot.

    One helper for every walk, because 25 walks each read what `glob` returned, and a
    committed link to its author's disk crashed the audit (2026-09-27). The link itself
    is 47-dangling-symlink's to report.
    """
    return sorted(p for p in paths if p.exists())


def tracked_paths(root: Path) -> list[str]:
    """Repository-relative paths of the working tree: tracked, or new and not ignored.

    Not `ls-files` alone: a file created and not yet added is there for the model,
    and calling an anchor to it dead was wrong on the first negative control.
    """
    r = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others",
                        "--exclude-standard"], capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.splitlines()
    return [str(p.relative_to(root)) for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts]


def nested_prefix(rel: str, tracked: list[str]) -> str | None:
    """The directory under which `rel` exists, when it does not exist at the root."""
    return next((t[: -len(rel)] for t in tracked if t.endswith("/" + rel)), None)


def git_ignored(root: Path):
    """A predicate: is this repository-relative path ignored by git?

    Asked of git itself rather than of a hand-written list of build folders: a
    project that generates into `out/` or `.next/` is covered by its own
    .gitignore. Only the repository's own rules count - never the user's global
    excludes. Outside a git repository nothing is ignored.
    """
    import subprocess
    cache: dict[str, bool] = {}
    if not (root / ".git").exists():
        return lambda rel: False

    def ignored(rel: str) -> bool:
        if rel not in cache:
            try:
                # The REPOSITORY's rules only: a user's global excludes file made the
                # same commit read differently on two machines (measured 2026-09-23 -
                # `**/.claude/settings.local.json` sat in ~/.config/git/ignore).
                r = subprocess.run(["git", "-C", str(root), "-c", "core.excludesFile=",
                                    "check-ignore", "-q", "--", rel],
                                   capture_output=True, timeout=5)
                cache[rel] = r.returncode == 0
            except (OSError, subprocess.SubprocessError):
                cache[rel] = False
        return cache[rel]
    return ignored


SPECIMEN_DIRS = frozenset({
    "vendor", "vendors", "third_party", "third-party", "3rdparty", "3rd_party", "external",
    "extern", "bower_components",
    "template", "templates", "scaffold", "scaffolds", "skeleton", "skeletons", "boilerplate",
    "boilerplates",
    "example", "examples", "sample", "samples", "demo", "demos", "fixture", "fixtures",
    "__fixtures__", "testdata", "test-data", "test_data",
})


def is_specimen_path(rel: str) -> bool:
    """Whether a repository-relative path lies under a specimen folder (SPECIMEN_DIRS)."""
    parts = rel.lower().split("/")[:-1]
    return any(p in SPECIMEN_DIRS or p.endswith(".xctemplate") for p in parts)
