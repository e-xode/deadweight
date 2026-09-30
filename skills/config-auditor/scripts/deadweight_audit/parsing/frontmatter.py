"""YAML frontmatter, the subset the harness reads - without a YAML dependency."""
from __future__ import annotations

import re


# YAML booleans the harness accepts: `disable-model-invocation: yes` withholds the
# skill exactly like `true`, and an auditor that only knew `true` miscounted both
# the budget and the index.
YAML_TRUE = {"true", "yes", "on", "1"}


BLOCK_SCALAR_INDICATORS = {">", ">-", ">+", "|", "|-", "|+"}


def _strip_inline_comment(value: str) -> str:
    """YAML ends a plain scalar at ` #`: the rest of the line is a comment.

    `model: sonnet  # needs reasoning` means `sonnet` to Claude Code. Kept whole,
    it was an unknown model - 24 false warnings, and 22 unknown tools from list
    items like `- Glob  # for patterns`, on one calibration sample (2026-09-23).
    A quoted value keeps its `#`.
    """
    v = value.strip()
    if v[:1] in ("'", '"'):
        return v
    m = re.search(r"\s#", v)
    return v[:m.start()].rstrip() if m else v


def parse_frontmatter(text: str) -> tuple[dict[str, str] | None, int]:
    if not text.startswith("---"):
        return None, 0
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, 0
    data: dict[str, str] = {}
    current_key: str | None = None
    buf: list[str] = []
    block_style: str | None = None

    def flush() -> None:
        nonlocal buf, block_style
        if current_key is None:
            # Anything before the first key - a stray comment, a blank line - is
            # discarded rather than left in the buffer. Until 2026-09-22 this branch
            # returned without clearing `buf`, so a comment above `name:` was glued
            # onto the name, and every downstream check then judged a value the file
            # does not contain: 422 false errors on one sampled public repository.
            buf = []
            block_style = None
            return
        if block_style == ">":
            value = " ".join(part for part in (s.strip() for s in buf) if part)
        else:
            value = "\n".join(buf).strip()
        data[current_key] = value.strip().strip('"').strip("'").replace("''", "'")
        buf = []
        block_style = None

    for raw in lines[1:end]:
        # A YAML comment at column 0 is a comment. Indented, it may be content
        # inside a block scalar, so it is only dropped when no block is open.
        if raw.lstrip().startswith("#") and (block_style is None or not raw[:1].isspace()):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:", raw):
            flush()
            key, _, value = raw.partition(":")
            current_key = key.strip()
            scalar = value.strip()
            if scalar in BLOCK_SCALAR_INDICATORS:
                block_style = scalar[0]
            else:
                buf.append(_strip_inline_comment(scalar))
        else:
            buf.append(raw.strip() if block_style else _strip_inline_comment(raw))
    flush()
    return data, end + 1


def frontmatter_keys(text: str) -> list[str]:
    """Top-level frontmatter keys, in file order."""
    if not text.startswith("---"):
        return []
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return []
    keys: list[str] = []
    for raw in lines[1:end]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", raw)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def frontmatter_list(value: str) -> list[str]:
    """Split a frontmatter scalar into items, block-list or inline-list alike."""
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        raw_items = value[1:-1].split(",")
    elif "\n" in value or value.lstrip().startswith("- "):
        raw_items = value.splitlines()
    else:
        raw_items = value.split(",")
    items = []
    for raw in raw_items:
        item = raw.strip()
        if item.startswith("- "):
            item = item[2:]
        item = item.strip().strip("'").strip('"').strip()
        if item:
            items.append(item)
    return items


class _YamlOutOfSubset(Exception):
    """A shape beyond the block subset hooks use: give up rather than guess."""


def yaml_block(lines: list[str]):
    """The block YAML subset hook frontmatter uses: maps, lists of maps, plain scalars.

    Standard library only, like the rest of this script. Flow collections (`{...}`),
    anchors and multi-line scalars raise _YamlOutOfSubset: an auditor that half-parses a
    hook reports hooks that are not there.
    """
    items = [(len(l) - len(l.lstrip(" ")), l.strip()) for l in lines
             if l.strip() and not l.lstrip().startswith("#")]
    def scalar(v: str):
        v = v.strip()
        if v[:1] in "{&*|>" or v.startswith("[") and not v.endswith("]"):
            raise _YamlOutOfSubset(v)
        if v.startswith("[") and v.endswith("]"):
            return [scalar(x) for x in v[1:-1].split(",") if x.strip()]
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            return v[1:-1]
        return v
    def block(i: int, ind: int):
        if i >= len(items):
            return None, i
        if items[i][1].startswith("- "):
            out = []
            while i < len(items) and items[i][0] == ind and items[i][1].startswith("- "):
                rest = items[i][1][2:]
                sub_ind = ind + 2
                if re.match(r"^[\w.-]+:(\s|$)", rest):
                    items[i] = (sub_ind, rest)
                    val, i = mapping(i, sub_ind)
                else:
                    val, i = scalar(rest), i + 1
                out.append(val)
            return out, i
        return mapping(i, ind)
    def mapping(i: int, ind: int):
        out = {}
        while i < len(items) and items[i][0] == ind and not items[i][1].startswith("- "):
            m = re.match(r"^([\w.-]+):(?:\s+(.*))?$", items[i][1])
            if not m:
                raise _YamlOutOfSubset(items[i][1])
            key, val = m.group(1), m.group(2)
            i += 1
            if val not in (None, ""):
                out[key] = scalar(val)
            elif i < len(items) and items[i][0] > ind:
                out[key], i = block(i, items[i][0])
            elif i < len(items) and items[i][0] == ind and items[i][1].startswith("- "):
                out[key], i = block(i, ind)
            else:
                out[key] = None
        return out, i
    if not items:
        return {}
    val, i = block(0, items[0][0])
    if i != len(items):
        raise _YamlOutOfSubset(items[i][1])
    return val


def frontmatter_hooks(text: str):
    """The `hooks:` block of a frontmatter, parsed; None when there is none or it is out of subset."""
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    end_ = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end_ is None:
        return None
    fm = lines[1:end_]
    start = next((i for i, l in enumerate(fm) if re.match(r"^hooks:\s*$", l)), None)
    if start is None:
        return None
    body = []
    for l in fm[start + 1:]:
        if l.strip() and not l.startswith((" ", "\t")):
            break
        body.append(l)
    try:
        return yaml_block(body)
    except (_YamlOutOfSubset, IndexError):
        return None
