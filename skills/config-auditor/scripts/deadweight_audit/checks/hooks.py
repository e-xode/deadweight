"""Hooks, in settings and in skill or agent frontmatter."""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

from ..context import AuditContext
from ..parsing.frontmatter import frontmatter_hooks
from ..repo import readable_files
from ..report import Report
from ..vocabulary.hooks import (
    CONTEXT_INJECTING_HOOK_EVENTS,
    HOOK_DEFAULT_TIMEOUT,
    HOOK_EVENT_TIMEOUT,
    HOOK_EVENT_TYPES,
    HOOK_PLUGIN_ROOT_VARS,
    HOOK_PROJECT_DIR_VARS,
    HOOK_TOOL_EVENTS,
    HOOK_TYPE_FIELDS,
    KNOWN_HOOK_EVENTS,
    MATCHERLESS_HOOK_EVENTS,
)
from ..vocabulary.tools import KNOWN_TOOLS, TOOL_ALIASES


def _hook_declarations(ctx: AuditContext) -> list[tuple[Path, object]]:
    """Where hooks are declared, which depends on the container.

    A project declares them among its settings; a plugin ships `hooks/hooks.json`
    at its root. Same schema, two homes - the same split as skills, and the same
    reason the layout has to be detected before anything is read.
    """
    root = ctx.root
    rels = ([Path("hooks") / "hooks.json"] if ctx.layout == "plugin"
            else [Path(ctx.claude_dir) / "settings.json",
                  Path(ctx.claude_dir) / "settings.local.json"])
    return [(root / rel, rel) for rel in rels if (root / rel).is_file()]


def hook_paths(command: str) -> list[str]:
    """Tokens of a hook command that name a file this script can resolve.

    Every token is examined, not just the first: `python3 "$X/audit.py" --root .`
    runs a script the first token does not name. Tokens that cannot be resolved
    WITHOUT GUESSING are returned to nobody - a bare binary on PATH, a flag, an
    inline jq filter. A check that guessed here would report `npm run lint` as a
    dead path, and a check that cries wolf is how people learn to skip the whole
    report.
    """
    # Split as the shell does: `"$X/post.py";` is the path `$X/post.py` then a `;`,
    # not a file named `post.py;`. Whitespace splitting reported a live script
    # dead on a sampled public repository (2026-09-27), once per `if`/`elif` arm.
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = [t.replace('"', "").replace("'", "") for t in command.split()]
    out: list[str] = []
    for clean in tokens:
        if "/" not in clean or clean in out:
            continue
        # `go vet ./...`, `src/**/*.ts`: a pattern the tool expands, not a file.
        if "..." in clean or any(c in clean for c in "*?["):
            continue
        if clean.startswith(HOOK_PLUGIN_ROOT_VARS + HOOK_PROJECT_DIR_VARS + ("./",) + HOME_PREFIXES):
            out.append(clean)
        # An absolute path, or a bare relative one, is a script only when it looks like one:
        # `/dev/null`, `src/app` or a jq path are arguments, not files to run. Unchecked before
        # 2026-10-08 (anthropics/claude-code#82323 asks for exactly this check).
        elif SCRIPT_RE.search(clean) and not clean.startswith(("-", "$", "{")):
            out.append(clean)
    return out


HOME_PREFIXES = ("~/", "$HOME/", "${HOME}/")


# Words after which the next word is still the program the shell executes: keywords that
# open a command list, and wrappers that exec their argument (the execute bit is checked
# either way: `timeout 10 x.sh`, `exec x.sh`, `{ x.sh; }` fail with 126 when it is missing,
# measured under sh -c, audit 3 g6-00).
_SHELL_RESET_WORDS = {"if", "then", "else", "elif", "do", "while", "until", "{", "!", "time"}
_EXEC_WRAPPERS = {"exec", "command", "nohup", "nice", "env", "timeout", "stdbuf", "xargs"}


