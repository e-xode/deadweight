"""Path globs as rule `paths:` and other tools' `applyTo`/`globs` write them."""
from __future__ import annotations

import re
from typing import Iterable


def expand_braces(pattern: str) -> list[str]:
    """Expand `{a,b}` alternatives into one pattern per branch."""
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    head, tail = pattern[: m.start()], pattern[m.end() :]
    expanded: list[str] = []
    for option in m.group(1).split(","):
        expanded.extend(expand_braces(head + option + tail))
    return expanded


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile one brace-free glob, with `**` spanning path segments."""
    segments = pattern.split("/")
    out: list[str] = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            out.append(".*" if last else "(?:.*/)?")
            continue
        compiled = ""
        pos = 0
        while pos < len(segment):
            char = segment[pos]
            if char == "*":
                compiled += "[^/]*"
            elif char == "?":
                compiled += "[^/]"
            elif char == "[":
                close = segment.find("]", pos + 1)
                if close == -1:
                    compiled += re.escape(char)
                else:
                    body = segment[pos + 1 : close]
                    compiled += "[" + ("^" + body[1:] if body.startswith("!") else body) + "]"
                    pos = close
            else:
                compiled += re.escape(char)
            pos += 1
        out.append(compiled if last else compiled + "/")
    return re.compile("^" + "".join(out) + "$")


def glob_match_count(pattern: str, files: Iterable[str]) -> int:
    files = list(files)
    matched: set[str] = set()
    for branch in expand_braces(pattern):
        regex = glob_to_regex(branch)
        matched.update(path for path in files if regex.match(path))
    return len(matched)
