"""Runtime configuration for the PreFlight product."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_FALLBACK_SECRET = secrets.token_urlsafe(32)


def _default_secret_key() -> str:
    return os.environ.get("PREFLIGHT_SECRET_KEY") or _FALLBACK_SECRET


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
    secret_key: str = field(default_factory=_default_secret_key)
    sync_runs: bool = False
    tier: str = "demo"
    release_context: str = "Qusar 2026.08 (review context)"
    host: str = field(default_factory=lambda: os.environ.get("PREFLIGHT_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("PREFLIGHT_PORT", "8000")))
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "testserver")
    allowed_origins: tuple[str, ...] = ()
    allowed_fixtures: tuple[str, ...] = (
        "demo-slice-300", "acme-pc-2026.10",
    )
    max_upload_bytes: int = 500 * 1024 * 1024
    # Optional evidence-locked AI QCer. Default is fully offline/deterministic.
    ai_provider: str = field(default_factory=lambda: os.environ.get("PREFLIGHT_AI_PROVIDER", "none"))
    ai_model: str = field(default_factory=lambda: os.environ.get("PREFLIGHT_AI_MODEL", ""))
    ai_base_url: str = field(default_factory=lambda: os.environ.get(
        "PREFLIGHT_AI_BASE_URL", "http://127.0.0.1:11434"
    ))
    ai_api_key: str = field(default_factory=lambda: os.environ.get("PREFLIGHT_AI_API_KEY", ""))
    ai_timeout: float = field(default_factory=lambda: float(os.environ.get("PREFLIGHT_AI_TIMEOUT", "90")))
    ai_allow_remote: bool = field(default_factory=lambda: os.environ.get("PREFLIGHT_AI_ALLOW_REMOTE", "") == "1")

    def __post_init__(self) -> None:
        if not self.allowed_origins:
            configured = f"http://{self.host}:{self.port}"
            self.allowed_origins = tuple(dict.fromkeys((
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "http://testserver",
                configured,
            )))