def _runs_directly(hook: dict, token: str) -> bool:
    """True when `token` is the program a hook executes, not an argument to one.

    Shell form goes to `sh -c` (hooks): `ruby x.rb` and `uv run x.py` hand the file to an
    interpreter, which needs no execute bit. Only the first word of a simple command - at
    the start, after `;`, `&&`, `||`, `|`, `(`, a newline or a keyword such as `then` or
    `{` - is executed itself, and a wrapper such as `timeout 10` or `exec` passes the word
    after its options on to be executed. Exec form runs `command`. A fixed list of
    interpreter names missed ruby, perl, uv, deno, bun, pwsh (audit 2026-10-08), and a
    substring test on it could hide a direct run.
    """
    command = str(hook.get("command", ""))
    if isinstance(hook.get("args"), list):
        return command == token
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return True                       # unparsable: keep the old, cautious verdict
    first = True
    wrapped = False                       # after a wrapper: skip its options and numbers
    target = False                        # the word after a redirect is a file, not the program
    lookup = False                        # `command -v x` looks x up, it does not run it
    prev = ""                             # the wrapper the options belong to
    for tok in tokens:
        # `./x.sh>/dev/null` is `./x.sh` then a redirect (external audit 4, ag-00): `<` and
        # `>` split words, and neither they nor their file start a new command.
        if tok and set(tok) <= set("<>&") and set(tok) & set("<>"):
            target = True
            continue
        if target:
            target = False
            continue
        if tok and set(tok) <= set(";&|()\n"):
            first, wrapped, lookup = True, False, False
            continue
        if lookup:
            continue
        if first and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            continue                      # `VAR=1 ./x.sh`: an assignment, not the program
        if first and tok in _SHELL_RESET_WORDS:
            continue
        if first and tok in _EXEC_WRAPPERS:
            wrapped, prev = True, tok
            continue
        if first and wrapped and tok in ("-v", "-V") and prev == "command":
            lookup = True                 # external audit 4, ag-01
            continue
        if first and wrapped and re.match(r"^(-.*|\d+(\.\d+)?[smhd]?)$", tok):
            continue                      # `timeout -k 5 10`, `nice -n 10`
        if first and tok == token:
            return True
        first = wrapped = False
    return False


def _dot_slash_hint(ctx: AuditContext, root: Path, decl: Path, token: str) -> str:
    """Why a `./` hook path is missing, and the path that works.

    hooks: "Handlers run in the current directory", which "follows Claude": a `./` path
    in a skill's or agent's frontmatter is NOT read from that file's folder.
    """
    hint = (". A `./` path is read from the current directory, which follows Claude's `cd`, "
            "not from the folder of the file that declares the hook (hooks)")
    beside = decl.parent / token[2:]
    if decl.suffix == ".md" and beside.exists() and ctx.layout != "plugin":
        hint += (f"; the script exists at '{beside.relative_to(root)}': write "
                 f"\"$CLAUDE_PROJECT_DIR\"/{beside.relative_to(root)}")
    return hint
SCRIPT_RE = re.compile(r"\.(sh|bash|zsh|py|js|mjs|cjs|ts|rb|pl|ps1)$")


def check_hooks(ctx: AuditContext, report: Report) -> None:
    """Hooks: the only configuration that executes, and the last one audited.

    A hook is the highest-consequence object in a Claude Code configuration - it
    runs code on an event, before anyone reads anything - and it was the one
    component this auditor could not see at all until 2026-09-22. Every other
    check here asks whether some text will be read; this one asks whether some
    code will run, against what, and at what price.

    Four failures it catches, none of which announces itself at runtime:
      - an event name that does not exist: it never fires, and never complains;
      - a command whose script is not there: a dead anchor that executes;
      - `${CLAUDE_PLUGIN_ROOT}` in a PROJECT hook: unresolvable by construction,
        since one variable cannot designate one plugin among the N installed;
      - no explicit timeout: the default is ten minutes of a hung session.
    """
    for path, rel in _hook_declarations(ctx):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # A settings file that does not parse is 24-settings-parse's to report: said
            # here too, one empty file was two ERRORs (third public sample, 2026-09-27).
            if path.name == "hooks.json":
                report.add("35-hooks-parse", "ERROR", f"'{rel}' is not valid JSON: {exc}", str(path))
            continue
        _audit_hooks(ctx, report, data.get("hooks") if isinstance(data, dict) else None, rel, path)


