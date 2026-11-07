"""A23: holdout isolation and rule-leakage checks."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings

REPO = Path(__file__).resolve().parents[1]


def test_holdout_filenames_are_not_in_rules() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in (REPO / "rules").glob("*.yaml"))
    for literal in ["AutoVehicle", "AutoDriver", "AutoCoverage", "AutoPolicyQuestions", "northstar"]:
        assert literal not in text, literal


def test_demo_config_uses_demo_slice() -> None:
    seed = (REPO / "scripts" / "seed_demo.py").read_text(encoding="utf-8")
    assert "demo-slice-300" in seed
    assert "northstar" not in seed


def test_holdout_is_not_an_importable_fixture() -> None:
    assert "northstar-pc-2026.10" not in Settings().allowed_fixtures


def test_ground_truth_holdout_is_labelled() -> None:
    import json

    payload = json.loads((REPO / "ground_truth" / "holdout_features.json").read_text(encoding="utf-8"))
    assert payload["holdout"] is True
    assert "never" in payload["note"].lower()
