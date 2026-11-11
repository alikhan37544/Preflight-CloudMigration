"""Freeze fixture, reference-target, annotation-guide, and rule-pack hashes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "ground_truth" / "FROZEN.json"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(root: Path) -> str:
    pairs = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            pairs.append((path.relative_to(root).as_posix(), sha_file(path)))
    payload = json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def rulepack_hash() -> str:
    """Hash the frozen review rule pack.

    The code-migration pack (``codebase_rules.yaml``) is versioned with the
    codebase lab, not with the sealed review-run rule pack. Excluding it keeps
    the pre-registered demo hashes reproducible after the additive feature.
    """
    payload = b""
    for path in sorted((REPO / "rules").glob("*.yaml")):
        if path.name == "codebase_rules.yaml":
            continue
        payload += path.name.encode() + b"\0" + path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def freeze() -> dict:
    fixtures = {}
    for name in ["acme-pc-2026.10", "demo-slice-300", "northstar-pc-2026.10"]:
        root = REPO / "fixtures" / name
        fixtures[name] = {
            "sha256": tree_hash(root),
            "files": sum(1 for p in root.rglob("*") if p.is_file()),
        }
    reference = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"
    gold_files = [
        "features.json", "mappings.json", "findings.json", "gaps.json",
        "estimate_moving_issues.json", "holdout_metrics.json", "holdout_features.json",
        "pa_veh_01_edges.json", "annotation_concordance.json",
    ]
    payload = {
        "schema_version": "1.0",
        "status": "frozen",
        "frozen_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commit": git_commit(),
        "author": "PreFlight Build",
        "fixtures": fixtures,
        "reference_target_sha256": sha_file(reference),
        "annotation_guide_sha256": sha_file(REPO / "ground_truth" / "ANNOTATION_GUIDE.md"),
        "annotation_concordance_sha256": sha_file(REPO / "ground_truth" / "annotation_concordance.json"),
        "rulepack_sha256": rulepack_hash(),
        "pre_registration_sha256": sha_file(REPO / "ground_truth" / "PRE_REGISTRATION.md"),
        "claims_ledger_sha256": sha_file(REPO / "docs" / "claims-ledger.json"),
        "gold": {name: sha_file(REPO / "ground_truth" / name) for name in gold_files},
        "change_log": [
            {"date": datetime.now(timezone.utc).date().isoformat(), "change": "Frozen demo-tier fixtures and rule pack."}
        ],
    }
    FROZEN.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    data = freeze()
    print(json.dumps(data, indent=2))
