"""Seed the pre-computed demo run used by the live product demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import REPO, Settings
from app.services.pipeline import execute_run
from app.services.migrator import run_migration
from app.store import RunStore

RUN_ID = "R-DEMO-001"


def seed(data: Path, fixture_id: str = "demo-slice-300", force: bool = True):
    store = RunStore(data)
    if store.run_dir(RUN_ID).exists():
        if not force:
            return None
        store.delete_run(RUN_ID)
    store.create_run(RUN_ID, project_id="demo", snapshot_id=f"S-{RUN_ID}", fixture_id=fixture_id)
    fixture = REPO / "fixtures" / fixture_id
    reference = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"
    result = execute_run(
        fixture, store, RUN_ID, project_id="demo", fixture_id=fixture_id,
        tier="demo", reference_path=reference,
        release_context=Settings().release_context,
    )
    # The migrator is part of the seeded demo: it writes a separate agent log
    # and bundle, and leaves the review-run audit at its original seed count.
    run_migration(store, RUN_ID, pace=0.0)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the PreFlight demo run")
    parser.add_argument("--data", type=Path, default=Settings().data_dir)
    parser.add_argument("--fixture", default="demo-slice-300")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    result = seed(args.data, args.fixture, force=args.force)
    if result is None:
        print(f"{RUN_ID} already exists at {RunStore(args.data).run_dir(RUN_ID)}")
        return 0
    print(f"Seeded {RUN_ID} with {len(result.discovery.features)} features, "
          f"{len(result.review.findings)} findings, "
          f"{len(result.reconstruction.mappings) if result.reconstruction else 0} mappings.")
    print(f"Open http://127.0.0.1:8000/?run={RUN_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
