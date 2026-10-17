"""Claude Code release watch: which changelog lines name a key this plugin has never heard of.

    python3 .github/scripts/claude_code_watch.py                 # print the issue body, write nothing
    python3 .github/scripts/claude_code_watch.py --create-issue  # CI only: open one issue for the range

Deterministic, standard library only, no model and no API key. Five steps:

1. npm `latest` of @anthropic-ai/claude-code (dist-tags, and the publish date from `time`).
2. Versions already covered. The state is the repository's ISSUES: an issue labelled
   `claude-code-drift` whose title carries `A..B` covers every version up to B. Before the
   first such issue, the baseline is the highest Claude Code version recorded as tested in
   skills/config-auditor/evidence.json (every `claude_code` value, wherever it sits). Nothing
   is committed back.
3. The upstream CHANGELOG.md, cut into the sections of the versions after the floor.
4. On each line: every camelCase identifier inside a backtick span (`"someKey": false` and
   `someKey: "block"` both yield someKey) that does not occur anywhere in the text files of
   skills/config-auditor - the plugin as checked out. Lines that remove or deprecate
   something, and lines naming a configuration surface, are reported whatever their keys.
   UPPER_SNAKE environment variables are listed apart: they are not configuration drift.
5. One Markdown body. With --create-issue, one issue for the whole range; --notify posts its
   title and URL to an optional Google Chat webhook read from the environment.

What it cannot see: a known key that changes meaning or place (a settings key that becomes
a frontmatter field is still "known"), a changed number or limit, a behaviour change written
without a backtick, and a section the changelog has not published yet.

Exit status: 0 (nothing new, or the body was printed or the issue opened); 2 (bad
arguments); 4 (the changelog's version headings no longer parse: a non-empty changelog with
no `## X.Y.Z` heading, or a `##` heading naming a version after the floor in another
shape - the watch would otherwise say "nothing new" for good); 1 is a crash.

Quoted upstream lines cannot notify anyone: `@name`, `owner/repo#N`, `#N`, `GH-N` and
URLs outside code spans are neutralised, so an issue opened here creates no mention and no
backlink on another repository's issues.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent
SKILL = "skills/config-auditor"
EXCLUSIONS = HERE / "claude_code_watch_exclude.txt"

NPM_URL = "https://registry.npmjs.org/@anthropic-ai/claude-code"
CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
LABEL = "claude-code-drift"
TITLE_PREFIX = "Claude Code drift"
KNOWN_SUFFIXES = (".py", ".md", ".json")
BODY_LIMIT = 60000  # GitHub refuses an issue body over 65536 characters
LINE_LIMIT = 400
EXIT_FORMAT = 4     # the changelog's headings changed shape: fail loudly, never "nothing new"

SECTION = re.compile(r"^##\s+v?(\d+\.\d+\.\d+)\s*$")
SPAN = re.compile(r"`([^`\n]+)`")
CAMEL = re.compile(r"(?<![A-Za-z0-9_])[a-z]+[A-Z][A-Za-z0-9]+(?![A-Za-z0-9_])")
ENV_VAR = re.compile(r"(?<![A-Za-z0-9_])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![A-Za-z0-9_])")
TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RANGE = re.compile(r"(\d+\.\d+\.\d+)(?:\s*\.\.\s*(\d+\.\d+\.\d+))?")
REMOVAL = re.compile(r"Removed|removed|Deprecated|deprecated")
MENTION = re.compile(r"(?<![\w`])@(?=\w)")
# GitHub autolinks these into references, and a reference to another repository's issue
# posts a backlink there: owner/repo#N, #N, GH-N, and issue or pull request URLs.
REFERENCE = re.compile(r"(?<![\w`/])(?:[\w.-]+/[\w.-]+)?#\d+\b|(?<![\w`])GH-\d+\b"
                       r"|https?://[^\s)>\]]*[^\s)>\].,;:!?'\"]", re.IGNORECASE)
HEADING_VERSION = re.compile(r"^##\s.*?\bv?(\d+\.\d+\.\d+)\b")
SURFACE = re.compile(r"frontmatter|settings\.json|hooks|permission|plugin\.json|marketplace",
                     re.IGNORECASE)


def vkey(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


# ---------- inputs ----------

def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "deadweight-claude-code-watch"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def npm_latest(doc: dict) -> tuple[str, str]:
    """(latest version, its publish timestamp or '') from the registry document."""
    latest = doc["dist-tags"]["latest"]
    return latest, doc.get("time", {}).get(latest, "")


def baseline_from_evidence(evidence: dict) -> str | None:
    """The highest `claude_code` value anywhere in evidence.json: the last version tested."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "claude_code" and isinstance(value, str) and RANGE.fullmatch(value):
                    found.append(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(evidence)
    return max(found, key=vkey) if found else None


def covered_upto(issues: list[dict]) -> str | None:
    """The highest version named by a `claude-code-drift` issue title, open or closed."""
    best: str | None = None
    for issue in issues:
        labels = {lab.get("name") if isinstance(lab, dict) else lab for lab in issue.get("labels", [])}
        if labels and LABEL not in labels:
            continue
        match = RANGE.search(issue.get("title", ""))
        if not match:
            continue
        upper = match.group(2) or match.group(1)
        if best is None or vkey(upper) > vkey(best):
            best = upper
    return best


def floor_version(baseline: str | None, covered: str | None) -> str | None:
    candidates = [v for v in (baseline, covered) if v]
    return max(candidates, key=vkey) if candidates else None


def split_sections(text: str) -> dict[str, list[str]]:
    """version -> its bullet lines, without the leading '- '."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw in text.splitlines():
        head = SECTION.match(raw)
        if head:
            current = sections.setdefault(head.group(1), [])
            continue
        if raw.startswith("## "):
            current = None
            continue
        if current is not None and raw.strip().startswith(("- ", "* ")):
            current.append(raw.strip()[2:].strip())
    return sections


def unparsed_headings(text: str) -> list[tuple[str, str]]:
    """(version, line) of each `## ...X.Y.Z...` heading that SECTION does not read."""
    found = []
    for raw in text.splitlines():
        head = HEADING_VERSION.match(raw)
        if head and not SECTION.match(raw):
            found.append((head.group(1), raw.strip()))
    return found


def format_problem(text: str, sections: dict[str, list[str]], floor: str | None) -> str:
    """Why the headings cannot be trusted, or '' when they can."""
    if text.strip() and not sections:
        return "no `## X.Y.Z` version heading parsed from a non-empty changelog"
    newer = [line for version, line in unparsed_headings(text)
             if floor is None or vkey(version) > vkey(floor)]
    if newer:
        return (f"{len(newer)} version heading(s) after the floor in a shape this script does not "
                f"read, first: {newer[0][:120]!r}")
    return ""


def new_versions(sections: dict[str, list[str]], after: str | None, through: str) -> list[str]:
    """Changelog versions in (after, through], ascending."""
    return sorted((v for v in sections
                   if vkey(v) <= vkey(through) and (after is None or vkey(v) > vkey(after))),
                  key=vkey)


def known_from_tree(root: Path) -> set[str]:
    known: set[str] = set()
    for path in (root / SKILL).rglob("*"):
        if path.is_file() and path.suffix in KNOWN_SUFFIXES and "__pycache__" not in path.parts:
            known.update(TOKEN.findall(path.read_text(encoding="utf-8", errors="replace")))
    return known


def known_from_git(root: Path, rev: str) -> set[str]:
    """The same set, from a commit: the plugin as published, not the working tree."""
    names = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "--name-only", rev, SKILL],
                           capture_output=True, text=True, check=True).stdout.split()
    known: set[str] = set()
    for name in names:
        if name.endswith(KNOWN_SUFFIXES):
            blob = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{name}"],
                                  capture_output=True, check=True).stdout
            known.update(TOKEN.findall(blob.decode("utf-8", errors="replace")))
    return known


def load_exclusions(path: Path) -> set[str]:
    excluded: set[str] = set()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            word = raw.split("#", 1)[0].strip()
            if word:
                excluded.add(word)
    return excluded


# ---------- extraction ----------

def identifiers(line: str) -> tuple[list[str], list[str]]:
    """(camelCase identifiers, UPPER_SNAKE variables) found inside the line's backtick spans."""
    camel: list[str] = []
    env: list[str] = []
    for span in SPAN.findall(line):
        for word in CAMEL.findall(span):
            if word not in camel:
                camel.append(word)
        for word in ENV_VAR.findall(span):
            if word not in env:
                env.append(word)
    return camel, env


def analyse(sections: dict[str, list[str]], versions: list[str], known: set[str],
            excluded: set[str]) -> dict:
    unknown: dict[str, list[tuple[str, str]]] = {}
    env: dict[str, list[str]] = {}
    removals: list[tuple[str, str]] = []
    surfaces: list[tuple[str, str]] = []
    skipped: set[str] = set()
    for version in versions:
        for line in sections[version]:
            camel, variables = identifiers(line)
            for word in camel:
                if word in excluded:
                    skipped.add(word)
                elif word not in known:
                    unknown.setdefault(word, []).append((version, line))
            for word in variables:
                env.setdefault(word, [])
                if version not in env[word]:
                    env[word].append(version)
            if REMOVAL.search(line):
                removals.append((version, line))
            elif SURFACE.search(line):
                surfaces.append((version, line))
    return {"unknown": unknown, "env": env, "removals": removals, "surfaces": surfaces,
            "excluded_seen": sorted(skipped)}


# ---------- output ----------

def title_for(versions: list[str]) -> str:
    span = versions[0] if len(versions) == 1 else f"{versions[0]}..{versions[-1]}"
    return f"{TITLE_PREFIX}: {span}"


def neutralise(line: str) -> str:
    """A quoted line that can neither @mention anyone nor link to another repository's issue.

    Outside code spans, `@name` gets a zero-width space after the `@`; a reference or a URL
    becomes a code span, with a zero-width space after any `#`. GitHub does not turn code
    into links or mentions."""
    line = MENTION.sub("@\u200b", line.replace("\r", " ").replace("\n", " "))
    parts = line.split("`")
    for i in range(0, len(parts), 2):   # even parts are outside backtick spans
        parts[i] = REFERENCE.sub(lambda m: "`" + m.group(0).replace("#", "#\u200b") + "`",
                                 parts[i])
    return "`".join(parts)


def clip(line: str, limit: int = LINE_LIMIT) -> str:
    """One changelog line, neutralised, and cut at a word boundary under `limit` characters
    without leaving a code span open."""
    line = neutralise(line)
    if len(line) <= limit:
        return line
    cut = line.rfind(" ", 0, limit - 2)
    head = line[:cut if cut > limit // 2 else limit - 2].rstrip()
    if head.count("`") % 2:
        head += "`"
    return head + "…"


def render(versions: list[str], found: dict, *, latest: str, published: str, floor: str | None,
           floor_source: str, known_source: str) -> str:
    out = [f"# {title_for(versions)}", "",
           f"npm `latest`: **{latest}**" + (f" (published {published})" if published else ""),
           f"Floor: {floor or 'none'} ({floor_source}). Versions read: {len(versions)} "
           f"({', '.join(versions)}).",
           f"Known identifiers: {known_source}.", "",
           "Generated by `.github/scripts/claude_code_watch.py`, without a model. Each item is "
           "a lead to check against the documentation, not a finding.", ""]
    unknown = found["unknown"]
    out += [f"## Identifiers the plugin has never named ({len(unknown)})", ""]
    if unknown:
        for word in sorted(unknown, key=str.lower):
            version, line = unknown[word][0]
            more = f" (+{len(unknown[word]) - 1} more)" if len(unknown[word]) > 1 else ""
            out.append(f"- [ ] `{word}` - {version}{more}: {clip(line)}")
    else:
        out.append("None.")
    out += ["", f"## Removed or deprecated ({len(found['removals'])})", ""]
    out += [f"- [ ] {v}: {clip(line)}" for v, line in found["removals"]] or ["None."]
    changes = [(v, line) for v, line in found["surfaces"] if not line.startswith("Fixed")]
    fixes = [(v, line) for v, line in found["surfaces"] if line.startswith("Fixed")]
    out += ["", f"## Lines naming a configuration surface ({len(changes)} changes, "
            f"{len(fixes)} fixes)", "",
            "frontmatter, settings.json, hooks, permission, plugin.json, marketplace - "
            "whatever the keys on the line.", ""]
    out += [f"- [ ] {v}: {clip(line)}" for v, line in changes] or ["None."]
    out += ["", f"## Environment variables, not drift ({len(found['env'])})", ""]
    out += [", ".join(f"`{w}` ({', '.join(vs)})" for w, vs in sorted(found["env"].items()))
            or "None."]
    if found["excluded_seen"]:
        out += ["", "Excluded as payload fields (claude_code_watch_exclude.txt): "
                + ", ".join(f"`{w}`" for w in found["excluded_seen"]) + "."]
    out += ["", "## What this watch cannot see", "",
            "- a known key that changes meaning or place (a settings key that becomes a "
            "frontmatter field is still known);",
            "- a changed number, limit or default written without a backtick;",
            "- a behaviour change that names no key and no surface listed above;",
            "- a version whose changelog section is not published yet.", ""]
    if fixes:
        out += [f"<details><summary>{len(fixes)} bug-fix lines on the same surfaces"
                "</summary>", ""]
        out += [f"- {v}: {clip(line)}" for v, line in fixes]
        out += ["", "</details>", ""]
    body = "\n".join(out)
    if len(body) > BODY_LIMIT:
        cut = body.rfind("\n", 0, BODY_LIMIT)
        body = (body[:cut] + "\n\n_(truncated: run the script locally for the full list)_\n"
                + ("\n</details>\n" if body.rfind("<details>", 0, cut) > body.rfind("</details>", 0, cut)
                   else ""))
    return body


# ---------- GitHub and Chat (CI only) ----------

def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def list_issues(repo: str) -> list[dict]:
    return json.loads(gh("issue", "list", "--repo", repo, "--label", LABEL, "--state", "all",
                         "--limit", "500", "--json", "number,title,labels,url"))


def create_issue(repo: str, title: str, body: str) -> str:
    """Make sure the label exists, open the issue, return its URL."""
    gh("label", "create", LABEL, "--repo", repo, "--force", "--color", "B60205",
       "--description", "Claude Code release lines the plugin does not cover yet")
    done = subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", title,
                           "--label", LABEL, "--body-file", "-"],
                          input=body, capture_output=True, text=True, check=True)
    return done.stdout.strip().splitlines()[-1]


