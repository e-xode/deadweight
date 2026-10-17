"""Vocabulary drift: the lists the auditor hard-codes, against the raw Claude Code docs.

    python3 .github/scripts/vocabulary_drift.py                # report; exit 1 on drift
    python3 .github/scripts/vocabulary_drift.py --json         # the same, as JSON
    python3 .github/scripts/vocabulary_drift.py --pages DIR    # read DIR/<page>.md, no network
    python3 .github/scripts/vocabulary_drift.py --markdown     # the issue section
    python3 .github/scripts/vocabulary_drift.py --attach FILE --repo OWNER/NAME [--issue-url URL]
                                                               # CI only: put FILE in an issue

Why. An auditor that enumerates what is valid drifts toward false as the harness moves:
every tool, field or setting the docs add becomes a false positive in every project that
uses it, with no change to the plugin. A date written next to a list is not a check.

Each list is read from the package as checked out
(skills/config-auditor/scripts/deadweight_audit/vocabulary) and compared with names
extracted by a fixed pattern from the RAW Markdown page (https://code.claude.com/docs/en/
<page>.md), never from a summary: a paraphrase cannot be diffed. Deterministic, standard
library only, no model and no API key.

Verdicts, per list:
  ok         the two sets are equal;
  drift      they differ (both directions are listed);
  unparsed   the page was read but the pattern found nothing: the page changed shape and
             this script must be fixed - counted as drift, it needs a maintainer;
  unchecked  the page could not be downloaded: NOT drift, nothing is known.

Exit status: 10 if any list is drift or unparsed; otherwise 3 if any is unchecked; 0.
Drift is 10, not 1, because Python exits 1 on any uncaught exception: a crash must never
be read as drift (the workflow attaches the section only on 10). --attach exits 2, and
touches no issue, when FILE is empty or is not one whole section between the markers.

What it does not compare: lists with no table or bullet list to read them from (the
per-event handler types of PermissionRequest, SessionStart and Setup are prose; timeouts,
aliases written in prose other than the marketplace pair; tool aliases and removals; the
model aliases of model-config).
"""
from __future__ import annotations

import argparse
import http.client
import importlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent
SCRIPTS = Path("skills") / "config-auditor" / "scripts"

sys.path.insert(0, str(HERE))
import claude_code_watch as watch  # noqa: E402  - label, body limit, gh, issue creation

DOCS = "https://code.claude.com/docs/en/{}.md"
START = "<!-- vocabulary-drift:start -->"
END = "<!-- vocabulary-drift:end -->"
STANDING_TITLE = f"{watch.TITLE_PREFIX}: documentation vocabulary"  # no version: not a range
NAMES_SHOWN = 40
EXIT_DRIFT, EXIT_UNCHECKED = 10, 3   # 1 is what a traceback exits with

# Docs Scope column -> the package list that holds the keys of that scope.
SCOPE_LISTS = {
    "Any file": "SETTINGS_KEYS_ANY",
    "User, local, or managed": "SETTINGS_KEYS_USER_LOCAL_MANAGED",
    "User": "SETTINGS_KEYS_USER",
    "User or managed": "SETTINGS_KEYS_USER_MANAGED",
    "Managed": "SETTINGS_KEYS_MANAGED",
    "Global config": "SETTINGS_KEYS_GLOBAL",
}
CMD_HTTP_MCP = frozenset({"command", "http", "mcp_tool"})


# ---------- the only network access ----------

