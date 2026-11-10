"""Reusable line indexing for scanner/review hot paths.

``source.count("\\n", 0, position) + 1`` is quadratic when called once per class
or finding. ``TextIndex`` records every newline offset once and resolves line
numbers with a binary search. ``lines`` keeps the exact ``str.splitlines()``
view used for excerpts, so CRLF and missing trailing newlines behave as before.
"""

from __future__ import annotations

from bisect import bisect_right


class TextIndex:
    """Line starts for a text, with lazy ``splitlines`` storage."""

    __slots__ = ("text", "line_starts", "_lines")

    def __init__(self, text: str) -> None:
        self.text = text
        starts = [0]
        find = text.find
        position = find("\n")
        while position != -1:
            starts.append(position + 1)
            position = find("\n", position + 1)
        self.line_starts = starts
        self._lines: list[str] | None = None

    def line_at(self, position: int) -> int:
        """Return the 1-based line containing ``position``.

        Newline characters belong to the line they terminate, matching
        ``text.count("\\n", 0, position) + 1``.
        """
        if position < 0:
            position = 0
        return bisect_right(self.line_starts, position)

    @property
    def lines(self) -> list[str]:
        if self._lines is None:
            self._lines = self.text.splitlines()
        return self._lines

    def excerpt(self, line: int, span: int = 3) -> str:
        lines = self.lines
        start = max(0, line - 1)
        return "\n".join(lines[start:start + span]).strip()
