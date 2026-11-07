"""Six-page review packet (JSON + standalone HTML)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import Manifest, Packet
from app.services.compare import CompareResult
from app.services.discovery import DiscoveryResult
from app.services.evaluate import EvaluationResult
from app.services.reconstruction import ReconstructionResult
from app.services.review import ReviewResult

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

DISCLAIMER = (
    "PreFlight is an independent academic research prototype. It is not affiliated with, endorsed by, "
    "sponsored by, or certified by Guidewire Software, Inc. Guidewire, InsuranceSuite, PolicyCenter, "
    "ClaimCenter, BillingCenter, Gosu, Advanced Product Designer (APD), Jutro, Integration Gateway, "
    "Cloud Assurance, Developer Assistants, Guidewire Cloud Platform, and InsuranceNow are trademarks "
    "or registered trademarks of Guidewire Software, Inc. This packet is generated from a synthetic "
    "fixture; it contains no customer data or confidential Guidewire information. Findings are "
    "pattern-based heuristics, not official Cloud Standards checks. Official Cloud Assurance: not run. "
    "Impact ranges are heuristic planning ranges, not quotes."
)

PAGES = [
    "Cover",
    "Executive summary",
    "Coverage and confidence",
    "Assumption register",
    "Findings",
    "Evidence and audit appendix",
]


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rulepack_hash() -> str:
    rules_dir = Path(__file__).resolve().parents[2] / "rules"
    payload = b""
    for path in sorted(rules_dir.glob("*.yaml")):
        payload += path.name.encode("utf-8") + b"\0" + path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def build_packet(*, store, run_id: str, project_id: str, fixture_id: str, release_context: str,
                 manifest: Manifest, discovery: DiscoveryResult, review: ReviewResult,
                 reconstruction: ReconstructionResult | None, comparison: CompareResult | None,
                 evaluation: EvaluationResult | None, reference_path: Path | None = None) -> Packet:
    audit = store.read_audit(run_id)
    audit_head = audit[-1]["hash"] if audit else "GENESIS"
    hashes = {
        "snapshot": manifest.sha256,
        "rulepack": _rulepack_hash(),
        "reference_target": _sha_file(Path(reference_path)) if reference_path and Path(reference_path).is_file() else "not used",
        "audit_head": audit_head,
    }
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    feature_count = len(discovery.features)
    finding_count = len(review.findings)
    mapping_count = len(reconstruction.mappings) if reconstruction else 0
    unsupported_count = len(manifest.unsupported_paths)
    metrics = [m for m in evaluation.metrics if m.primary] if evaluation else []
    assumptions = reconstruction.assumptions if reconstruction else []
    findings = review.findings

    executive_summary = (
        f"{feature_count} feature candidates were assembled from {manifest.file_count} files. "
        f"{finding_count} advisory findings were recorded, each with evidence and a claim-strength label. "
        f"{mapping_count} source properties received an explicit disposition; unresolved items became "
        f"assumptions instead of silent gaps."
    )
    coverage_summary = (
        f"{manifest.file_count - unsupported_count} files parsed; {unsupported_count} unsupported or "
        f"corrupt files are listed in the manifest rather than hidden. Confidence labels are parsed, "
        f"linked, inferred-review, or unresolved. This packet makes no deployability or certification claim."
    )

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("packet_document.html")
    html = template.render(
        run_id=run_id,
        project_id=project_id,
        fixture_id=fixture_id,
        release_context=release_context,
        created_at=now,
        snapshot_hash=manifest.sha256,
        audit_head=audit_head,
        hashes=hashes,
        file_count=manifest.file_count,
        unsupported_count=unsupported_count,
        feature_count=feature_count,
        finding_count=finding_count,
        mapping_count=mapping_count,
        executive_summary=executive_summary,
        coverage_summary=coverage_summary,
        metrics=metrics,
        assumptions=assumptions,
        findings=findings,
        evidence_sample=discovery.evidence[:20],
        disclaimer=DISCLAIMER,
    )

    packet = Packet(
        packet_id=f"PKT-{run_id}",
        run_id=run_id,
        pages=PAGES,
        hashes=hashes,
        audit_head=audit_head,
        disclaimer=DISCLAIMER,
        created_at=now,
    )
    store.write_artifact(run_id, "packet.json", packet.model_dump(mode="json"))
    store.write_artifact(run_id, "packet.html", html)
    return packet