def notify(title: str, url: str) -> int:
    """POST {"text": ...} to GOOGLE_CHAT_WEBHOOK. Silent when unset.

    Never prints the webhook: its query string holds a key and a token, and a malformed
    value raises errors (ValueError, http.client.InvalidURL) whose message quotes it. Every
    exception is caught and reported by its type and HTTP status only."""
    hook = os.environ.get("GOOGLE_CHAT_WEBHOOK", "").strip()
    if not hook:
        return 0
    data = json.dumps({"text": f"{title}\n{url}"}).encode()
    try:
        request = urllib.request.Request(hook, data=data, method="POST",
                                         headers={"Content-Type": "application/json; charset=UTF-8"})
        with urllib.request.urlopen(request, timeout=30):
            pass
    except Exception as error:   # noqa: BLE001 - any message may quote the secret URL
        code = getattr(error, "code", None)
        code = code if isinstance(code, int) else None
        print(f"chat notification failed: {type(error).__name__} (status {code or 'none'})",
              file=sys.stderr)
        return 1
    print("chat notification sent")
    return 0


def write_output(**values: str) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")


# ---------- main ----------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--create-issue", action="store_true",
                   help="open one issue for the range (needs gh and GH_TOKEN); off by default")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                   help="owner/name whose issues hold the state (default: $GITHUB_REPOSITORY)")
    p.add_argument("--root", type=Path, default=PLUGIN, help="plugin root (default: this checkout)")
    p.add_argument("--changelog", type=Path, help="local CHANGELOG.md instead of fetching it")
    p.add_argument("--npm-json", type=Path, help="local registry document instead of fetching it")
    p.add_argument("--issues-json", type=Path, help="local `gh issue list --json` output")
    p.add_argument("--after", help="override the floor: read versions strictly after this one")
    p.add_argument("--through", help="override npm latest: read versions up to this one")
    p.add_argument("--known-git-rev", help="build the known set from this commit, not the tree")
    p.add_argument("--exclusions", type=Path, default=EXCLUSIONS)
    p.add_argument("--json", action="store_true", help="print the analysis as JSON, not Markdown")
    p.add_argument("--notify", nargs=2, metavar=("TITLE", "URL"),
                   help="only post TITLE and URL to $GOOGLE_CHAT_WEBHOOK, then exit")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.notify:
        return notify(*args.notify)
    if args.create_issue and not args.repo:
        print("--create-issue needs --repo or $GITHUB_REPOSITORY", file=sys.stderr)
        return 2

    if args.through:
        latest, published = args.through, ""
    else:
        raw = args.npm_json.read_bytes() if args.npm_json else fetch(NPM_URL)
        latest, published = npm_latest(json.loads(raw))

    evidence = json.loads((args.root / SKILL / "evidence.json").read_text(encoding="utf-8"))
    baseline = baseline_from_evidence(evidence)
    if args.issues_json:
        issues = json.loads(args.issues_json.read_text(encoding="utf-8"))
    elif args.repo:
        issues = list_issues(args.repo)
    else:
        issues = []
    covered = covered_upto(issues)
    if args.after:
        floor, source = args.after, "--after"
    else:
        floor = floor_version(baseline, covered)
        source = (f"issues cover up to {covered}" if floor == covered and covered
                  else f"baseline: highest version tested in evidence.json, {baseline}")

    text = (args.changelog.read_text(encoding="utf-8") if args.changelog
            else fetch(CHANGELOG_URL).decode("utf-8"))
    sections = split_sections(text)
    problem = format_problem(text, sections, floor)
    if problem:
        print(f"::error::Claude Code changelog format changed: {problem}. "
              "Fix SECTION in .github/scripts/claude_code_watch.py.")
        write_output(issue_url="", issue_title="")
        return EXIT_FORMAT
    versions = new_versions(sections, floor, latest)
    if not versions:
        print(f"nothing new: latest {latest}, floor {floor}"
              + ("" if latest in sections else f"; no changelog section for {latest} yet"))
        write_output(issue_url="", issue_title="")
        return 0

    if args.known_git_rev:
        known, known_source = known_from_git(args.root, args.known_git_rev), \
            f"{SKILL} at {args.known_git_rev}"
    else:
        known, known_source = known_from_tree(args.root), f"{SKILL} as checked out"
    found = analyse(sections, versions, known, load_exclusions(args.exclusions))
    title = title_for(versions)

    if args.json:
        print(json.dumps({"title": title, "versions": versions, "floor": floor,
                          "unknown": sorted(found["unknown"]), "env": sorted(found["env"]),
                          "removals": found["removals"], "surfaces": found["surfaces"],
                          "excluded_seen": found["excluded_seen"]}, indent=1))
    body = render(versions, found, latest=latest, published=published, floor=floor,
                  floor_source=source, known_source=known_source)
    if not args.create_issue:
        if not args.json:
            print(body)
        write_output(issue_url="", issue_title="")
        return 0
    url = create_issue(args.repo, title, body)
    print(f"{title}\n{url}")
    write_output(issue_url=url, issue_title=title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
