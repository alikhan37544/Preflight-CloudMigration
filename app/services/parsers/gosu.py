"""Comment/string-aware Gosu scanner.

This is deliberately a scanner, not a parser. It masks comments and string
literals so detection rules cannot fire on prose or text, then extracts
packages, imports, classes, methods, calls, and brace-matched blocks.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services.parsers.base import (
    GosuBlock,
    GosuClass,
    GosuMethod,
    ParsedGUnit,
    ParsedGosu,
)
from app.services.textindex import TextIndex

_PACKAGE = re.compile(r"(?m)^\s*package\s+([\w.]+)")
_IMPORT = re.compile(r"(?m)^\s*(?:uses|import)\s+([\w.*]+)")
_CLASS = re.compile(r"\bclass\s+([A-Za-z_]\w*)(?:\s+extends\s+([A-Za-z_]\w*))?")
_FUNCTION = re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\(")
_CALL = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\(")


def mask_source(source: str) -> str:
    """Replace comments and string literals with spaces, preserving layout."""
    out = list(source)
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char == "/" and index + 1 < length and source[index + 1] == "/":
            while index < length and source[index] != "\n":
                out[index] = " "
                index += 1
        elif char == "/" and index + 1 < length and source[index + 1] == "*":
            out[index] = " "
            out[index + 1] = " "
            index += 2
            while index + 1 < length and not (source[index] == "*" and source[index + 1] == "/"):
                if source[index] != "\n":
                    out[index] = " "
                index += 1
            if index + 1 < length:
                out[index] = " "
                out[index + 1] = " "
                index += 2
        elif char in {'"', "'"}:
            quote = char
            out[index] = " "
            index += 1
            while index < length:
                if source[index] == "\\":
                    out[index] = " "
                    index += 1
                    if index < length and source[index] != "\n":
                        out[index] = " "
                        index += 1
                elif source[index] == quote:
                    out[index] = " "
                    index += 1
                    break
                else:
                    if source[index] != "\n":
                        out[index] = " "
                    index += 1
        else:
            index += 1
    return "".join(out)


def mask_comments(source: str) -> str:
    """Mask comments but preserve string literals (for value inspection)."""
    out = list(source)
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char in {'"', "'"}:
            quote = char
            index += 1
            while index < length:
                if source[index] == "\\":
                    index += 2
                elif source[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
        elif char == "/" and index + 1 < length and source[index + 1] == "/":
            while index < length and source[index] != "\n":
                out[index] = " "
                index += 1
        elif char == "/" and index + 1 < length and source[index + 1] == "*":
            out[index] = " "
            out[index + 1] = " "
            index += 2
            while index + 1 < length and not (source[index] == "*" and source[index + 1] == "/"):
                if source[index] != "\n":
                    out[index] = " "
                index += 1
            if index + 1 < length:
                out[index] = " "
                out[index + 1] = " "
                index += 2
        else:
            index += 1
    return "".join(out)


def _line_at(source: str, position: int, index: TextIndex | None = None) -> int:
    if index is None:
        index = TextIndex(source)
    return index.line_at(position)


def _match_brace(masked: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(masked)):
        char = masked[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _blocks(source: str, masked: str, call: str = "runWithNewBundle",
            index: TextIndex | None = None) -> list[GosuBlock]:
    if index is None:
        index = TextIndex(source)
    blocks: list[GosuBlock] = []
    for match in re.finditer(r"\b" + re.escape(call) + r"\s*\(", masked):
        prefix = masked[max(0, match.start() - 40):match.start()]
        if re.search(r"\bfunction\s+$", prefix):
            continue
        open_index = masked.find("{", match.end())
        if open_index == -1:
            continue
        between = masked[match.end():open_index]
        if "->" not in between:
            continue
        close_index = _match_brace(masked, open_index)
        if close_index == -1:
            continue
        start_line = _line_at(source, match.start(), index)
        end_line = _line_at(source, close_index, index)
        commit_lines = [
            _line_at(source, match.start() + commit.start(), index)
            for commit in re.finditer(r"\bcommit\s*\(", masked[match.start():close_index])
        ]
        blocks.append(
            GosuBlock(
                call=call,
                start_line=start_line,
                end_line=end_line,
                commit_line=commit_lines[0] if commit_lines else None,
                text=source[match.start():close_index + 1],
                commit_lines=commit_lines,
            )
        )
    return blocks


def scan_gosu(path: Path) -> ParsedGosu:
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    index = TextIndex(raw)
    masked = mask_source(raw)
    package_match = _PACKAGE.search(masked)
    imports = [m.group(1) for m in _IMPORT.finditer(masked)]

    classes: list[GosuClass] = []
    for match in _CLASS.finditer(masked):
        name = match.group(1)
        base = match.group(2)
        open_index = masked.find("{", match.end())
        if open_index == -1:
            continue
        close_index = _match_brace(masked, open_index)
        if close_index == -1:
            continue
        body = masked[open_index:close_index]
        methods = [
            GosuMethod(name=m.group(1), line=_line_at(raw, open_index + m.start(), index))
            for m in _FUNCTION.finditer(body)
        ]
        classes.append(
            GosuClass(name=name, base=base, line=_line_at(raw, match.start(), index),
                      methods=methods)
        )

    calls = [f"{m.group(1)}.{m.group(2)}" for m in _CALL.finditer(masked)]
    return ParsedGosu(
        path=str(path),
        package=package_match.group(1) if package_match else None,
        imports=imports,
        raw=raw,
        masked=masked,
        classes=classes,
        calls=calls,
        blocks=_blocks(raw, masked, index=index),
    )


DB_TOKENS = [
    "Query.make", "Query.select", "Query.add", "loadSampleData",
    ".commit(", "DriverManager.getConnection",
]


def parse_gunit(path: Path) -> ParsedGUnit:
    doc = scan_gosu(path)
    if not doc.classes:
        raise ValueError(f"no test class found in {path}")
    test_class = doc.classes[0]
    db_calls: list[str] = []
    for token in DB_TOKENS:
        if token in doc.masked:
            db_calls.append(token.lstrip("."))
    return ParsedGUnit(
        path=str(path),
        class_name=test_class.name,
        base_class=test_class.base,
        methods=[m.name for m in test_class.methods],
        db_calls=db_calls,
    )
