"""Markdown as the harness reads it: code spans, fences, links, imports."""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import unquote


def injected_memory(text: str) -> str:
    """A CLAUDE.md as the model receives it: block-level HTML comments removed.

    "Block-level HTML comments are stripped before injection; comments inside code
    blocks are preserved" (memory). Counting them charged the budget for a maintainer
    note that costs nothing - the very place this plugin's references recommend for one.
    """
    out, pos = [], 0
    for a, b in fenced_spans(text):
        out.append(re.sub(r"(?ms)^[ \t]*<!--.*?-->[ \t]*\n?", "", text[pos:a]))
        out.append(text[a:b])
        pos = b
    out.append(re.sub(r"(?ms)^[ \t]*<!--.*?-->[ \t]*\n?", "", text[pos:]))
    return "".join(out)


def strip_code_fences(text: str, indented: bool = False) -> str:
    """The prose of a markdown file: fenced blocks and inline code replaced by spaces.

    Replaced, not removed: removing `` `a`/`b`/`c` `` left `//`, and a sampled public
    repository (2026-09-27) had 15 of 15 "code comment" findings made that way.
    `indented=True` also blanks CommonMark indented code blocks. The documentation says
    import parsing skips "code spans and fenced code blocks" (memory); the CLI 2.1.294
    lexes memory files with marked and skips every `code` token, indented ones included
    (read in its source, 2026-10-08), so memory_imports passes it too (audit externe 3, g7-01).
    """
    chars = list(text)
    spans = fenced_spans(text) + inline_code_spans(text)
    if indented:
        spans += indented_code_spans(text)
    for a, b in spans:
        chars[a:b] = " " * (b - a)
    return "".join(chars)


LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")


def indented_code_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges of CommonMark indented code blocks (4+ spaces or a tab).

    "An indented code block is composed of one or more indented chunks separated by
    blank lines" and "cannot interrupt a paragraph" (CommonMark 0.31.2, 4.4). So a
    chunk opens only after a blank line (or at the top of the file), and never inside
    a list: there an indented line is the item's continuation, not code. Inside a list
    the line stays prose - the conservative side for a check that hunts prose
    (audit externe 2026-10-08, P1-B--07).
    """
    chars = list(text)
    for a, b in fenced_spans(text):
        chars[a:b] = ["\n" if c == "\n" else " " for c in text[a:b]]   # keep the lines
    prose = "".join(chars)
    spans: list[tuple[int, int]] = []
    pos, prev_blank, in_code, in_list = 0, True, False, False
    for line in prose.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        blank = not body.strip()
        is_indented = body.startswith("    ") or body.startswith("\t")
        if blank:
            prev_blank = True
        elif is_indented and (in_code or (prev_blank and not in_list)):
            spans.append((pos, pos + len(body)))
            in_code, prev_blank = True, False
        else:
            in_code = False
            if LIST_ITEM_RE.match(body):
                in_list = True
            elif not is_indented and prev_blank:
                in_list = False         # a paragraph at the margin ends the list
            prev_blank = False
        pos += len(line)
    return spans


# `\ ` is part of a path: "To import a file whose path contains spaces, put a backslash
# before each space" (memory). Stopping at the backslash left `@docs/Dev\ Guide.md`
# unfollowed (audit externe 3, g7-02).
IMPORT_RE = re.compile(r"(?<![\w./@-])@((?:~/|\.{0,2}/)?(?:[\w./@-]|\\ )+\.[A-Za-z0-9]+)\b")


def memory_imports(text: str) -> list[str]:
    """The `@path` imports of a memory file, as the harness parses them.

    "Import parsing skips Markdown code spans and fenced code blocks" (memory): a
    `` `@AGENTS.md` `` names the file, it does not import it. Indented code blocks are
    skipped too (see strip_code_fences). An escaped space is returned unescaped, as the
    path on disk.
    """
    body = strip_code_fences(text, indented=True)
    return [m.group(1).replace("\\ ", " ") for m in IMPORT_RE.finditer(body)]


FENCE_RE = re.compile(r"^ {0,3}(?:[ \t]*)(`{3,}|~{3,})(.*)$")


def fenced_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by fenced code blocks, both fences included.

    CommonMark: a fence is 3+ backticks or tildes; it closes on the SAME character,
    at least as many times, with nothing after it. A ```` ```` ```` block that shows
    ``` ``` ``` blocks is one block - five ad hoc parsers in this file toggled on any
    line starting with three backticks, and read the specimen inside as prose
    (2026-09-27). The one parser every check goes through.
    """
    spans: list[tuple[int, int]] = []
    is_open: tuple[int, str, int] | None = None     # (start, char, length)
    nested = 0
    pos = 0
    for line in text.splitlines(keepends=True):
        m = FENCE_RE.match(line.rstrip("\r\n"))
        if m:
            run, info = m.group(1), m.group(2)
            if is_open is None:
                if not (run[0] == "`" and "`" in info):
                    is_open = (pos, run[0], len(run))
            elif run[0] == is_open[1] and info.strip() and len(run) == is_open[2]:
                # ```markdown ... ```python ... ``` ... ``` : same-length nesting, which
                # CommonMark closes at the first bare fence and authors - models first -
                # write to mean an inner block. The model reads the intent, not the
                # render: 9 of 66 ERRORs on a second public sample were links in the
                # outer example, "outside" only by CommonMark's count (2026-09-27).
                nested += 1
            elif run[0] == is_open[1] and len(run) >= is_open[2] and not info.strip():
                if nested:
                    nested -= 1
                else:
                    spans.append((is_open[0], pos + len(line)))
                    is_open = None
        pos += len(line)
    if is_open is not None:
        spans.append((is_open[0], len(text)))
    return spans


