"""Six-page review packet (JSON + standalone HTML).

The packet is an evidence-complete, self-verifying artifact: every hash and
audit count is captured at generation time, the audit chain is verified before
the packet is written, and the packet JSON carries its own canonical content
hash. A broken audit chain fails the build rather than producing a packet that
merely looks complete.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import ArtifactStatus, Evidence, Manifest, Packet
from app.services.compare import CompareResult
from app.services.discovery import DiscoveryResult
from app.services.evaluate import EvaluationResult
from app.services.reconstruction import ReconstructionResult
from app.services.redaction import redact_excerpt
from app.services.review import ReviewResult

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
REPO = Path(__file__).resolve().parents[2]
FROZEN_MANIFEST = REPO / "ground_truth" / "FROZEN.json"

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

PACKET_HASH_SCOPE = (
    "SHA-256 over the canonical packet JSON payload (sorted keys, compact separators), "
    "excluding packet_sha256 and hashes.packet. It covers run identity, page list, counts, "
    "all other artifact hashes, audit verification and event count, disclaimer, and created_at. "
    "It does not cover the rendered HTML wrapper or external source files."
)

UNSUPPORTED_STATUSES = {
    ArtifactStatus.UNSUPPORTED,
    ArtifactStatus.BINARY,
    ArtifactStatus.CORRUPT,
    ArtifactStatus.EXCLUDED,
}


class PacketIntegrityError(RuntimeError):
    """Raised when a packet would certify an unverifiable audit chain."""


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rulepack_hash() -> str:
    rules_dir = REPO / "rules"
    payload = b""
    for path in sorted(rules_dir.glob("*.yaml")):
        payload += path.name.encode("utf-8") + b"\0" + path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def _ground_truth_hash() -> str:
    if FROZEN_MANIFEST.is_file():
        return _sha_file(FROZEN_MANIFEST)
    return "not available"


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def packet_content_hash(packet_payload: dict) -> str:
    """Recompute the packet hash from its canonical payload.

    ``packet_sha256`` and ``hashes.packet`` are excluded so the stored hash is
    reproducible from the packet JSON without a circular dependency.
    """
    payload = {key: value for key, value in packet_payload.items() if key != "packet_sha256"}
    hashes = dict(payload.get("hashes") or {})
    hashes.pop("packet", None)
    hashes.pop("packet_sha256", None)
    payload["hashes"] = hashes
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _locator_text(evidence: Evidence) -> str:
    locator = evidence.locator
    kind = getattr(locator.kind, "value", str(locator.kind))
    text = f"{kind}: {locator.value}"
    if locator.line and str(locator.line) not in locator.value:
        text += f" (line {locator.line})"
    return text


def _source_ref(evidence: Evidence) -> str:
    if evidence.locator.line:
        return f"{evidence.path}:{evidence.locator.line}"
    return evidence.path


def _evidence_view(evidence: Evidence) -> dict:
    excerpt, changed = redact_excerpt(evidence.excerpt)
    excerpt_sha = evidence.excerpt_sha
    if changed:
        excerpt_sha = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    return {
        "evidence_id": evidence.evidence_id,
        "path": evidence.path,
        "source": _source_ref(evidence),
        "locator": _locator_text(evidence),
        "excerpt": excerpt,
        "excerpt_sha": excerpt_sha,
        "confidence": getattr(evidence.confidence, "value", str(evidence.confidence)),
        "method": evidence.method,
        "redacted": evidence.redacted or changed,
    }


def _finding_view(finding, evidence_by_id: dict[str, Evidence]) -> dict:
    evidence = [
        _evidence_view(evidence_by_id[evidence_id])
        for evidence_id in finding.evidence_ids
        if evidence_id in evidence_by_id
    ]
    message, _ = redact_excerpt(finding.message)
    return {
        "finding": finding,
        "message": message,
        "evidence": evidence,
        "sources": [item["source"] for item in evidence],
        "source": evidence[0]["source"] if evidence else "no source locator",
        "claim_strength": getattr(finding.claim_strength, "value", str(finding.claim_strength)),
        "standard": finding.standard_id or finding.standard_title or finding.standard_url or "none",
        "standard_title": finding.standard_title,
        "standard_url": finding.standard_url,
    }


def _excluded_files(manifest: Manifest) -> list[dict]:
    artifacts = {artifact.path: artifact for artifact in manifest.artifacts}
    paths = set(manifest.unsupported_paths)
    paths.update(
        artifact.path for artifact in manifest.artifacts
        if artifact.status in UNSUPPORTED_STATUSES
    )
    reasons = {
        ArtifactStatus.BINARY: "Binary content; not parsed.",
        ArtifactStatus.UNSUPPORTED: "File type is outside the supported parsers.",
        ArtifactStatus.CORRUPT: "Parser could not read the file.",
        ArtifactStatus.EXCLUDED: "Excluded by the snapshot policy.",
    }
    rows = []
    for path in sorted(paths):
        artifact = artifacts.get(path)
        if artifact is None:
            rows.append({
                "path": path,
                "status": "unsupported",
                "kind": "unknown",
                "reason": "Listed in the manifest but absent from parsed artifacts.",
            })
            continue
        reason = "; ".join(artifact.warnings) or reasons.get(
            artifact.status, f"Status {artifact.status.value}; not included in analysis."
        )
        rows.append({
            "path": artifact.path,
            "status": artifact.status.value,
            "kind": artifact.kind,
            "reason": reason,
        })
    return rows


def build_packet(*, store, run_id: str, project_id: str, fixture_id: str, release_context: str,
                 manifest: Manifest, discovery: DiscoveryResult, review: ReviewResult,
                 reconstruction: ReconstructionResult | None, comparison: CompareResult | None,
                 evaluation: EvaluationResult | None, reference_path: Path | None = None,
                 reference_sha256: str | None = None) -> Packet:
    audit = store.read_audit(run_id)
    audit_verified = store.verify_audit(run_id)
    if not audit_verified:
        raise PacketIntegrityError(
            f"audit chain for {run_id} did not verify; refusing to build a review packet"
        )
    audit_head = audit[-1]["hash"] if audit else "GENESIS"

    if reference_sha256 is not None:
        reference_hash = reference_sha256
    elif reference_path and Path(reference_path).is_file():
        reference_hash = _sha_file(Path(reference_path))
    else:
        reference_hash = "not used"

    hashes = {
        "snapshot": manifest.sha256,
        "rulepack": _rulepack_hash(),
        "reference_target": reference_hash,
        "ground_truth_manifest": _ground_truth_hash(),
        "audit_head": audit_head,
    }
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    feature_count = len(discovery.features)
    finding_count = len(review.findings)
    readiness_count = len(review.readiness)
    mapping_count = len(reconstruction.mappings) if reconstruction else 0
    change_count = len(reconstruction.changes) if reconstruction else 0
    unsupported_count = len(manifest.unsupported_paths)
    metrics = [m for m in evaluation.metrics if m.primary] if evaluation else []
    assumptions = reconstruction.assumptions if reconstruction else []
    mappings = reconstruction.mappings if reconstruction else []
    changes = reconstruction.changes if reconstruction else []
    findings = review.findings

    evidence_by_id = {item.evidence_id: item for item in review.evidence}
    finding_views = [_finding_view(finding, evidence_by_id) for finding in findings]
    readiness_views = [_finding_view(finding, evidence_by_id) for finding in review.readiness]

    finding_groups = []
    for rule_id in sorted({finding.rule_id for finding in findings}):
        group_findings = [finding for finding in findings if finding.rule_id == rule_id]
        first = group_findings[0]
        finding_groups.append({
            "rule_id": rule_id,
            "title": first.title,
            "severity": first.severity.value,
            "claim_strength": first.claim_strength.value,
            "standard_id": first.standard_id,
            "standard_title": first.standard_title,
            "standard_url": first.standard_url,
            "findings": [
                view for view in finding_views if view["finding"].rule_id == rule_id
            ],
        })

    linked_findings: dict[str, set[str]] = defaultdict(set)
    for finding in findings + review.readiness:
        for evidence_id in finding.evidence_ids:
            linked_findings[evidence_id].add(finding.finding_id)

    review_evidence_views = []
    for evidence in sorted(review.evidence, key=lambda item: item.evidence_id):
        view = _evidence_view(evidence)
        view["linked_findings"] = sorted(linked_findings.get(evidence.evidence_id, []))
        review_evidence_views.append(view)

    discovery_evidence_views = [
        _evidence_view(evidence)
        for evidence in sorted(discovery.evidence, key=lambda item: item.evidence_id)
    ]

    audit_rows = []
    for event in audit:
        previous = event.get("prev_hash") or ""
        audit_rows.append({
            "seq": event.get("seq"),
            "ts": event.get("ts"),
            "action": event.get("action"),
            "actor": event.get("actor", "system"),
            "object": f"{event.get('object_type')}:{event.get('object_id')}",
            "hash": (event.get("hash") or "")[:16],
            "prev_hash": previous[:16],
        })

    excluded_files = _excluded_files(manifest)

    counts = {
        "files": manifest.file_count,
        "unsupported_files": len(excluded_files),
        "features": feature_count,
        "findings": finding_count,
        "readiness": readiness_count,
        "rules": len(finding_groups),
        "mappings": mapping_count,
        "changes": change_count,
        "assumptions": len(assumptions),
        "discovery_evidence": len(discovery.evidence),
        "review_evidence": len(review.evidence),
        "evidence": len(discovery.evidence) + len(review.evidence),
        "audit_events": len(audit),
        "metrics": len(metrics),
    }

    executive_summary = (
        f"{feature_count} feature candidates were assembled from {manifest.file_count} files. "
        f"{finding_count} advisory findings and {readiness_count} readiness flags were recorded, "
        f"each with evidence and a claim-strength label. {mapping_count} source properties received "
        f"an explicit disposition and {change_count} target changes await approval; unresolved items "
        f"became assumptions instead of silent gaps."
    )
    coverage_summary = (
        f"{manifest.file_count - unsupported_count} files parsed; {unsupported_count} unsupported or "
        f"corrupt files are listed below rather than hidden. Confidence labels are parsed, linked, "
        f"inferred-review, or unresolved. This packet makes no deployability or certification claim."
    )

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("packet_document.html")

    packet = Packet(
        packet_id=f"PKT-{run_id}",
        run_id=run_id,
        pages=PAGES,
        hashes=dict(hashes),
        audit_head=audit_head,
        disclaimer=DISCLAIMER,
        created_at=now,
        counts=counts,
        audit_verified=True,
        audit_event_count=len(audit),
        hash_scope=PACKET_HASH_SCOPE,
    )
    packet_sha256 = packet_content_hash(packet.model_dump(mode="json"))
    packet.hashes["packet"] = packet_sha256
    packet.packet_sha256 = packet_sha256

    html = template.render(
        run_id=run_id,
        project_id=project_id,
        fixture_id=fixture_id,
        release_context=release_context,
        created_at=now,
        snapshot_hash=manifest.sha256,
        audit_head=audit_head,
        hashes=packet.hashes,
        packet_sha256=packet_sha256,
        hash_scope=PACKET_HASH_SCOPE,
        counts=counts,
        file_count=manifest.file_count,
        unsupported_count=unsupported_count,
        feature_count=feature_count,
        finding_count=finding_count,
        readiness_count=readiness_count,
        mapping_count=mapping_count,
        change_count=change_count,
        executive_summary=executive_summary,
        coverage_summary=coverage_summary,
        metrics=metrics,
        assumptions=assumptions,
        findings=findings,
        finding_groups=finding_groups,
        readiness=review.readiness,
        readiness_views=readiness_views,
        mappings=mappings,
        changes=changes,
        excluded_files=excluded_files,
        discovery_evidence=discovery_evidence_views,
        review_evidence=review_evidence_views,
        evidence_count=len(discovery_evidence_views) + len(review_evidence_views),
        audit_events=audit_rows,
        audit_event_count=len(audit_rows),
        audit_verified=audit_verified,
        disclaimer=DISCLAIMER,
    )

    store.write_artifact(run_id, "packet.json", packet.model_dump(mode="json"))
    store.write_artifact(run_id, "packet.html", html)
    return packet
