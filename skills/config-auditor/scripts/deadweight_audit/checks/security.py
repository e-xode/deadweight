"""Security: broad allows, secrets, remote execution, hidden unicode."""
from __future__ import annotations

import json
import os
import posixpath
import re
import shlex
from pathlib import Path

from ..catalog import SECURITY_GRADE
from ..context import AuditContext
from ..repo import git_tracked, readable_files
from ..report import Report


# A literal credential, not a ${VAR} reference. Prefixes of widely used token formats.
SECRET_LITERAL_RE = re.compile(r"(Bearer\s+[A-Za-z0-9._~+/-]{16,}|sk-[A-Za-z0-9_-]{16,}"
                               r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                               r"|xox[abpr]-[A-Za-z0-9-]{10,}|(?:AKIA|ASIA)[0-9A-Z]{16}"
                               r"|AIza[0-9A-Za-z_-]{35}|glpat-[0-9A-Za-z_-]{20,}|npm_[A-Za-z0-9]{36}"
                               r"|hf_[A-Za-z0-9]{30,}|(?:sk|rk|pk)_live_[0-9A-Za-z]{20,}"
                               r"|xai-[A-Za-z0-9]{20,}|SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"
                               r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


# --- Security -----------------------------------------------------------------
_SEC_BLANKET = re.compile(r"^(Bash|PowerShell)(\(\s*\*?\s*\))?$")


# The interpreter directly followed by the wildcard (`python*`, `python:*`, `node *`), as in
# the docs' "Bash(python*)". `pwsh scripts/*` names a folder of scripts: narrower, not this.
_SEC_INTERP = re.compile(r"^(Bash|PowerShell)\(\s*(?:python\d?(?:\.\d+)?|node|deno|bun|ruby|perl|php|sh|bash|zsh|pwsh)"
                         r"\s*[:\s]?\s*\*\s*\)$")


_SEC_PKG_RUN = re.compile(r"^Bash\(\s*(?:npm|pnpm|yarn|bun)\s+(?:run|exec|dlx|x)?\s*[:\s]?\*\s*\)$"
                          r"|^Bash\(\s*(?:npx|bunx|pnpx|uvx|pipx\s+run)[:\s]\*\s*\)$")


_SEC_REMOTE_EXEC = re.compile(r"(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b|(?:ba|z)?sh\s+<\(\s*(?:curl|wget)"
                              r"|base64\s+(?:-d|--decode)[^|]*\|\s*(?:ba|z)?sh\b|\biex\s*\(\s*(?:irm|iwr|Invoke-WebRequest)")


_SEC_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069\U000e0000-\U000e007f]")


# The three subdivision flags (England, Scotland, Wales): U+1F3F4, the tags spelling
# gbeng/gbsct/gbwls, U+E007F (UTS #51, ED-14a). Only these exact spellings are exempt: a
# tag_spec may be any run of U+E0020-E007E, so "black flag + any tags" could carry text.
_SEC_FLAG_TAGS = re.compile("\U0001F3F4\U000E0067\U000E0062(?:\U000E0065\U000E006E\U000E0067"
                            "|\U000E0073\U000E0063\U000E0074|\U000E0077\U000E006C\U000E0073)\U000E007F")


# `docker run` options that take their value as the NEXT argument (`docker run --help`).
# Without them the value of `-e NAME` was read as the image (audit externe 2026-10-08).
_DOCKER_VALUE_FLAGS = frozenset("""-a -c -e -h -l -m -p -u -v -w --add-host --annotation --attach
    --blkio-weight --blkio-weight-device --cap-add --cap-drop --cgroup-parent --cgroupns --cidfile
    --cpu-period --cpu-quota --cpu-rt-period --cpu-rt-runtime --cpu-shares --cpus --cpuset-cpus
    --cpuset-mems --device --device-cgroup-rule --device-read-bps --device-read-iops
    --device-write-bps --device-write-iops --dns --dns-option --dns-search --domainname
    --entrypoint --env --env-file --expose --gpus --group-add --health-cmd --health-interval
    --health-retries --health-start-interval --health-start-period --health-timeout --hostname
    --ip --ip6 --ipc --isolation --kernel-memory --label --label-file --link --link-local-ip
    --log-driver --log-opt --mac-address --memory --memory-reservation --memory-swap
    --memory-swappiness --mount --name --net --network --network-alias --oom-score-adj --pid
    --pids-limit --platform --publish --pull --restart --runtime --security-opt --shm-size
    --stop-signal --stop-timeout --storage-opt --sysctl --tmpfs --ulimit --user --userns --uts
    --volume --volume-driver --volumes-from --workdir""".split())


