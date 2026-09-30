"""Markdown as the harness reads it: code spans, fences, links, imports."""
from __future__ import annotations

import re
from typing import Iterable


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


def strip_code_fences(text: str) -> str:
    """The prose of a markdown file: fenced blocks and inline code replaced by spaces.

    Replaced, not removed: removing `` `a`/`b`/`c` `` left `//`, and a sampled public
    repository (2026-09-27) had 15 of 15 "code comment" findings made that way.
    """
    chars = list(text)
    for a, b in fenced_spans(text) + inline_code_spans(text):
        chars[a:b] = " " * (b - a)
    return "".join(chars)


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