def check_frontmatter_hooks(ctx: AuditContext, report: Report) -> None:
    """Hooks declared in a skill's or an agent's frontmatter: the same checks as settings hooks."""
    root = ctx.root
    partial: list[Path] = []
    foreign: list[Path] = []
    sources = [(p, "skill") for p in readable_files((root / ctx.skills_dir).glob("*/SKILL.md"))] + \
              [(p, "agent") for p in readable_files((root / ctx.agents_dir).rglob("*.md"))]
    for p, kind_ in sources:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not re.search(r"^hooks:", text.split("\n---", 2)[0] if text.startswith("---") else "", re.M):
            continue
        hooks = frontmatter_hooks(text)
        fm_block = text.split("\n---", 2)[0]
        keys = re.findall(r"^  ([A-Za-z]+):", fm_block.split("\nhooks:", 1)[-1], re.M) \
            if "\nhooks:" in fm_block else []
        if keys and all(c[0].islower() and c not in KNOWN_HOOK_EVENTS for c in keys):
            # `pre:` / `post:`: another orchestrator's hook format in an agent Claude Code
            # also loads. None of it runs here - one cause, said once per repository, not
            # 218 ERRORs across 2 repositories (600 public repositories, 2026-09-27).
            foreign.append(p)
            continue
        if hooks is None:
            # Out of the block subset (`pre: |`, flow mappings): the event names are still
            # readable at the first level - and an unknown one never fires, however written.
            partial.append(p)
            fm_block = text.split("\n---", 2)[0]
            block = re.split(r"^hooks:\s*$", fm_block, maxsplit=1, flags=re.M)
            if len(block) == 2:
                lines = [l for l in block[1].splitlines() if l.strip()]
                ind = min((len(l) - len(l.lstrip()) for l in lines if l.startswith(" ")), default=0)
                for l in lines:
                    if not l.startswith(" "):
                        break
                    mm = re.match(r"^ {%d}([A-Za-z]+):" % ind, l)
                    if mm and mm.group(1) not in KNOWN_HOOK_EVENTS:
                        report.add("35-hooks-event", "ERROR",
                                   f"'{mm.group(1)}' in the frontmatter hooks of '{p.relative_to(root)}' "
                                   "is not a hook event: it never fires (hooks).", str(p))
            continue
        if kind_ == "agent" and isinstance(hooks, dict) and "Stop" in hooks:
            # "Claude Code converts a Stop hook here to SubagentStop" (hooks).
            hooks = {("SubagentStop" if e == "Stop" else e): v for e, v in hooks.items()}
        _audit_hooks(ctx, report, hooks, str(p.relative_to(root)), p)
    if foreign:
        shown = ", ".join(str(x.relative_to(root)) for x in foreign[:3])
        report.add("35-hooks-event", "WARN",
                   f"{len(foreign)} file(s) declare frontmatter hooks whose events are all "
                   "unknown to Claude Code (lowercase keys such as pre/post: another tool's format). "
                   f"Claude Code runs none of them ({shown}{'...' if len(foreign) > 3 else ''}).",
                   str(root))
    if partial:
        shown = ", ".join(str(x.relative_to(root)) for x in partial[:3])
        report.add("35-hooks-shape", "NOTICE",
                   f"{len(partial)} file(s) declare frontmatter hooks in a form this script reads "
                   f"only in part (multi-line scalars, flow mappings): event names checked, the "
                   f"rest not ({shown}{'...' if len(partial) > 3 else ''}).", str(root))


