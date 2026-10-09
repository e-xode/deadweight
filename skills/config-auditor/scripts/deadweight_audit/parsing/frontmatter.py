"""YAML frontmatter, the subset the harness reads - without a YAML dependency."""
from __future__ import annotations

import re


# YAML booleans the harness accepts: `disable-model-invocation: yes` withholds the
# skill exactly like `true`, and an auditor that only knew `true` miscounted both
# the budget and the index.
YAML_TRUE = {"true", "yes", "on", "1"}


BLOCK_SCALAR_INDICATORS = {">", ">-", ">+", "|", "|-", "|+"}
# A block-scalar header may also carry an indentation digit, before or after the
# chomping sign (YAML 1.2, 8.1.1): `>2`, `|2-`, `>-2`. Knowing only the six bare forms
# left `>2` inside the value, and 02 blamed a valid file for the parser's limit.
BLOCK_SCALAR_HEADER = re.compile(r"^[>|](?:[1-9][+-]?|[+-][1-9]?)?$")


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
            if BLOCK_SCALAR_HEADER.match(_strip_inline_comment(scalar)):
                block_style = scalar[0]
            else:
                buf.append(_strip_inline_comment(scalar))
        else:
            buf.append(raw.strip() if block_style else _strip_inline_comment(raw))
    flush()
    return data, end + 1


