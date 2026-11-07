"""Runtime configuration for the PreFlight product."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("PREFLIGHT_DATA_DIR", REPO / "data")))
    fixtures_dir: Path = field(default_factory=lambda: Path(os.environ.get("PREFLIGHT_FIXTURES_DIR", REPO / "fixtures")))
    ground_truth_dir: Path = field(default_factory=lambda: REPO / "ground_truth")
    reference_path: Path | None = field(
        default_factory=lambda: Path(os.environ.get(
            "PREFLIGHT_REFERENCE_PATH",
            REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json",
        ))
    )
    secret_key: str = "local-development-secret"
    sync_runs: bool = False
    tier: str = "demo"
    release_context: str = "Qusar 2026.08 (review context)"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    allowed_fixtures: tuple[str, ...] = (
        "demo-slice-300", "acme-pc-2026.10",
    )
    max_upload_bytes: int = 500 * 1024 * 1024