def _docker_image(args: list[str]) -> str:
    """The image of `docker run ...`: the first argument that is neither an option nor its value."""
    rest = args[args.index("run") + 1:]
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--":
            return rest[i + 1] if i + 1 < len(rest) else ""
        if a.startswith("-"):
            i += 2 if (a in _DOCKER_VALUE_FLAGS and "=" not in a) else 1
            continue
        return a
    return ""


def _hook_commands(hooks) -> list[str]:
    """The `command` of every command hook in a hooks object (settings or hooks/hooks.json)."""
    if not isinstance(hooks, dict):
        return []
    return [str(h.get("command", "")) for groups in hooks.values() if isinstance(groups, list)
            for g in groups if isinstance(g, dict) and isinstance(g.get("hooks"), list)
            for h in g["hooks"] if isinstance(h, dict) and h.get("type", "command") == "command"]


def _flag_values(command: str, flags: tuple[str, ...]) -> list[str]:
    """The arguments given to one of `flags` in a shell command: `--f a b`, `--f=a`."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if any(t.startswith(f + "=") for f in flags):
            out.append(t.split("=", 1)[1])
        elif t in flags:
            i += 1
            while i < len(toks) and not toks[i].startswith("-"):
                out.append(toks[i])
                i += 1
            continue
        i += 1
    return out


_SEC_PINNED_REF = re.compile(r"^(?:[0-9a-f]{7,40}|v?\d[\w.+-]*)$")   # a commit, or a version-shaped tag
_SEC_SCOPED_RULE = re.compile(r"^[A-Za-z_][\w*-]*\(.*\)$")


def _split_rules(value: str) -> list[str]:
    """`Bash,Edit(x),Read` -> its rules, commas inside parentheses kept."""
    out, depth, cur = [], 0, ""
    for ch in value:
        depth += (ch == "(") - (ch == ")")
        if ch in ", " and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [r for r in out + [cur] if r]


def _git_ref(spec: str) -> str:
    """The ref of a `git+URL@ref` source: after the last '@' of the path, past the host, so
    `git+ssh://git@host/x` (user, no ref) has none and `@feature/orders`, a ref holding '/',
    is named whole (external audit 4, se-01b)."""
    url = spec.split("#", 1)[0]
    m = re.match(r"git\+[\w.+-]+://[^/]*(.*)$", url)
    path = m.group(1) if m else url
    return path.rsplit("@", 1)[1].rstrip("/") if "@" in path else ""


def _git_may_track(root: Path, rel: str) -> bool:
    """Whether git may track `rel`. Only a clear "not tracked" or "not a repository" answers
    False; git missing or failing otherwise keeps the stricter grade (repo.git_tracked)."""
    return git_tracked(root, rel) in ("tracked", "unknown")


_SEC_ZW = re.compile("[\u200b\u2060]|(?<!^)\ufeff")


_SEC_KEY_NAME = re.compile(r"(?:^|_)(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE_KEY)$", re.I)


def _sec(report: Report, level: str, check: str, message: str, where: Path) -> None:
    report.add(check, SECURITY_GRADE[level], f"Security ({level}): {message}", str(where))


def check_security(ctx: AuditContext, report: Report) -> None:
    """What the configuration lets run, reach or leak - not whether it parses.

    The other checks read the shape of permissions, hooks and MCP servers; this one reads
    what a valid shape allows. The lists come from the docs (permission-modes: the "broad
    allow rules that grant arbitrary code execution" auto mode drops) and from the MCP and
    hooks security sections. Grades: high = ERROR, medium = WARN, whatever the profile.
    """
    root = ctx.root
    # 1. Settings: allow rules, additional directories, env secrets, hook and status commands.
    for rel in (f"{ctx.claude_dir}/settings.json", f"{ctx.claude_dir}/settings.local.json"):
        path = root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        # settings.json is shared by design; settings.local.json only when git tracks it.
        shared = not rel.endswith("settings.local.json") or _git_may_track(root, rel)
        # Git missing or refusing (dubious ownership): the stricter grade stays, but the message
        # does not state a reach git never confirmed (external audit 4, se-00b).
        reach = ("for everyone this file reaches" if not rel.endswith("settings.local.json")
                 or git_tracked(root, rel) == "tracked" else
                 "for everyone this file reaches if git tracks it (git could not answer)")
        for rule in [r for r in (perms.get("allow") or []) if isinstance(r, str)]:
            r = rule.strip()
            if _SEC_BLANKET.match(r) and rel.endswith("settings.local.json") and not shared:
                # "Project local | .claude/settings.local.json | You, in this one project only"
                # (settings): untracked, it reaches no one else (audit externe 2026-10-08).
                _sec(report, "medium", "50-security-broad-allow",
                     f"allow rule '{rule}' in '{rel}' approves every shell command without a "
                     "prompt in your own sessions of this project (a personal file git does not "
                     "track). Auto mode drops it as a rule that grants arbitrary code execution "
                     "(permission-modes).", path)
            elif _SEC_BLANKET.match(r):
                _sec(report, "high", "50-security-broad-allow",
                     f"allow rule '{rule}' in '{rel}' approves every shell command without a "
                     f"prompt, {reach}. Auto mode drops it as a rule that "
                     "grants arbitrary code execution (permission-modes).", path)
            # A NAMED subagent (`Agent(Explore)`) is as narrow as that agent: only the bare
            # rule and `Agent(*)` open every subagent (5 findings of 98 were named ones).
            elif _SEC_INTERP.match(r) or _SEC_PKG_RUN.match(r) or r in ("Agent", "Agent(*)", "Monitor", "Monitor(*)"):
                _sec(report, "medium", "50-security-broad-allow",
                     f"allow rule '{rule}' in '{rel}' runs arbitrary code without a prompt (an "
                     "interpreter, a package-manager run, Agent or Monitor): auto mode drops it "
                     "for that reason. Narrow it to the exact commands (permission-modes).", path)
            elif r in ("WebFetch", "WebFetch(domain:*)"):
                _sec(report, "medium", "50-security-broad-allow",
                     f"allow rule '{rule}' in '{rel}' fetches any URL without a prompt: every "
                     "host is reachable. Allow the domains you need (permissions).", path)
        for d in [x for x in (perms.get("additionalDirectories") or []) if isinstance(x, str)]:
            # posixpath, not os.path: on Windows ntpath turns '../x' back into '..\\x'.
            s, n = d.strip(), posixpath.normpath(d.strip().replace("\\", "/"))
            # The message names the case it found: it listed all three for every entry.
            where = ("the filesystem root" if s == "/" else
                     "a whole home" if s in ("~", "~/", "$HOME", "${HOME}") else
                     "a directory outside the project" if n == ".." or n.startswith("../") else "")
            if where:
                _sec(report, "medium", "50-security-directories",
                     f"additionalDirectories '{d}' in '{rel}' extends Claude's working boundary "
                     f"to {where} (security).", path)
        env = data.get("env") if isinstance(data.get("env"), dict) else {}
        for key, val in env.items():
            if not isinstance(val, str) or "${" in val:
                continue
            if SECRET_LITERAL_RE.search(val):
                _sec(report, "high", "50-security-secret",
                     f"env.{key} in '{rel}' holds what looks like a literal credential, in a "
                     "settings file. Keep it in the environment, not in the file - and rotate "
                     "it if the file was ever committed.", path)
            elif _SEC_KEY_NAME.search(key) and len(val) >= 16 and re.search(r"\d", val) \
                    and not re.search(r"(?i)your|example|xxx|changeme|placeholder|<|dummy|test", val):
                _sec(report, "medium", "50-security-secret",
                     f"env.{key} in '{rel}' is named like a credential and holds a literal value. "
                     "If it is one, move it out of the file.", path)
        # Only what executes: the `command` of command hooks. The whole hooks object was
        # searched, and a `prompt` hook telling the model to block `curl … | bash` read as
        # one that runs it (seventh public sample, 2026-09-27).
        blobs = _hook_commands(data.get("hooks"))
        blobs.append(str((data.get("statusLine") or {}).get("command", ""))
                     if isinstance(data.get("statusLine"), dict) else "")
        if any(_SEC_REMOTE_EXEC.search(b) for b in blobs):
            _sec(report, "high", "50-security-remote-exec",
                 f"a hook or the status line in '{rel}' downloads code and runs it (a `curl | sh` "
                 "shape): it executes with your full user permissions on every event, and what "
                 "it runs is whatever the server returns that day (hooks, security).", path)
    # 1b. A plugin's hooks/hooks.json: "Claude Code merges whatever you declare with
    # hooks/hooks.json when that file exists" (plugins-reference). Hooks inline in
    # plugin.json stay unread here, as hooks-anatomy.md declares.
    if ctx.layout == "plugin":
        path = root / "hooks" / "hooks.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else None
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            data = None
        if isinstance(data, dict) and any(_SEC_REMOTE_EXEC.search(b) for b in _hook_commands(data.get("hooks"))):
            _sec(report, "high", "50-security-remote-exec",
                 "a hook in 'hooks/hooks.json' downloads code and runs it (a `curl | sh` shape): "
                 "it executes with the full user permissions of everyone who installs the plugin, "
                 "and what it runs is whatever the server returns that day (hooks, security).", path)
    # 2. MCP servers: unpinned packages, plain http, download-and-run.
    for path in (root / ".mcp.json",):
        if not path.is_file():
            continue
        try:
            servers = (json.loads(path.read_text(encoding="utf-8-sig")) or {}).get("mcpServers") or {}
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, AttributeError):
            continue
        for srv, conf in sorted(servers.items()) if isinstance(servers, dict) else []:
            if not isinstance(conf, dict):
                continue
            cmd = str(conf.get("command", ""))
            args = [str(a) for a in (conf.get("args") or []) if isinstance(a, (str, int))]
            pkgs = [a for a in args if not a.startswith("-")]
            runner = os.path.basename(cmd)
            if runner in ("npx", "bunx", "pnpx") or (runner in ("pnpm", "yarn") and args[:1] == ["dlx"]):
                cand = [a for a in pkgs if a != "dlx"][:1]
                if cand and not cand[0].startswith((".", "/")) and (
                        "@" not in cand[0][1:] or cand[0].endswith("@latest")):
                    _sec(report, "medium", "50-security-mcp-unpinned",
                         f"MCP server '{srv}' runs '{cand[0]}' through {runner} with no pinned "
                         "version: each start may fetch different code than the one you "
                         "reviewed. Pin a version (package@x.y.z).", path)
            # uv: "To run a tool at a specific version, use `command@<version>`" and "the `@`
            # syntax cannot be used for anything other than an exact version" (docs.astral.sh/uv,
            # guides/tools) - except `@latest`, which asks for the newest.
            # A git source is another matter: `git+URL@master` "pull[s] the latest commit from
            # a specific named branch" (same guide), so its '@' pins nothing by itself.
            elif runner in ("uvx",) and pkgs and pkgs[0].startswith("git+"):
                ref = _git_ref(pkgs[0])
                if not ref or not _SEC_PINNED_REF.match(ref):
                    _sec(report, "medium", "50-security-mcp-unpinned",
                         f"MCP server '{srv}' runs '{pkgs[0]}' through uvx with "
                         + (f"the git ref '{ref}', neither a commit hash nor a version tag" if ref
                            else "no git ref")
                         + ": a branch \"pull[s] the latest commit\" (uv, guides/tools), so each "
                         "start may run code you did not review. Pin a commit (git+URL@<commit>).", path)
            elif runner in ("uvx",) and pkgs and "==" not in pkgs[0] and not pkgs[0].startswith((".", "/")) \
                    and ("@" not in pkgs[0][1:] or pkgs[0].endswith("@latest")):
                _sec(report, "medium", "50-security-mcp-unpinned",
                     f"MCP server '{srv}' runs '{pkgs[0]}' through uvx with no pinned version "
                     "(package==x.y.z or package@x.y.z).", path)
            elif runner == "docker" and "run" in args:
                img = _docker_image(args)
                img = "" if img.startswith("/") else img
                if img and (":" not in img.split("/")[-1] or img.endswith(":latest")) and "@sha256" not in img:
                    _sec(report, "medium", "50-security-mcp-unpinned",
                         f"MCP server '{srv}' runs the image '{img}' with no pinned tag.", path)
            url = str(conf.get("url", ""))
            if url.startswith("http://") and not re.match(r"http://(localhost|127\.0\.0\.1|\[::1\])(:|/|$)", url):
                _sec(report, "medium", "50-security-mcp-http",
                     f"MCP server '{srv}' is reached over plain http ({url.split('?')[0]}): "
                     "requests, tokens and tool results travel unencrypted.", path)
            if _SEC_REMOTE_EXEC.search(" ".join([cmd] + args)):
                _sec(report, "high", "50-security-remote-exec",
                     f"MCP server '{srv}' downloads code and runs it at start.", path)
    # 3. `claude -p` runs that believe they are sandboxed. `--allowedTools` "Tools that execute
    # without prompting ... To restrict which tools are available, use --tools instead", and a
    # scoped `--disallowedTools` rule "leaves the tool available" (cli-reference). A harness
    # that isolates with those alone leaves every other tool reachable - measured by a
    # colleague session on 2.1.283: 147 of 257 runs called a tool outside the list.
    # `.claude/` by name, not CLAUDE_DIR: in a plugin that is the whole repository, and the
    # check read its own message in audit.py.
    scripts = [p for d in (root / ".github" / "workflows", root / "scripts", root / "bin", root / ".claude")
               if d.is_dir() for p in readable_files(d.rglob("*"))
               if p.is_file() and p.suffix in (".yml", ".yaml", ".sh", ".py", ".js", ".ts", ".mjs", "")]
    for p in scripts:
        try:
            t = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # One command over several lines (`\` continuations, as in best-practices) is one line here.
        t = re.sub(r"\\\r?\n", " ", t)
        for line_text in re.findall(r"^.*\bclaude\b[^\n]*\s(?:-p|--print)\b[^\n]*$", t, re.M):
            if not re.search(r"--(?:allowedTools|allowed-tools|disallowedTools|disallowed-tools)\b", line_text) \
                    or re.search(r"--(?:tools|restricted)\b", line_text):   # --bare skips discovery, keeps the tools
                continue
            # dontAsk "auto-denies every tool call that would otherwise prompt you" (permission-modes);
            # `--permission-prompts none`: "Claude Code denies them instead" (cli-reference).
            if re.search(r"--permission-mode[=\s]+[\"']?dontAsk\b", line_text) \
                    or re.search(r"--permission-prompts[=\s]+[\"']?none\b", line_text):
                continue
            # A bare name in --disallowedTools "removes the matching tools from Claude's context";
            # only a scoped rule "leaves the tool available" (cli-reference).
            allowed = re.search(r"--(?:allowedTools|allowed-tools)\b", line_text)
            # A rule has a rule's shape (`Bash(rm *)`): the prompt that follows a bare name is not one.
            scoped = [v for v in _flag_values(line_text, ("--disallowedTools", "--disallowed-tools"))
                      if any(_SEC_SCOPED_RULE.match(x.strip()) for x in _split_rules(v))]
            if allowed:
                _sec(report, "medium", "50-security-headless-isolation",
                     f"'{p.relative_to(root)}' runs `claude -p` with --allowedTools and no --tools: "
                     "--allowedTools approves calls, it does not remove tools - \"to restrict which "
                     "tools are available, use --tools\" (cli-reference), --permission-mode dontAsk "
                     "to deny every call it does not approve (permission-modes), or --restricted for "
                     "an evaluation harness.", p)
                break
            if scoped:
                _sec(report, "medium", "50-security-headless-isolation",
                     f"'{p.relative_to(root)}' runs `claude -p` with a scoped --disallowedTools rule "
                     f"('{scoped[0]}') and no --tools: a scoped rule \"leaves the tool available and "
                     "denies only calls that match\" (cli-reference). A bare tool name removes the "
                     "tool; --tools restricts which tools are available.", p)
                break
    # 4. Hidden characters in what the model reads.
    read_files = [root / n for n in ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md") if (root / n).is_file()]
    for d in ((root / ctx.claude_dir) if ctx.layout == "project" else root / ctx.skills_dir, root / ctx.agents_dir,
              root / "commands", root / "hooks"):
        if d.is_dir():
            read_files += [p for p in readable_files(d.rglob("*"))
                    if p.suffix in (".md", ".sh", ".py", ".js", ".json", ".mdc")]
    for p in sorted(set(read_files)):
        try:
            t = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        t = _SEC_FLAG_TAGS.sub("", t)      # a visible flag emoji, not hidden text
        m = _SEC_BIDI.search(t)
        if m:
            _sec(report, "high", "50-security-hidden-unicode",
                 f"'{p.relative_to(root)}' contains U+{ord(m.group(0)):04X}, a bidirectional or tag "
                 "character: invisible in an editor, read by the model. It is how instructions "
                 "are hidden in rules files.", p)
        elif _SEC_ZW.search(t):
            m = _SEC_ZW.search(t)
            # low: 9 findings in 5 of 600 repositories, some of them a reference that
            # documents the byte-order mark - below the 90% bar set before measuring.
            _sec(report, "low", "50-security-hidden-unicode",
                 f"'{p.relative_to(root)}' contains U+{ord(m.group(0)):04X}, a zero-width character: "
                 "usually a copy-paste artefact, sometimes a hiding place.", p)