def frontmatter_raw_value(text: str, key: str) -> str | None:
    """The text after `key:` on its own line, unparsed: quotes and headers kept.

    parse_frontmatter strips quotes, so `"> Refund policy"` and `> Refund policy` come
    out the same; a check that must tell a quoted value from a raw one reads this.
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    for raw in lines[1:end or 1]:
        m = re.match(rf"^{re.escape(key)}\s*:(.*)$", raw)
        if m:
            return m.group(1).strip()
    return None


# Escapes a YAML double-quoted scalar accepts (YAML 1.2, 5.7); any other one is a
# parse error - `"\q"` was rejected by `claude plugin validate` 2.1.294.
_DQ_ESCAPES = set('0abt\tnvfre "/\\N_LPxuU')


def _close_quote(s: str, q: str) -> int | None:
    """Index just past the closing quote of a scalar opened before `s`, or None."""
    i = 0
    while i < len(s):
        c = s[i]
        if q == '"' and c == "\\":
            if i + 1 < len(s) and s[i + 1] not in _DQ_ESCAPES:
                raise ValueError(f"invalid escape '\\{s[i + 1]}' in a double-quoted value")
            i += 2
            continue
        if c == q:
            if q == "'" and s[i + 1:i + 2] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _drop_comment(s: str) -> str:
    """`s` without a trailing ` # ...` comment; whitespace before the `#` is kept."""
    m = re.search(r"(?<=\s)#", s)
    return s[:m.start()] if m else s


def _flow_scan(s: str, depth: int) -> tuple[int, str]:
    """Bracket depth of a flow collection after `s`, and the text after its closer.

    Brackets inside quotes or after a ` #` comment do not count.
    """
    quote = ""
    prev = "["                       # a quote opens a scalar only where an item starts
    for i, c in enumerate(s):
        if quote:
            if c == quote:
                quote = ""
            continue
        if c.isspace():
            continue
        last, prev = prev, c
        if c in "\"'" and last in "[{,:":
            quote = c
        elif c == "#" and (i == 0 or s[i - 1].isspace()):
            break
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth <= 0:
                return 0, s[i + 1:].strip()
    return depth, ""


def frontmatter_yaml_error(text: str) -> str | None:
    """Why the frontmatter would not parse in Claude Code, or None.

    parse_frontmatter is tolerant on purpose and reads fields out of a frontmatter the
    harness rejects whole. Claude Code is tolerant too, but not in the same places:
    `claude plugin validate` 2.1.294 ACCEPTS a plain value holding ': ' or starting with
    '>' or '{', and REJECTS each shape below ("YAML frontmatter failed to parse ... At
    runtime this agent does not load at all"). Only measured rejections are listed - a
    strict YAML parser would condemn files that load, which is worse than silence.
    Comments (whole lines, or after ` #`) and the inside of a `[...]`/`{...}` spread over
    several lines are not judged by the ':' tests: the validator accepts them, and
    reading them as values gave false ERRORs (audit 3, g3-00).
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    state: str | None = None         # "plain", "block", "quoted", "flow", or another value
    quote = ""
    block_indented = False
    flow_depth = 0
    where = ""
    try:
        for n, raw in enumerate(lines[1:end], start=2):
            where = f"line {n}"
            if state == "flow":
                # Inside an open `[`/`{`: items hold ':' freely and the closer may sit at
                # column 0 - both pass the validator. Measured rejections: a column-0 line
                # that is neither a key, a closer nor a comment (`tools: [Read,` / `Grep]`),
                # and text after the closer on its line. A column-0 key ends the matter:
                # `tools: [Read` then `model: sonnet` passes, so it is read as a key.
                if not raw.strip() or raw.lstrip().startswith("#"):
                    continue
                col0_key = re.match(r"^[^\s#'\"?\-\]}][^:]*?:(?=\s|$)", raw)
                if not col0_key:
                    if raw[:1] not in (" ", "\t") and raw[:1] not in "]}":
                        return f"{where}: a line at column 0 inside an open '[' or '{{'"
                    flow_depth, rest = _flow_scan(raw, flow_depth)
                    if flow_depth <= 0:
                        if rest and not rest.startswith("#"):
                            return f"{where}: text after the closing bracket"
                        state = "plain"     # what follows a closed collection is judged as base did
                    continue
                state = "other"
            if state == "quoted":
                close = _close_quote(raw, quote)
                if close is None:
                    continue
                rest = raw[close:].strip()
                if rest and not rest.startswith("#"):
                    return f"{where}: text after the closing quote"
                state = "other"
                continue
            if not raw.strip():
                continue
            indented = raw[:1] in (" ", "\t")
            # A comment line ends nothing and says nothing, at any indentation, outside a
            # block scalar (where it is text). `  # TODO: tighten` under a plain value
            # passes the validator; read as text, its ':' was a false ERROR (audit 3, g3-00).
            if raw.startswith("#") or (raw.lstrip().startswith("#") and state != "block"):
                continue
            # A YAML key may hold spaces: `Not for:` at column 0 is a key with a null value.
            key = re.match(r"^[^\s#'\"?-][^:]*?:(?=\s|$)(.*)$", raw)
            if key and not indented:
                value = key.group(1)
                v = value.strip()
                state, block_indented = "other", False
                if not v or v.startswith("#"):
                    continue
                if v[0] in "\"'":
                    close = _close_quote(v[1:], v[0])
                    if close is None:
                        state, quote = "quoted", v[0]
                        continue
                    rest = v[1 + close:].strip()
                    if rest and not rest.startswith("#"):
                        return f"{where}: text after the closing quote"
                elif BLOCK_SCALAR_HEADER.match(_strip_inline_comment(v)):
                    state = "block"
                elif re.match(r"^[-?](\s|$)", v):
                    return f"{where}: a value opening with '{v[0]} ', read as a nested collection"
                elif v[0] in "[{":
                    flow_depth, _ = _flow_scan(v, 0)
                    state = "flow" if flow_depth > 0 else "plain"
                elif re.search(r":\t*$", _drop_comment(value)):
                    # `Not for:` fails, `Not for: ` (trailing space) passes - measured both.
                    # A trailing comment is not the value: `model: sonnet # was opus:` passes.
                    return f"{where}: an unquoted value ending with ':'"
                else:
                    state = "plain"
                continue
            if indented:
                if state == "block":
                    block_indented = True
                elif state == "plain":
                    body = _drop_comment(raw).strip()
                    if ": " in body or ":\t" in body or body.endswith(":"):
                        return (f"{where}: an indented line holding ':' under an unquoted value "
                                "(a key indented by mistake, or a value to quote)")
                continue
            # Column 0, not a key: fatal after a plain value or an empty block header.
            if state == "plain" or (state == "block" and not block_indented):
                return f"{where}: a line at column 0 that is not a 'key: value'"
        if state == "quoted":
            return "a quoted value is never closed"
    except ValueError as exc:
        return f"{where}: {exc}"
    return None


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
        # A flow list splits on its TOP-LEVEL commas only: `["src/**/*.{ts,tsx}"]` is one
        # item in YAML, and the documented brace glob was cut in two (audit 2026-10-08).
        raw_items = _split_flow_items(value[1:-1])
    elif "\n" in value or value.lstrip().startswith("- "):
        raw_items = value.splitlines()
    else:
        # Plain comma form: split outside parentheses only. `Agent(worker, researcher), Read`
        # is two entries in the sub-agents docs' own example. Braces are left alone here:
        # what Claude Code makes of `paths: a/{b,c}` written this way is not measured.
        raw_items = _split_flow_items(value, braces=False)
    items = []
    for raw in raw_items:
        item = raw.strip()
        if item.startswith("- "):
            item = item[2:]
        item = item.strip().strip("'").strip('"').strip()
        if item:
            items.append(item)
    return items


def _split_flow_items(body: str, braces: bool = True) -> list[str]:
    """Split a list body on commas outside quotes, `(...)` groups and, in a YAML flow list
    (`braces=True`), `{...}` groups."""
    items: list[str] = []
    current = ""
    quote = ""
    depth = 0
    for char in body:
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'" and not current.strip():
            quote = char
        elif char == "(" or (braces and char == "{"):
            depth += 1
        elif (char == ")" or (braces and char == "}")) and depth:
            depth -= 1
        elif char == "," and not depth:
            items.append(current)
            current = ""
            continue
        current += char
    items.append(current)
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
