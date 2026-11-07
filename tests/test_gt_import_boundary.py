"""Ground-truth import boundary: product code must not import evaluation gold."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_app_code_does_not_import_ground_truth() -> None:
    offenders = []
    for path in (REPO / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import ground_truth" in text or "from ground_truth" in text:
            offenders.append(path)
    assert offenders == []
