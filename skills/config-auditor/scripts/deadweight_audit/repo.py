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


def project_memory_files(root: Path) -> list[Path]:
    """Every project memory file that exists: ./CLAUDE.md, ./.claude/CLAUDE.md, ./CLAUDE.local.md.

    claude_md_path() picks ONE, for the checks that need the file a table lives in. What
    loads is all of them: "All discovered files are concatenated into context rather than
    overriding each other", and CLAUDE.local.md "loads alongside CLAUDE.md and is treated
    the same way" (memory). Measuring the first only let a 300-line .claude/CLAUDE.md pass
    beside a one-line ./CLAUDE.md (audit externe 2026-10-08, P2-A--06).
    """
    # Each file once, by real path: a .claude/CLAUDE.md linked to ./CLAUDE.md is one file,
    # and was reported twice by 01 while 17 counted it once (audit externe 3, g4-06).
    seen: set[str] = set()
    out: list[Path] = []
    for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md", root / "CLAUDE.local.md"):
        real = os.path.realpath(p)
        if p.is_file() and real not in seen:
            seen.add(real)
            out.append(p)
    return out


IMPORT_MAX_HOPS = 4   # "a maximum depth of four hops" (memory)


def expand_imports(path: Path) -> list[Path]:
    """The files a memory file pulls in at launch through `@path` imports, recursively.

    "Imported files are expanded and loaded into context at launch"; "Relative paths
    resolve relative to the file containing the import, not the working directory";
    "a maximum depth of four hops" (memory). `~/` and absolute paths are skipped: they
    depend on the machine. Each file once, by real path; the importing file excluded.
    """
    from .parsing.markdown import memory_imports
    seen = {os.path.realpath(path)}
    found: list[Path] = []
    frontier = [path]
    for _ in range(IMPORT_MAX_HOPS):
        nxt = []
        for f in frontier:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for ref in memory_imports(text):
                if ref.startswith(("~/", "/")):
                    continue
                target = f.parent / ref
                real = os.path.realpath(target)
                if real in seen or not target.is_file():
                    continue
                seen.add(real)
                found.append(target)
                nxt.append(target)
        frontier = nxt
    return found


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
    # Git absent or failing falls back to the walk: it raised FileNotFoundError, and the
    # checks that list the tree crashed on a machine without git (external audit 3, 2026-10-08).
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others",
                            "--exclude-standard"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        r = None
    if r is not None and r.returncode == 0:
        return r.stdout.splitlines()
    return [str(p.relative_to(root)) for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts]


def nested_prefix(rel: str, tracked: list[str]) -> str | None:
    """The directory under which `rel` exists, when it does not exist at the root."""
    return next((t[: -len(rel)] for t in tracked if t.endswith("/" + rel)), None)


def git_tracked(root: Path, rel: str) -> str:
    """What git says of `rel` (relative to `root`): "tracked", "untracked", "outside" (no
    repository) or "unknown" (git missing, timed out or failing otherwise).

    Asked of git, which finds the enclosing repository even when `root` is a subfolder of
    it: testing `root / ".git"` read a file committed above the audit root as untracked
    (external audit 3, 2026-10-08). Each caller decides what "unknown" is worth.
    """
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", rel],
                           capture_output=True, text=True, timeout=10,
                           env={**os.environ, "LC_ALL": "C", "LANGUAGE": "C"})
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if r.returncode == 0:
        return "tracked"
    if "not a git repository" in r.stderr:
        return "outside"
    return "untracked" if r.returncode == 1 else "unknown"


def git_ignores(root: Path, rel: str) -> bool:
    """Whether the repository's own rules ignore `rel`, whatever folder of it `root` is.

    Outside a repository, or without git, nothing is ignored.
    """
    try:
        # The REPOSITORY's rules only: a user's global excludes file made the
        # same commit read differently on two machines (measured 2026-09-23 -
        # `**/.claude/settings.local.json` sat in ~/.config/git/ignore).
        r = subprocess.run(["git", "-C", str(root), "-c", "core.excludesFile=",
                            "check-ignore", "-q", "--", rel],
                           capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


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
            cache[rel] = git_ignores(root, rel)
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
