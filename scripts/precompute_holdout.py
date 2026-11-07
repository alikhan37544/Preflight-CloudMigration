"""Pre-compute the holdout aggregate once, before freeze.

The demo pipeline never scans the holdout; evaluation reads this aggregate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.discovery import run_discovery
from app.services.intake import build_manifest

REPO = Path(__file__).resolve().parents[1]


def tree_hash(root: Path) -> str:
    pairs = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            pairs.append((path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    payload = json.dumps(pairs, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    root = REPO / "fixtures" / "northstar-pc-2026.10"
    manifest = build_manifest(root, snapshot_id="S-HOLDOUT", project_id="holdout")
    discovery = run_discovery(root, manifest)
    gold = json.loads((REPO / "ground_truth" / "holdout_features.json").read_text(encoding="utf-8"))
    found = {f.capability for f in discovery.features if f.capability}
    expected = {f["capability"] for f in gold["features"]}
    payload = {
        "schema_version": "1.0",
        "fixture": "northstar-pc-2026.10",
        "numerator": len(found & expected),
        "denominator": len(expected),
        "capabilities": sorted(found),
        "holdout_sha256": tree_hash(root),
        "computed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "caveat": "Pre-computed holdout aggregate; not imported into the demo or used for tuning.",
    }
    out = REPO / "ground_truth" / "holdout_metrics.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