def inline_code_spans(text: str) -> list[tuple[int, int]]:
    """Inline code outside fenced blocks: a run of N backticks closed by a run of exactly N."""
    # Searched in a copy where the fenced blocks are blanked: searched in the raw text,
    # a backtick inside a block paired with one after it, and every inline span of the
    # rest of the file shifted by one (second public sample, 2026-09-27).
    chars = list(text)
    for a, b in fenced_spans(text):
        chars[a:b] = " " * (b - a)
    prose = "".join(chars)
    spans: list[tuple[int, int]] = []
    # Paragraph by paragraph, as CommonMark does: a span never crosses a blank line,
    # and a failed pairing must not swallow the backtick that opens the next one.
    for para in re.finditer(r"(?:[^\n]|\n(?![ \t]*\n))+", prose):
        # `(?<!`)`: a run opens only at its first backtick. Without it the last
        # backtick of "``" opened a span that closed on the next line's first backtick,
        # and every later span shifted by one (sixth public sample, 2026-09-27).
        for m in re.finditer(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", para.group(0), re.S):
            spans.append((para.start() + m.start(), para.start() + m.end()))
    return spans


def in_spans(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def iter_relative_links(text: str) -> Iterable[tuple[str, int]]:
    # A link inside a fenced block is a specimen, not a reference: the file that
    # shows a reader how to write a context map links to the `src/ordering/`
    # the reader will create, not to one that exists here. Verified 2026-09-22
    # on a sampled public repository, where 3 of 9 link errors were examples.
    # Same for inline code (`[Testing](./TESTING.md)` quoted as a style example)
    # and for an elided target (`](...issues/M)`): 6 of the 14 link ERRORs on a
    # 150-repository sample, 2026-09-27, were one or the other.
    spans = fenced_spans(text) + inline_code_spans(text)
    # An HTML comment is not rendered: a usage note in `<!-- … -->` showing what to write
    # in CLAUDE.md, link included, was checked as a link (seventh public sample, 2026-09-27).
    spans += [m.span() for m in re.finditer(r"<!--.*?-->", text, re.S)]
    # `](rules/x.md)` is as relative as `](./rules/x.md)`: only the `./` form was
    # checked, so the same dead link was reported or not by its spelling (2026-09-27).
    # Not a URL (`scheme:`), an anchor (`#`), an absolute path or a `<...>` placeholder.
    for m in re.finditer(r"\]\((?![a-zA-Z][\w+.-]*:|#|/|<)([^)\s]+)", text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        link = m.group(1)
        link = link.split("#", 1)[0]
        # A link target is a URL: `pricing%20guide.md` names `pricing guide.md`. Read raw,
        # it was looked up literally and reported missing (external audit, 2026-10-08).
        if "%" in link:
            link = unquote(link)
        # A bare link with no extension (`](cnspec_run)`) is a docs-site route the
        # generator resolves, not a file: ~75 false ERRORs when it was read as one.
        if not link.startswith(".") and not re.search(r"\.\w{1,5}$", link.split("/")[-1] or "x"):
            continue
        # Inside a quoted sentence the file tells an agent to WRITE ("Please read our
        # [Code of Conduct](CODE_OF_CONDUCT.md)"), the link is text for another repository.
        line_start = text.rfind("\n", 0, m.start()) + 1
        if text.count('"', line_start, m.start()) % 2:
            continue
        if link and not link.startswith("..."):
            yield link, m.start()
