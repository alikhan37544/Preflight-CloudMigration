"""Line-offset regression tests for scanner and review excerpts."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers.gosu import _blocks, _line_at as gosu_line_at, scan_gosu
from app.services.review import _excerpt_at, _line_at as review_line_at
from app.services.textindex import TextIndex


def _legacy_line_at(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def _legacy_excerpt(source: str, line: int, span: int = 3) -> str:
    lines = source.splitlines()
    start = max(0, line - 1)
    return "\n".join(lines[start:start + span]).strip()


@pytest.mark.parametrize(
    "source",
    [
        "one\ntwo\nthree\n",
        "one\r\ntwo\r\nthree",
        "one\ntwo\nthree",
        "one\r\ntwo\nthree\nfour",
        "",
    ],
)
def test_line_at_matches_newline_count_at_every_position(source: str) -> None:
    index = TextIndex(source)
    for position in range(len(source) + 2):
        expected = _legacy_line_at(source, position)
        assert index.line_at(position) == expected
        assert gosu_line_at(source, position) == expected
        assert review_line_at(source, position) == expected


@pytest.mark.parametrize("line", [1, 2, 3, 4, 99])
def test_excerpt_at_preserves_splitlines_semantics(line: int) -> None:
    source = "  first\r\nsecond line\r\n  third\r\nfourth"
    assert _excerpt_at(source, line) == _legacy_excerpt(source, line)
    assert _excerpt_at(source, line, span=2) == _legacy_excerpt(source, line, span=2)


def test_scan_gosu_crlf_lines_and_no_trailing_newline(tmp_path: Path) -> None:
    source = (
        "package acme\r\n"
        "class BundleCommit {\r\n"
        "  function save() {\r\n"
        "    gw.transaction.Transaction.runWithNewBundle(\\bundle -> {\r\n"
        "      bundle.add(vehicle)\r\n"
        "      bundle.commit()\r\n"
        "    })\r\n"
        "  }\r\n"
        "}"
    )
    path = tmp_path / "BundleCommit.gs"
    path.write_bytes(source.encode("utf-8"))

    doc = scan_gosu(path)
    assert doc.package == "acme"
    assert doc.classes[0].line == 2
    assert doc.classes[0].methods[0].line == 3
    block = doc.find_blocks("runWithNewBundle")[0]
    assert block.start_line == 4
    assert block.commit_line == 6
    assert block.end_line == 7
    assert block.text.startswith("runWithNewBundle")
    assert doc.raw.endswith("}")

    # Direct helper use with a precomputed index produces the same lines.
    assert _blocks(source, source, index=TextIndex(source))[0].commit_line == 6