def fetch_page(name: str) -> str:
    """One raw docs page. The docs host answers 403 to urllib's default User-Agent."""
    request = urllib.request.Request(DOCS.format(name), headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def directory_reader(directory: Path) -> Callable[[str], str]:
    """A page reader over saved pages: DIR/<page>.md. A missing file raises, as a 404 would."""
    def read(name: str) -> str:
        return (directory / f"{name}.md").read_text(encoding="utf-8")
    return read


# ---------- the package side ----------

def load_vocabulary(root: Path) -> dict[str, set[str]]:
    """Every list compared below, from the vocabulary package under `root`."""
    sys.path.insert(0, str(root / SCRIPTS))
    tools = importlib.import_module("deadweight_audit.vocabulary.tools")
    front = importlib.import_module("deadweight_audit.vocabulary.frontmatter")
    hooks = importlib.import_module("deadweight_audit.vocabulary.hooks")
    settings = importlib.import_module("deadweight_audit.vocabulary.settings")
    typed = hooks.HOOK_EVENT_TYPES
    vocab = {
        "KNOWN_TOOLS": set(tools.KNOWN_TOOLS),
        "AGENT_KNOWN_KEYS": set(front.AGENT_KNOWN_KEYS),
        "SKILL_KNOWN_KEYS": set(front.SKILL_KNOWN_KEYS),
        "KNOWN_HOOK_EVENTS": set(hooks.KNOWN_HOOK_EVENTS),
        "KNOWN_MODEL_TIERS": set(tools.KNOWN_MODEL_TIERS),
        "SETTINGS_KNOWN_KEYS": set(settings.SETTINGS_KNOWN_KEYS),
        "HOOK_HANDLER_TYPES": set(hooks.HOOK_TYPE_FIELDS),
        "HOOK_EVENTS_ALL_TYPES": set(hooks.KNOWN_HOOK_EVENTS) - set(typed),
        "HOOK_EVENTS_CMD_HTTP_MCP": {e for e, t in typed.items() if set(t) == CMD_HTTP_MCP},
        "AGENT_PERMISSION_MODES": set(front.AGENT_PERMISSION_MODES),
        "SETTINGS_SCOPES": set(SCOPE_LISTS),
    }
    for name in SCOPE_LISTS.values():
        vocab[name] = set(getattr(settings, name))
    return vocab


# ---------- the docs side: one extractor per list ----------

def names(text: str, pattern: str) -> set[str]:
    return set(re.findall(pattern, text, re.M))


def table_cell(text: str, row_prefix: str, index: int) -> str:
    """Cell `index` (split on '|') of the first line starting with row_prefix, or ''."""
    line = next((raw for raw in text.splitlines() if raw.startswith(row_prefix)), "")
    cells = line.split("|")
    return cells[index] if len(cells) > index else ""


def bullets_after(text: str, lead: str) -> set[str]:
    """The `* `Name`` bullets of the list that follows the paragraph starting with lead."""
    lines = text.splitlines()
    start = next((i for i, raw in enumerate(lines) if raw.startswith(lead)), None)
    found: set[str] = set()
    if start is None:
        return found
    for raw in lines[start + 1:]:
        item = re.fullmatch(r"[*-] `([A-Z][A-Za-z]+)`\s*", raw)
        if item:
            found.add(item.group(1))
        elif raw.strip() and found:
            break
        elif raw.strip():
            return set()
    return found


def settings_rows(text: str) -> dict[str, str]:
    """key -> its Scope cell (the last column of the settings-reference key table)."""
    rows: dict[str, str] = {}
    for raw in text.splitlines():
        head = re.match(r"^\| \[`([A-Za-z][A-Za-z0-9.]*)`\]", raw)
        if head:
            rows[head.group(1)] = raw.rstrip().rstrip("|").split(" | ")[-1].strip()
    return rows


def settings_aliases(text: str) -> set[str]:
    """Aliases written in prose: "you can write `extraKnownMarketplaces` as `additional...`"."""
    return {alias for raw in text.splitlines() if "you can write `" in raw
            for alias in re.findall(r"`[A-Za-z]+` as `([A-Za-z]+)`", raw)}


def model_tiers(text: str) -> set[str]:
    cell = table_cell(text, "| `model`", 3)
    found = set(re.findall(r"`([a-z]+)`", cell)) - {"model"}
    return found | {"inherit"} if found else found


def handler_types(text: str) -> set[str]:
    """The `type` row of the common hook fields, the one listing the most values."""
    best: set[str] = set()
    for raw in text.splitlines():
        if raw.startswith("| `type` | yes |"):
            values = set(re.findall(r'`"([a-z_]+)"`', raw))
            if len(values) > len(best):
                best = values
    return best


def scope_extractor(label: str) -> Callable[[str], set[str] | None]:
    """Keys of one scope; None when the key table itself is gone (unparsed)."""
    def extract(text: str) -> set[str] | None:
        rows = settings_rows(text)
        return {key for key, scope in rows.items() if scope == label} if rows else None
    return extract


@dataclass(frozen=True)
class Comparison:
    name: str
    page: str
    extract: Callable[[str], set[str] | None]   # None or an empty set: unparsed
    drop_from_ours: Callable[[str], set[str]] | None = None   # package names this table omits
    note: str = ""
    may_be_empty: bool = False  # an empty set is a verdict (a scope the docs no longer use)


COMPARISONS: tuple[Comparison, ...] = (
    # The six of the maintainer's derive.py, with the same patterns.
    Comparison("KNOWN_TOOLS", "tools-reference",
               lambda t: names(t, r"^\| `([A-Z][A-Za-z]+)` +\|")),
    Comparison("AGENT_KNOWN_KEYS", "sub-agents",
               lambda t: names(t, r"^\| `([a-zA-Z]+)`(?:\.[a-zA-Z]+)? +\| (?:Yes|No) ")),
    Comparison("SKILL_KNOWN_KEYS", "skills",
               lambda t: names(t, r"^\| `([a-z_-]+)` +\| (?:Yes|No|Recommended) ")),
    Comparison("KNOWN_HOOK_EVENTS", "hooks",
               lambda t: names(t, r"^### ([A-Z][A-Za-z]+)\s*$")
               & set(re.findall(r"`([A-Z][A-Za-z]+)`", t))),
    Comparison("KNOWN_MODEL_TIERS", "sub-agents", model_tiers,
               note="the `model` row of the frontmatter table, plus `inherit`"),
    Comparison("SETTINGS_KNOWN_KEYS", "settings-reference",
               lambda t: names(t, r"^\| \[`([A-Za-z][A-Za-z0-9.]*)`\]") | settings_aliases(t),
               note="the key table plus the aliases written in prose"),
    # Not in derive.py: lists the docs give as a table row or a bullet list.
    Comparison("HOOK_HANDLER_TYPES", "hooks", handler_types,
               note="the `type` row of the common hook fields; package: HOOK_TYPE_FIELDS"),
    Comparison("HOOK_EVENTS_ALL_TYPES", "hooks",
               lambda t: bullets_after(t, "Events that support all five hook types"),
               note="package: events absent from HOOK_EVENT_TYPES"),
    Comparison("HOOK_EVENTS_CMD_HTTP_MCP", "hooks",
               lambda t: bullets_after(t, "Events that support `command`, `http`, and "
                                          "`mcp_tool` hooks but not"),
               note="package: HOOK_EVENT_TYPES entries equal to command, http, mcp_tool"),
    Comparison("AGENT_PERMISSION_MODES", "sub-agents",
               lambda t: set(re.findall(r"`([A-Za-z]+)`", table_cell(t, "| `permissionMode`", 3)))
               - {"permissionMode"},
               note="the `permissionMode` row of the frontmatter table"),
    Comparison("SETTINGS_SCOPES", "settings-reference",
               lambda t: set(settings_rows(t).values()),
               note="the Scope values of the key table; package: the lists this script maps"),
    *(Comparison(list_name, "settings-reference", scope_extractor(label),
                 drop_from_ours=settings_aliases, may_be_empty=True,
                 note=f"keys whose Scope is \"{label}\"; prose aliases left out")
      for label, list_name in SCOPE_LISTS.items()),
)


# ---------- comparing ----------

@dataclass
class Result:
    name: str
    page: str
    verdict: str                      # ok | drift | unparsed | unchecked
    docs: int = 0
    ours: int = 0
    missing: list[str] = field(default_factory=list)   # in the docs, not in the package
    extra: list[str] = field(default_factory=list)     # in the package, not in the docs
    error: str = ""
    note: str = ""


def describe(error: BaseException) -> str:
    code = getattr(error, "code", None)
    return (type(error).__name__ + (f" {code}" if code else "") + f": {error}")[:200]


def compare(read: Callable[[str], str], vocab: dict[str, set[str]],
            comparisons: tuple[Comparison, ...] = COMPARISONS) -> list[Result]:
    pages: dict[str, str | BaseException] = {}
    results: list[Result] = []
    for comp in comparisons:
        if comp.page not in pages:
            try:
                pages[comp.page] = read(comp.page)
            except (urllib.error.URLError, OSError, UnicodeDecodeError, ValueError,
                    http.client.HTTPException) as error:   # IncompleteRead: a partial download
                pages[comp.page] = error
        text = pages[comp.page]
        ours = set(vocab.get(comp.name, set()))
        if isinstance(text, BaseException):
            results.append(Result(comp.name, comp.page, "unchecked", ours=len(ours),
                                  error=describe(text), note=comp.note))
            continue
        if comp.drop_from_ours:
            ours -= comp.drop_from_ours(text)
        doc = comp.extract(text)
        if doc is None or (not doc and not comp.may_be_empty):
            results.append(Result(comp.name, comp.page, "unparsed", ours=len(ours),
                                  note=comp.note))
            continue
        missing, extra = sorted(doc - ours), sorted(ours - doc)
        results.append(Result(comp.name, comp.page, "drift" if missing or extra else "ok",
                              docs=len(doc), ours=len(ours), missing=missing, extra=extra,
                              note=comp.note))
    return results


def exit_code(results: list[Result]) -> int:
    if any(r.verdict in ("drift", "unparsed") for r in results):
        return EXIT_DRIFT
    if any(r.verdict == "unchecked" for r in results):
        return EXIT_UNCHECKED
    return 0


# ---------- output ----------

def shown(items: list[str]) -> str:
    head = ", ".join(items[:NAMES_SHOWN])
    return head + (f" (+{len(items) - NAMES_SHOWN} more)" if len(items) > NAMES_SHOWN else "")


def render_text(results: list[Result]) -> str:
    out: list[str] = []
    for r in results:
        if r.verdict == "ok":
            out.append(f"  ok        {r.name:34} {r.docs}")
        elif r.verdict == "drift":
            out.append(f"  DRIFT     {r.name:34} docs {r.docs}, package {r.ours}")
            if r.missing:
                out.append(f"            in the docs, not in the package: {shown(r.missing)}")
            if r.extra:
                out.append(f"            in the package, not in the docs: {shown(r.extra)}")
        elif r.verdict == "unparsed":
            out.append(f"  UNPARSED  {r.name:34} nothing extracted from {r.page}.md - "
                       "the page changed shape; fix the pattern")
        else:
            out.append(f"  UNCHECKED {r.name:34} could not read {r.page}.md ({r.error})")
    drift = sum(r.verdict in ("drift", "unparsed") for r in results)
    unchecked = sum(r.verdict == "unchecked" for r in results)
    out += ["", f"{drift} list(s) out of step with the docs, {unchecked} could not be checked, "
            f"{len(results)} compared."]
    return "\n".join(out)


def render_markdown(results: list[Result]) -> str:
    bad = [r for r in results if r.verdict in ("drift", "unparsed")]
    unchecked = [r for r in results if r.verdict == "unchecked"]
    out = [START, f"## Vocabulary out of step with the documentation ({len(bad)} of "
           f"{len(results)} lists)", "",
           "Generated by `.github/scripts/vocabulary_drift.py`, without a model: the lists of "
           "`skills/config-auditor/scripts/deadweight_audit/vocabulary` against names extracted "
           "from the raw docs pages. Each item is a lead to check, not a finding.", ""]
    for r in bad:
        if r.verdict == "unparsed":
            out.append(f"- [ ] `{r.name}` ({r.page}): nothing extracted - the page changed "
                       "shape, the pattern needs fixing.")
            continue
        line = f"- [ ] `{r.name}` ({r.page}): docs {r.docs}, package {r.ours}."
        if r.missing:
            line += " In the docs, not in the package: " + shown([f"`{n}`" for n in r.missing]) + "."
        if r.extra:
            line += " In the package, not in the docs: " + shown([f"`{n}`" for n in r.extra]) + "."
        out.append(watch.neutralise(line))   # no length cut: shown() bounds the names
    if not bad:
        out.append("None.")
    if unchecked:
        out += ["", "Could not be checked (page not downloaded - not drift): "
                + ", ".join(f"`{r.name}` ({r.page})" for r in unchecked) + "."]
    ok = [r.name for r in results if r.verdict == "ok"]
    if ok:
        out += ["", "In step: " + ", ".join(f"`{n}`" for n in ok) + "."]
    out += ["", END]
    return "\n".join(out)


def as_json(results: list[Result]) -> str:
    return json.dumps({"exit": exit_code(results), "results": [r.__dict__ for r in results]},
                      indent=1)


# ---------- the issue (CI only) ----------

def merge_section(body: str, section: str) -> str:
    """Replace a previous section, or append one; keep the body under GitHub's limit."""
    if START in body and END in body:
        before, rest = body.split(START, 1)
        body = before.rstrip() + "\n\n" + rest.split(END, 1)[1].lstrip()
    room = watch.BODY_LIMIT - len(body) - 4
    if len(section) > room:
        cut = section.rfind("\n", 0, max(room - 120, 0))
        section = (section[:cut] + "\n\n_(truncated: run the script locally for the full list)_\n"
                   + END) if cut > 0 else ""
    return body.rstrip() + ("\n\n" + section + "\n" if section else "\n")


def find_standing_issue(repo: str) -> str:
    issues = json.loads(watch.gh("issue", "list", "--repo", repo, "--label", watch.LABEL,
                                 "--state", "open", "--limit", "200", "--json", "title,url"))
    return next((i["url"] for i in issues if i.get("title") == STANDING_TITLE), "")


def valid_section(section: str) -> bool:
    """One whole --markdown output: starts with START, ends with END, something between."""
    text = section.strip()
    return (text.startswith(START) and text.endswith(END) and text.count(START) == 1
            and text.count(END) == 1 and len(text) > len(START) + len(END) + 1)


def attach(section: str, repo: str, issue_url: str) -> str:
    """Put the section in the watch's issue, or in the one standing vocabulary issue."""
    if not valid_section(section):
        raise ValueError("not a vocabulary section: empty, or markers missing")
    target = issue_url or find_standing_issue(repo)
    if not target:
        url = watch.create_issue(repo, STANDING_TITLE, merge_section("", section))
        watch.write_output(drift_issue_url=url)
        return url
    body = json.loads(watch.gh("issue", "view", target, "--repo", repo, "--json", "body"))["body"]
    subprocess.run(["gh", "issue", "edit", target, "--repo", repo, "--body-file", "-"],
                   input=merge_section(body or "", section), capture_output=True, text=True,
                   check=True)
    watch.write_output(drift_issue_url=target)
    return target


# ---------- main ----------

def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--root", type=Path, default=PLUGIN, help="plugin root (default: this checkout)")
    p.add_argument("--pages", type=Path, help="read saved pages DIR/<page>.md instead of fetching")
    out = p.add_mutually_exclusive_group()
    out.add_argument("--json", action="store_true", help="print the results as JSON")
    out.add_argument("--markdown", action="store_true", help="print the issue section")
    p.add_argument("--attach", type=Path, metavar="FILE",
                   help="CI only: put FILE (a --markdown output) in an issue, then exit")
    p.add_argument("--repo", default="", help="owner/name for --attach")
    p.add_argument("--issue-url", default="",
                   help="the watch's issue for this run; empty: the standing vocabulary issue")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.attach:
        if not args.repo:
            print("--attach needs --repo", file=sys.stderr)
            return 2
        section = args.attach.read_text(encoding="utf-8") if args.attach.is_file() else ""
        if not valid_section(section):
            print(f"::error::--attach: {args.attach} is empty or not one vocabulary section; "
                  "no issue was touched")
            return 2
        print(attach(section, args.repo, args.issue_url))
        return 0
    read = directory_reader(args.pages) if args.pages else fetch_page
    results = compare(read, load_vocabulary(args.root))
    if args.json:
        print(as_json(results))
    elif args.markdown:
        print(render_markdown(results))
    else:
        print(render_text(results))
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
