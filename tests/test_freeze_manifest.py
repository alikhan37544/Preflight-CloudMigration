"""Freeze-manifest integrity gate: every recorded hash is recomputed."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.freeze import rulepack_hash, sha_file, tree_hash

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "ground_truth" / "FROZEN.json"


def test_frozen_manifest_is_complete_and_matches_files() -> None:
    data = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert data["status"] == "frozen", "run: python scripts/freeze.py"
    assert data["commit"]
    assert data["frozen_at"]
    for name, entry in data["fixtures"].items():
        root = REPO / "fixtures" / name
        assert root.is_dir()
        assert sum(1 for p in root.rglob("*") if p.is_file()) == entry["files"]
        assert tree_hash(root) == entry["sha256"], name
    reference = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"
    assert sha_file(reference) == data["reference_target_sha256"]
    assert sha_file(REPO / "ground_truth" / "ANNOTATION_GUIDE.md") == data["annotation_guide_sha256"]
    assert sha_file(REPO / "ground_truth" / "annotation_concordance.json") == data["annotation_concordance_sha256"]
    assert rulepack_hash() == data["rulepack_sha256"]
    assert sha_file(REPO / "ground_truth" / "PRE_REGISTRATION.md") == data["pre_registration_sha256"]
    assert sha_file(REPO / "docs" / "claims-ledger.json") == data["claims_ledger_sha256"]
    assert data["gold"]
    for name, recorded in data["gold"].items():
        assert sha_file(REPO / "ground_truth" / name) == recorded, name
