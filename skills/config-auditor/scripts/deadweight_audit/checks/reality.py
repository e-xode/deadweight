"""Instructions against the repository: commands, anchors, file trees."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..context import AuditContext
from ..parsing.markdown import fenced_spans, inline_code_spans
from ..repo import readable_files, git_ignored, nested_prefix, tracked_paths
from ..report import Report


# ancrage
ANCHOR_SEVERITY = "WARN"   # ratchet: move to "ERROR" once this repository is at zero


# The WHOLE path, never its tail. The first version opened on `\b(?:src|...)/`, and
# `/` is not a word character, so there is a word boundary before every segment:
# `.claude/skills/<skill>/scripts/measure.mjs` matched as `scripts/measure.mjs`, was
# looked up from the root, and reported dead. Measured 2026-09-23 on one repository:
# 10 dead anchors out of 10 were live paths cut in half - and the bug was there from
# the first release that shipped this check, not introduced later. Absolute paths
# are captured too, so they are reported as unverifiable instead of vanishing.
ANCHOR_PATH_RE = re.compile(
    # `:` too: `package:other/src/internal.dart` is a Dart import URI, not a path
    # (second public sample, 2026-09-27).
    r"(?<![\w./~$}:-])((?:/|~/|(?:\.{1,2}/)*)(?:[\w.-]+/)*?"
    r"(?:src|server|scripts|electron|docker|app|lib|packages|test|tests)"
    r"/[A-Za-z0-9_./-]+\.[a-z]{2,4})\b(?!\.\w)"   # not the `.yml` of `x.yml.template`
)


ANCHOR_TEMPLATE_RE = re.compile(
    # `/.../` is an author eliding the middle of a path (`core/src/.../Rule.kt`): 7 dead
    # anchors on a second public sample were that, 2026-09-27.
    r"(MyPage|Feature|Example|Foo|Bar|YourThing|your(?=[A-Z_-])|<[^>]+>|placeholder|xxx|/\.\.\./)", re.IGNORECASE
)


def anchor_verdict(root: Path, ref: str, body: str, fences: list, bases: tuple, ignored, tracked_cache: list):
    """What one path named in a configuration file resolves to: alive, dead, unverifiable or skip.

    One chain for skills, CLAUDE.md, rules and agents. `bases` are the extra directories a
    relative path may be written from (a skill's folder, the skills directory).
    """
    rel = ref[2:] if ref.startswith("./") else ref
    # A path outside the repository, or one git ignores (`dist/`, `node_modules/`), is
    # alive on a machine that built the project and dead on a fresh clone. An absolute
    # path names the machine it runs on. Neither can be checked from here.
    if rel.startswith(("../", "/", "~/")) or ignored(rel):
        return "unverifiable", ""
    if (root / rel).exists() or any((b / rel).exists() for b in bases):
        return "alive", ""
    if ANCHOR_TEMPLATE_RE.search(ref):
        return "skip", ""             # template / illustrative path
    at = body.find(ref)
    if re.search(r"(?:e\.g\.|\bexample\b|such as|for instance)[^.\n]{0,30}$",
                 body[max(0, at - 48):at], re.I):
        # `**Example**: `x``, `Example: when `x` changes` - the phrase need not touch the
        # path. 2 of 23 dead anchors on a public sample, 2026-09-27.
        return "unverifiable", " (given as an example)"
    if not tracked_cache:
        tracked_cache.append(tracked_paths(root))
    prefix = nested_prefix(rel, tracked_cache[0])
    if prefix:
        # A monorepo names paths from its package: `src/x.ts` is `packages/api/src/x.ts`.
        # Found, so not dead; not where it says, so not alive (10 of 23 on a public sample).
        return "unverifiable", f" (only under {prefix})"
    if any(a <= at < b for a, b in fences):
        # A dead path inside a code block: an illustration of another codebase, or a stale
        # command. 42 of 45 dead anchors on a calibration sample (2026-09-23) sat in the
        # example blocks of a kit describing the projects it is installed into.
        return "unverifiable", " (in an example block)"
    return "dead", ""


# --- The repository as it is ------------------------------------------------------
_RUN_RE = re.compile(r"(?<![\w/-])(npm|pnpm|yarn|bun)\s+run\s+([A-Za-z0-9_:.@/-]+)")


_MAKE_RE = re.compile(r"(?<![\w/.-])make\b([^\n\x00;&|]*)")


_JUST_RE = re.compile(r"(?<![\w/.-])just\s+([A-Za-z0-9_-]+)")


_VERIFY_RE = re.compile(r"\b(?:test|tests|lint|check|typecheck|type-check|build|verify|ci|fmt|format)\b", re.I)


def _repo_commands(root: Path) -> dict:
    """npm scripts, make targets and just recipes the repository defines - None where it has no such file."""
    tracked = [t for t in tracked_paths(root) if "node_modules/" not in t]
    out: dict = {"npm": None, "make": None, "just": None, "make_pattern": False}
    for t in tracked:
        base = t.rsplit("/", 1)[-1]
        try:
            if base == "package.json":
                sc = json.loads((root / t).read_text(encoding="utf-8-sig")).get("scripts") or {}
                out["npm"] = (out["npm"] or set()) | set(sc)
            elif base in ("Makefile", "makefile", "GNUmakefile") or base.endswith(".mk"):
                txt = (root / t).read_text(encoding="utf-8", errors="replace")
                out["make"] = (out["make"] or set()) | set(re.findall(r"^([A-Za-z0-9_./-]+)\s*:(?!=)", txt, re.M))
                # A pattern rule, or an `include`, defines targets this reading cannot list
                # (3 false findings on openshift-style boilerplate among 600 repositories).
                out["make_pattern"] |= bool(re.search(r"^%[^:\n]*:|^-?include\s", txt, re.M))
            elif base.lower() in ("justfile", ".justfile"):
                txt = (root / t).read_text(encoding="utf-8", errors="replace")
                out["just"] = (out["just"] or set()) | set(re.findall(r"^@?([A-Za-z0-9_-]+)(?:\s[^:=\n]*)?:(?!=)", txt, re.M))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            continue
    return out


def _instruction_files(root: Path) -> list[Path]:
    """What the model is told to follow in every session or on demand: CLAUDE.md, rules, commands, agents."""
    files = [root / n for n in ("CLAUDE.md", ".claude/CLAUDE.md") if (root / n).is_file()]
    for d in ("rules", "commands", "agents"):
        base = root / ".claude" / d
        if base.is_dir():
            files += readable_files(base.rglob("*.md"))
    return files


def check_repository_reality(ctx: AuditContext, report: Report) -> None:
    """Instructions that name what the repository no longer has.

    "Treat CLAUDE.md like code: review it when things go wrong, prune it regularly", and
    include "Bash commands Claude can't guess" (best-practices): a command the file names
    and the repository does not define sends the model down a failing path it was told to
    take. Only npm/pnpm/yarn/bun `run`, `make` and `just` are resolved, and only where the
    repository has the file that defines them - a script run by path is an anchor (28).
    """
    root = ctx.root
    cmds = _repo_commands(root)
    tracked_cache: list = []
    ignored = git_ignored(root)
    for f in _instruction_files(root):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fences = fenced_spans(text)
        rel = f.relative_to(root)
        # Commands are read in code only - inline spans and fenced blocks. In prose, `make`
        # and `just` are English: "make the change" gave `make the` (600 public repositories).
        # Joined on NUL, not a newline: `make` and `when` in two spans are not `make when`.
        # Fenced blocks only when they hold shell: in Go, `make` is a builtin (a rule's Go
        # snippet gave `make when`). Spans after "e.g." / "for example" are examples.
        shell_fences = [(a, b) for a, b in fences
                        if re.match(r"\s*(?:`{3,}|~{3,})\s*(?:bash|sh|shell|zsh|console|terminal|text)?\s*$",
                                    text[a:text.find("\n", a)] if "\n" in text[a:b] else text[a:b])]
        spans = [(a, b) for a, b in inline_code_spans(text)
                 if not re.search(r"(?:e\.g\.|\bexample\b|such as|for instance)[^.\n]{0,20}$",
                                  text[max(0, a - 40):a], re.I)]
        code = "\x00".join(text[a:b] for a, b in shell_fences + spans)
        dead = []
        if cmds["npm"] is not None:
            for tool, name in _RUN_RE.findall(code):
                # `npm run build/lint` means "build or lint", not a script of that name.
                if not name.startswith(("-", "<", "$", "{")) and "/" not in name and name not in cmds["npm"]:
                    dead.append(f"{tool} run {name}")
        if cmds["make"] is not None and not cmds["make_pattern"]:
            for remainder in _MAKE_RE.findall(code):
                # Read make's arguments: `-C dir` and `-f file` take a value, `VAR=x` is a
                # variable, the first bare word is the target. `make -C src` names none.
                word_set, target = remainder.replace("`", " ").split(), None
                i = 0
                while i < len(word_set):
                    w = word_set[i]
                    if w in ("-C", "-f", "--directory", "--file", "-I", "-o", "-W"):
                        i += 2
                        continue
                    if w.startswith("-") or "=" in w:
                        i += 1
                        continue
                    target = w if re.fullmatch(r"[A-Za-z0-9_./-]+", w) else None
                    break
                if target and target not in cmds["make"]:
                    dead.append(f"make {target}")
        if cmds["just"] is not None:
            for name in _JUST_RE.findall(code):
                if name not in cmds["just"] and not name.endswith("-"):
                    dead.append(f"just {name}")
        # A template is not a command: `npm run db:generate:<name>`, `bun run ...`, `make do-`,
        # `just --list` (a flag). 4 of 20 findings in a sample of the first pass.
        dead = sorted({x for x in dead if re.search(r"[A-Za-z0-9]$", x.split()[-1])
                       and not x.split()[-1].startswith("-") and "..." not in x})
        # WARN where the instructions are this project's own (CLAUDE.md, rules); NOTICE in
        # agents and commands, which are often kits describing the project they are
        # installed into - `npm run complexity-check` in a generic reviewer agent.
        grade = "WARN" if f.name == "CLAUDE.md" or ".claude/rules" in str(rel) else "NOTICE"
        if dead:
            report.add("51-stale-command", grade,
                       f"'{rel}' tells the model to run {', '.join(dead[:5])}"
                       f"{' (+' + str(len(dead) - 5) + ')' if len(dead) > 5 else ''}, which the "
                       "repository does not define (package.json scripts, Makefile targets, "
                       "justfile recipes). The model will try it and fail.", str(f))
        # Paths named in CLAUDE.md, rules and agents: the chain skills already use.
        if f.name == "CLAUDE.md" or ".claude/rules" in str(rel) or ".claude/agents" in str(rel):
            dead_links = []
            for ref in sorted(set(ANCHOR_PATH_RE.findall(text))):
                verdict, _ = anchor_verdict(root, ref, text, fences, (f.parent,), ignored, tracked_cache)
                if verdict == "dead":
                    dead_links.append(ref)
            if dead_links:
                # NOTICE: expected ~75% before measuring, and the first pass on 600 public
                # repositories confirmed it - templates, build outputs, files to create.
                report.add("28-config-anchors", "NOTICE",
                           f"'{rel}' names {', '.join(dead_links[:4])}{'...' if len(dead_links) > 4 else ''}, "
                           "which does not exist. A dead anchor in an instruction file sends the "
                           "model exploring for a file that is gone.", str(f))
        if f.name == "CLAUDE.md":
            tree = len(re.findall(r"^[\s│]*[├└]──", text, re.M))
            if tree >= 5:
                report.add("52-claude-md-tree", "NOTICE",
                           f"'{rel}' carries a file tree ({tree} lines). The docs list "
                           "\"file-by-file descriptions of the codebase\" among what to leave out: "
                           "the model reads the tree itself, and the lines are paid every "
                           "session (best-practices).", str(f))
    # A repository that defines a verification command and never tells Claude about it.
    defines = sorted({n for n in (cmds["npm"] or set()) | (cmds["make"] or set()) | (cmds["just"] or set())
                      if _VERIFY_RE.fullmatch(n.split(":")[0])})
    claude_md = next((root / n for n in ("CLAUDE.md", ".claude/CLAUDE.md") if (root / n).is_file()), None)
    if defines and claude_md is not None:
        told = " ".join(p.read_text(encoding="utf-8", errors="replace") for p in _instruction_files(root))
        if not re.search(r"\b(?:test|lint|typecheck|type-check|build|check|verify|pytest|cargo|go test|tsc|eslint|ruff|mypy|vitest|jest)\b",
                         told, re.I):
            report.add("53-no-verification-command", "NOTICE",
                       f"The repository defines {', '.join(defines[:4])}, and no instruction file "
                       "names a test, lint or build command. \"Give Claude a check it can run\" "
                       "(best-practices): without one it cannot verify its own work.", str(claude_md))


def check_skill_anchors(ctx: AuditContext, report: Report) -> None:
    """Every path a SKILL.md names in its body must resolve to a real file.

    A skill cannot fail loudly: when the code it describes moves, the skill keeps
    loading and keeps saying the same thing. Naming a verifiable path is the only
    way a doctrine can be contradicted by reality. A dead anchor is worse than no
    anchor: the skill is read in full at level 2, then the model looks for a file
    that is gone and falls back to exploration (Glob/Grep) - a fixed cost turned
    into an open one.
    """
    root = ctx.root
    skills_dir = root / ctx.skills_dir
    if not skills_dir.is_dir():
        return
    total = anchored = alive = dead = 0
    unverifiable: list[str] = []
    ignored = git_ignored(root)
    tracked_cache: list = []
    for skill_md in readable_files(skills_dir.glob("*/SKILL.md")):
        total += 1
        name = skill_md.parent.name
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
        # The documented path variables name a base, not the filesystem root: read
        # literally, `${CLAUDE_SKILL_DIR}/scripts/x.py` became the absolute path
        # `/scripts/x.py`. Substituted to what they resolve to before extraction.
        body = re.sub(r"\$\{?CLAUDE_SKILL_DIR\}?/", "./", body)
        body = re.sub(r"\$\{?CLAUDE_(?:PROJECT_DIR|PLUGIN_ROOT)\}?/", "", body)
        refs = sorted(set(ANCHOR_PATH_RE.findall(body)))
        fences = fenced_spans(body)
        if not refs:
            continue
        anchored += 1
        for ref in refs:
            verdict, note = anchor_verdict(root, ref, body, fences,
                                           (skill_md.parent, skills_dir), ignored, tracked_cache)
            if verdict == "alive":
                alive += 1
            elif verdict == "skip":
                continue
            elif verdict == "unverifiable":
                unverifiable.append(f"{name}: {ref}{note}")
            else:
                dead += 1
                report.add(
                    "28-skill-anchors",
                    ANCHOR_SEVERITY,
                    f"'{name}' names '{ref}', which does not exist. A dead anchor sends the "
                    "model exploring for a file that is gone: fix the path, or drop the claim.",
                    str(skill_md),
                )
    if total:
        report.add(
            "28-skill-anchors",
            "INFO",
            f"Falsifiability: {anchored}/{total} skills name at least one checkable path "
            f"({100 * anchored / total:.0f}%). Live anchors {alive}, dead {dead}. "
            "A skill that names nothing verifiable cannot be proven wrong - it can only rot quietly.",
            str(skills_dir),
        )
    if unverifiable:
        shown = ", ".join(unverifiable[:5]) + (f" (+{len(unverifiable) - 5})" if len(unverifiable) > 5 else "")
        report.add(
            "28-skill-anchors",
            "NOTICE",
            f"{len(unverifiable)} anchor(s) not verifiable from the repository - ignored by git "
            f"or outside it, so their existence depends on the machine: {shown}. Counted neither "
            "alive nor dead.",
            str(skills_dir),
        )