def _audit_hooks(ctx: AuditContext, report: Report, hooks, rel: str, path: Path, in_agent: bool = False) -> None:
    """Every check on one hooks object, wherever it was declared.

    Settings files, a plugin's hooks/hooks.json, `plugin.json` `hooks`, and the
    frontmatter of skills and agents share one format (hooks). Until 2026-09-27 only
    the first two were read: 156 agent files with frontmatter hooks in a sample of
    600 public repositories were never checked.
    """
    root = ctx.root
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        report.add("35-hooks-shape", "ERROR",
                   f"'hooks' in '{rel}' is not an object of event -> entries.", str(path))
        return

    injecting = []
    for event in sorted(hooks):
        if event not in KNOWN_HOOK_EVENTS:
            report.add("35-hooks-event", "ERROR",
                       f"'{event}' is not a hook event: it never fires. An interactive session "
                       "warns once at startup; `claude -p` and CI say nothing. Known events: "
                       f"{len(KNOWN_HOOK_EVENTS)} (hooks).", str(path))
            continue
        entries = hooks[event]
        if not isinstance(entries, list):
            report.add("35-hooks-shape", "ERROR",
                       f"'{event}' in '{rel}' must hold a list of matcher groups.", str(path))
            continue
        for i, entry in enumerate(entries):
            where = f"{event}[{i}]"
            if not isinstance(entry, dict):
                report.add("35-hooks-shape", "ERROR",
                           f"{where} in '{rel}' is not an object.", str(path))
                continue
            m = entry.get("matcher")
            if (isinstance(m, str) and re.fullmatch(r"mcp__[A-Za-z0-9_-]+", m)
                    and "__" not in m[5:]):
                report.add("35-hooks-matcher", "ERROR",
                           f"{where} matches '{m}', a bare MCP server prefix: it is compared "
                           f"as an exact string and matches no tool. Use '{m}__.*' (hooks).",
                           str(path))
            # A matcher written as a permission rule, `Bash(git commit*)` (anthropics/claude-code
            # #82314): it holds parentheses, so it is a regular expression tested against the
            # TOOL NAME only (hooks, "Matchers"), and `Bash(git commit*)` matches no tool name.
            # The argument filter belongs in the handler's `if` field. Judged by running the
            # pattern on the tool it names: `Edit(.*)` does match `Edit` and is left alone.
            pr = re.fullmatch(r"\s*([A-Za-z_]+)\((.*)\)\s*", m) if isinstance(m, str) else None
            if (event in HOOK_TOOL_EVENTS and pr
                    and (pr.group(1) in KNOWN_TOOLS or pr.group(1) in TOOL_ALIASES)):
                try:
                    fires = re.search(m, pr.group(1)) is not None
                except re.error:
                    fires = False
                if not fires:
                    report.add("35-hooks-matcher", "ERROR",
                               f"{where} in '{rel}' has matcher '{m}', written as a permission rule. "
                               "A matcher is compared with the tool name only, so this group never "
                               f"fires on '{event}'. Write the matcher '{pr.group(1)}' and put "
                               f"'{m.strip()}' in the handler's `if` field (hooks).", str(path))
            # "Matchers are case-sensitive" (hooks-guide), and a matcher made only of
            # letters, digits, `_ - , |` and spaces is compared as exact names (hooks):
            # `bash`, `Create` or `MCP` on a tool event matches no tool, ever.
            if (event in HOOK_TOOL_EVENTS and isinstance(m, str) and m.strip()
                    and re.fullmatch(r"[A-Za-z0-9_\-, |]+", m)):
                dead = [a for a in (x.strip() for x in re.split(r"[|,]", m)) if a
                        and a not in KNOWN_TOOLS and a not in TOOL_ALIASES
                        and not a.startswith("mcp__")]
                alts = [x for x in (y.strip() for y in re.split(r"[|,]", m)) if x]
                if dead and len(dead) == len(alts):
                    report.add("35-hooks-matcher", "ERROR",
                               f"{where} in '{rel}' matches {', '.join(repr(x) for x in dead)}, "
                               "which names no tool: matchers are exact and case-sensitive, so "
                               f"this group never fires on '{event}' (hooks).", str(path))
                elif dead:
                    # `Edit|MultiEdit|Write` still fires for Edit and Write: only the dead
                    # alternative is noise (57 of 60 findings on 600 public repositories).
                    report.add("35-hooks-matcher", "NOTICE",
                               f"{where} in '{rel}' lists {', '.join(repr(x) for x in dead)}, which "
                               "names no current tool (a retired one, or a typo): that alternative "
                               "matches nothing, the others still fire (hooks).", str(path))
            if entry.get("matcher") and event in MATCHERLESS_HOOK_EVENTS:
                report.add("35-hooks-matcher", "WARN",
                           f"{where} declares matcher '{entry['matcher']}' on '{event}', which "
                           "always fires. The matcher filters nothing and reads as if it did.",
                           str(path))
            inner = entry.get("hooks")
            if isinstance(inner, list) and not inner:
                # `"hooks": []` is a list, and an empty one runs nothing: a placeholder, not a
                # malformed group. It read "has no 'hooks' list" as an ERROR until 2026-09-27
                # (5 in one fresh public repository).
                report.add("35-hooks-shape", "NOTICE",
                           f"{where} in '{rel}' has an empty 'hooks' list: the group runs "
                           "nothing.", str(path))
                continue
            if not isinstance(inner, list):
                report.add("35-hooks-shape", "ERROR",
                           f"{where} in '{rel}' has no 'hooks' list.", str(path))
                continue
            for j, hook in enumerate(inner):
                spot = f"{where}.hooks[{j}]"
                if not isinstance(hook, dict):
                    report.add("35-hooks-shape", "ERROR",
                               f"{spot} in '{rel}' is not an object.", str(path))
                    continue
                if "type" not in hook:
                    report.add("35-hooks-shape", "WARN",
                               f"{spot} in '{rel}' has no 'type': the handler field is "
                               "required (hooks).", str(path))
                kind = hook.get("type", "command")
                if kind not in HOOK_TYPE_FIELDS:
                    report.add("35-hooks-shape", "ERROR",
                               f"{spot} in '{rel}' has type '{kind}', which is not a hook type "
                               f"({', '.join(sorted(HOOK_TYPE_FIELDS))}).", str(path))
                    continue
                if kind not in HOOK_EVENT_TYPES.get(event, HOOK_TYPE_FIELDS):
                    report.add("35-hooks-shape", "ERROR",
                               f"{spot} in '{rel}' is a '{kind}' hook on '{event}', which runs "
                               f"only {', '.join(sorted(HOOK_EVENT_TYPES[event]))} hooks: Claude "
                               "Code skips it (hooks).", str(path))
                    continue
                cond = hook.get("if")
                if cond is not None:
                    if event not in HOOK_TOOL_EVENTS:
                        report.add("35-hooks-if", "ERROR",
                                   f"{spot} in '{rel}' sets 'if' on '{event}': 'if' is evaluated "
                                   "on tool events only, and elsewhere the hook never runs "
                                   "(hooks).", str(path))
                    elif not isinstance(cond, str) or re.search(r"&&|\|\|", cond):
                        report.add("35-hooks-if", "ERROR",
                                   f"{spot} in '{rel}' combines rules in 'if': it holds exactly "
                                   "one permission rule, with no &&, || or list (hooks).",
                                   str(path))
                missing = [f for f in HOOK_TYPE_FIELDS[kind] if not hook.get(f)]
                if missing and kind != "command":
                    report.add("35-hooks-shape", "ERROR",
                               f"{spot} in '{rel}' is a '{kind}' hook with no "
                               f"{', '.join(repr(f) for f in missing)}.", str(path))
                if kind != "command":
                    continue
                command = hook.get("command")
                if isinstance(command, str) and isinstance(hook.get("args"), list):
                    # Exec form: the script can be any element, not just the command.
                    command = " ".join([command] + [str(a) for a in hook["args"]])
                if isinstance(command, str) and re.search(r'(?<!")\$\{?CLAUDE_PLUGIN_ROOT\}?/', command) \
                        and "args" not in hook:
                    report.add("35-hooks-command", "WARN",
                               f"{spot} in '{rel}' uses ${{CLAUDE_PLUGIN_ROOT}} unquoted in a "
                               "shell-form command: a plugin root with a space splits the "
                               "path. Wrap it in double quotes (plugins-reference).", str(path))
                if not isinstance(command, str) or not command.strip():
                    report.add("35-hooks-shape", "ERROR",
                               f"{spot} in '{rel}' is a command hook with no 'command'.",
                               str(path))
                    continue
                # hooks: "Claude Code doesn't enforce it on a command hook you run with
                # `async: true`" - such a hook blocks nothing, and a timeout does nothing.
                # `asyncRewake` keeps an enforced timeout, so it stays in.
                if "timeout" not in hook and not (hook.get("async") is True
                                                  and not hook.get("asyncRewake")):
                    default = HOOK_EVENT_TIMEOUT.get(event, HOOK_DEFAULT_TIMEOUT)
                    # NOTICE everywhere: `timeout` is optional and the docs recommend no value;
                    # no harm of the 600s default is documented or measured here (audit
                    # 2026-10-08). It was the most frequent finding of the 35 family.
                    report.add("35-hooks-timeout", "NOTICE",
                               f"{spot} in '{rel}' sets no 'timeout': the default on '{event}' "
                               f"is {default}s"
                               + (" (a budget shared by every SessionEnd hook)."
                                  if event == "SessionEnd" else ".")
                               + (" A hook that hangs holds the event it was meant to observe."
                                  if default >= 60 else ""), str(path))
                for token in hook_paths(command):
                    if token.startswith(HOOK_PLUGIN_ROOT_VARS) and ctx.layout != "plugin":
                        report.add("35-hooks-command", "ERROR",
                                   f"{spot} in '{rel}' uses CLAUDE_PLUGIN_ROOT, which a project "
                                   "hook cannot resolve: one variable cannot designate one "
                                   "plugin among those installed. A hook that needs a plugin's "
                                   "files has to be shipped BY that plugin.", str(path))
                        continue
                    resolved = token
                    for var in HOOK_PLUGIN_ROOT_VARS + HOOK_PROJECT_DIR_VARS:
                        resolved = resolved.replace(var, str(root))
                    outside = token.startswith(HOME_PREFIXES) or token.startswith("/")
                    for pre in HOME_PREFIXES:
                        if resolved.startswith(pre):
                            resolved = str(Path.home() / resolved[len(pre):])
                    # removeprefix, not lstrip: lstrip strips a SET of
                    # characters, so "./.claude/x" lost its dot-directory and
                    # a live script was reported dead. Caught by the negative
                    # control, never by reading the line.
                    rel_tok = resolved[2:] if resolved.startswith("./") else resolved
                    target = Path(rel_tok) if rel_tok.startswith("/") else root / rel_tok
                    if not target.exists():
                        where_txt = (" on this machine: a path outside the repository resolves "
                                     "per machine, so it is missing for everyone else too unless "
                                     "they install it" if outside else
                                     _dot_slash_hint(ctx, root, path, token) if token.startswith("./") else
                                     "" if token.startswith(HOOK_PLUGIN_ROOT_VARS + HOOK_PROJECT_DIR_VARS) else
                                     " from the project root. A bare relative path is read from the "
                                     "current directory, which follows Claude's `cd`: prefer "
                                     "\"$CLAUDE_PROJECT_DIR\"/... (hooks)")
                        report.add("35-hooks-command", "ERROR",
                                   f"{spot} in '{rel}' runs '{token}', which does not exist{where_txt}. A "
                                   "dead anchor that executes is worse than one that is read.",
                                   str(path))
                    elif target.is_file() and not os.access(target, os.X_OK) \
                            and _runs_directly(hook, token):
                        report.add("35-hooks-command", "WARN",
                                   f"{spot} in '{rel}' runs '{token}' directly, but it is not "
                                   "executable (chmod +x).", str(path))
        if event in CONTEXT_INJECTING_HOOK_EVENTS:
            injecting.append(event)

    if injecting:
        report.add("35-hooks-context", "NOTICE",
                   f"'{rel}' declares hooks on {', '.join(injecting)}: for these events Claude "
                   "Code adds plain-text stdout to the context. Whatever they print is paid in "
                   "tokens on every session - a cost the harness's own estimate leaves out, "
                   "because it prices the declaration and not the output.", str(path))
