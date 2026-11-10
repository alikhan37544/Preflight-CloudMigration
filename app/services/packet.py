"""Six-page review packet (JSON + standalone HTML).

The packet is an evidence-complete, self-verifying artifact. ``packet_sha256``
(also stored as ``hashes.packet`` and ``hashes.packet_html``) is the SHA-256 of
the complete rendered HTML after normalizing the packet's own hash fields.
``hashes.packet_json`` separately covers the canonical packet JSON. Neither
digest is a digest of the other format. Content digests bind the packet to the
persisted findings/mappings/evidence, and the audit chain is verified before the
packet is written. A broken audit chain fails the build rather than producing a
packet that merely looks complete.
"""

from __future__ import annotations

import hashlib
import re
import json
from collections import defaultdict
from datetime import datetime, timezone
from html import escape as html_escape, unescape as html_unescape
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

CLOUD_RETROFIT_BOUNDARY = (
    "Cloud Retrofit without APD App; not Guidewire's recommended process; local, "
    "non-deployable draft; field-level nameOverride only applies on this path."
)

PACKET_HASH_PLACEHOLDER = "__PACKET_SHA256__"

PACKET_HASH_SCOPE = (
    "SHA-256 over the complete rendered packet HTML after normalizing the packet hash fields to "
    "a fixed placeholder. packet_sha256 and hashes.packet_html are the same value. The canonical "
    "packet JSON is covered separately by hashes.packet_json (excluding packet_sha256 and the "
    "packet/packet_html/packet_json hash entries), and hashes.findings, hashes.mappings, "
    "hashes.evidence and the other content digests bind the artifact payloads to the packet."
)

# Persisted artifacts whose canonical content digest is carried by the packet.
# (hash key, artifact name, list key in the artifact payload)
CONTENT_ARTIFACTS = (
    ("features", "features.json", "features"),
    ("findings", "findings.json", "findings"),
    ("readiness", "findings.json", "readiness"),
    ("mappings", "mappings.json", "mappings"),
    ("changes", "changes.json", "changes"),
    ("assumptions", "assumptions.json", "assumptions"),
    ("evidence", "evidence.json", "evidence"),
    ("review_evidence", "review_evidence.json", "evidence"),
    ("gaps", "gaps.json", "gaps"),
)

HASH_EXCLUDED_KEYS = {"packet", "packet_html", "packet_json"}

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


def _hash_payload(payload) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def packet_content_hash(packet_payload: dict) -> str:
    """Recompute the canonical packet-JSON hash from the packet payload.

    ``packet_sha256`` and the packet/packet_html/packet_json hash entries are
    excluded so the stored JSON hash is reproducible from the packet without a
    circular dependency. The rendered HTML has its own digest
    (:func:`packet_html_hash`).
    """
    payload = {key: value for key, value in packet_payload.items() if key != "packet_sha256"}
    hashes = dict(payload.get("hashes") or {})
    for key in HASH_EXCLUDED_KEYS:
        hashes.pop(key, None)
    payload["hashes"] = hashes
    return _hash_payload(payload)


def packet_html_hash(html: str, expected_hash: str | None) -> str:
    """Hash complete rendered HTML with the packet hash fields normalized.

    The packet document contains its own digest. Hashing the final document
    directly would therefore be circular, so every occurrence of ``expected_hash``
    is replaced with a fixed placeholder before hashing. Verification recomputes
    this value from the stored hash and the bytes currently on disk; changing any
    other byte in the document changes the digest.
    """
    canonical = html
    if expected_hash:
        canonical = canonical.replace(expected_hash, PACKET_HASH_PLACEHOLDER)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _content_hashes(*, discovery: DiscoveryResult, review: ReviewResult,
                    reconstruction: ReconstructionResult | None) -> dict[str, str]:
    mappings = reconstruction.mappings if reconstruction else []
    changes = reconstruction.changes if reconstruction else []
    assumptions = reconstruction.assumptions if reconstruction else []
    return {
        "features": _hash_payload([f.model_dump(mode="json") for f in discovery.features]),
        "findings": _hash_payload([f.model_dump(mode="json") for f in review.findings]),
        "readiness": _hash_payload([f.model_dump(mode="json") for f in review.readiness]),
        "mappings": _hash_payload([m.model_dump(mode="json", by_alias=True) for m in mappings]),
        "changes": _hash_payload([c.model_dump(mode="json") for c in changes]),
        "assumptions": _hash_payload([a.model_dump(mode="json") for a in assumptions]),
        "evidence": _hash_payload([e.model_dump(mode="json") for e in discovery.evidence]),
        "review_evidence": _hash_payload([e.model_dump(mode="json") for e in review.evidence]),
        "gaps": _hash_payload([g.model_dump(mode="json") for g in discovery.gaps]),
    }


def verify_packet_artifacts(store, run_id: str, *, include_content: bool = False,
                            include_audit: bool = True) -> tuple[bool, str | None]:
    """Verify the packet's own hashes, the live audit chain, and optionally content.

    Returns ``(True, None)`` or ``(False, reason)``. The self-hash checks catch
    edits to either packet.html or packet.json. ``include_content`` additionally
    compares the content digests captured at build time with the current
    persisted findings/mappings/evidence artifacts. A packet is never treated as
    verified merely because the files exist.
    """
    try:
        packet = store.read_artifact(run_id, "packet.json")
        html = store.read_artifact(run_id, "packet.html")
    except Exception as exc:  # StoreError or unreadable output
        return False, f"packet artifacts are unreadable: {exc}"
    if not isinstance(packet, dict) or not isinstance(html, str):
        return False, "packet artifacts do not have the expected shape"
    expected = packet.get("packet_sha256")
    hashes = packet.get("hashes")
    if not isinstance(expected, str) or len(expected) != 64:
        return False, "packet_sha256 is missing or malformed"
    if not isinstance(hashes, dict):
        return False, "packet hashes are missing"
    if hashes.get("packet_html") != expected:
        return False, "hashes.packet_html does not match packet_sha256"
    if hashes.get("packet") != expected:
        return False, "hashes.packet does not match packet_sha256"
    actual_html = packet_html_hash(html, expected)
    if actual_html != expected:
        return False, (
            "rendered packet.html SHA-256 does not match packet_sha256 "
            f"(expected {expected[:12]}..., observed {actual_html[:12]}...)"
        )
    stored_json_hash = hashes.get("packet_json")
    actual_json_hash = packet_content_hash(packet)
    if not isinstance(stored_json_hash, str) or actual_json_hash != stored_json_hash:
        return False, (
            "packet.json canonical content SHA-256 does not match hashes.packet_json "
            "(the packet metadata or a content digest was edited)"
        )
    if include_audit:
        if packet.get("audit_verified") is not True:
            return False, "packet does not record a verified audit chain"
        try:
            audit = store.read_audit(run_id)
            live_head = audit[-1]["hash"] if audit else "GENESIS"
        except Exception as exc:
            return False, f"audit log is unreadable: {exc}"
        if packet.get("audit_head") != live_head:
            return False, "packet audit head does not match the live audit log"
        if not store.verify_audit(run_id):
            return False, "audit chain does not verify"
    if include_content:
        for key, artifact_name, list_key in CONTENT_ARTIFACTS:
            try:
                payload = store.read_artifact(run_id, artifact_name)
            except Exception as exc:
                return False, f"content artifact {artifact_name!r} is unreadable: {exc}"
            items = payload.get(list_key) if isinstance(payload, dict) else None
            if not isinstance(items, list):
                return False, f"content artifact {artifact_name!r} has no {list_key!r} list"
            observed = _hash_payload(items)
            if hashes.get(key) != observed:
                return False, (
                    f"content digest {key!r} does not match {artifact_name}; "
                    "the packet no longer reflects the persisted artifacts"
                )
    return True, None


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



_TABLE_RE = re.compile(r"<table([^>]*)>(.*?)</table>", flags=re.S | re.I)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.S | re.I)
_TH_RE = re.compile(r"<th[^>]*>(.*?)</th>", flags=re.S | re.I)
_TD_RE = re.compile(r"<td[^>]*>", flags=re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", flags=re.S | re.I)


def _plain_text(fragment: str) -> str:
    """Collapse a small HTML fragment to readable caption text."""
    text = html_unescape(_TAG_RE.sub(" ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def _caption_for_table(inner: str, index: int, prefix: str) -> tuple[str, int]:
    """Derive a caption from the table's own first-row header cells.

    A positional caption list mislabels tables as soon as a finding group is
    added or removed. Deriving the caption from the header cells keeps the
    caption aligned with the table, and the column count drives the mobile
    horizontal-scroll width.
    """
    if index == 0:
        # The cover is the first key-value table: its labels are row headers.
        return "Packet cover", 2
    first_row = _ROW_RE.search(inner)
    if first_row:
        header_cells = [_plain_text(cell) for cell in _TH_RE.findall(first_row.group(1))]
        header_cells = [cell for cell in header_cells if cell]
        if header_cells and not _TD_RE.search(first_row.group(1)):
            labels = list(dict.fromkeys(header_cells))
            return f"Table: {' · '.join(labels)}", len(header_cells)
    headings = list(_HEADING_RE.finditer(prefix))
    if headings:
        heading = _plain_text(headings[-1].group(1))
        if heading:
            return f"Table: {heading}", len(header_cells) if first_row else 2
    return f"Packet table {index + 1}", len(header_cells) if first_row else 2


def _accessible_tables(html: str) -> str:
    """Add captions, header sections, scopes, and keyboard scroll regions.

    Each table gets a caption derived from its own header row (or its nearest
    section heading as a fallback), scoped header cells, and a wrapper that can
    be scrolled with the keyboard at narrow viewports. The wrapper also keeps
    ``thead`` visible on mobile instead of stacking unlabelled cells.
    """
    counter = 0

    def replace(match):
        nonlocal counter
        attrs, inner = match.group(1), match.group(2)
        caption, columns = _caption_for_table(inner, counter, html[:match.start()])
        counter += 1
        first_row = _ROW_RE.search(inner)
        if first_row and _TH_RE.search(first_row.group(1)) and not _TD_RE.search(first_row.group(1)):
            header = re.sub(r"<th(?![^>]*\bscope=)", '<th scope="col"', first_row.group(0), flags=re.I)
            rest = inner[first_row.end():]
            inner = f"<thead>{header}</thead><tbody>{rest}</tbody>"
        else:
            inner = re.sub(r"<th(?![^>]*\bscope=)", '<th scope="row"', inner, flags=re.I)
        escaped = html_escape(caption, quote=True)
        return (
            f'<div class="table-scroll" role="group" aria-label="{escaped}" tabindex="0">'
            f'<table{attrs} data-columns="{columns}">'
            f"<caption>{escaped}</caption>{inner}</table></div>"
        )

    return _TABLE_RE.sub(replace, html)


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
    hashes.update(_content_hashes(
        discovery=discovery, review=review, reconstruction=reconstruction
    ))
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
        f"{finding_count} advisory findings and {readiness_count} "
        f"{'readiness flag' if readiness_count == 1 else 'readiness flags'} were recorded, "
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
    # The canonical JSON hash covers every packet field except the hash entries
    # themselves. It is stored inside the packet and recomputed on verification.
    packet.hashes["packet_json"] = packet_content_hash(packet.model_dump(mode="json"))
    # Render with placeholders so the complete HTML can be hashed before the
    # digest is embedded in the document (avoiding a circular hash).
    packet.hashes["packet"] = PACKET_HASH_PLACEHOLDER
    packet.hashes["packet_html"] = PACKET_HASH_PLACEHOLDER

    html = template.render(
        run_id=run_id,
        project_id=project_id,
        fixture_id=fixture_id,
        release_context=release_context,
        created_at=now,
        snapshot_hash=manifest.sha256,
        audit_head=audit_head,
        hashes=packet.hashes,
        packet_sha256=PACKET_HASH_PLACEHOLDER,
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
        scope_boundary=CLOUD_RETROFIT_BOUNDARY,
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
    html = _accessible_tables(html)
    packet_sha256 = packet_html_hash(html, PACKET_HASH_PLACEHOLDER)
    packet.hashes["packet"] = packet_sha256
    packet.hashes["packet_html"] = packet_sha256
    packet.packet_sha256 = packet_sha256
    html = html.replace(PACKET_HASH_PLACEHOLDER, packet_sha256)

    store.write_artifact(run_id, "packet.json", packet.model_dump(mode="json"))
    store.write_artifact(run_id, "packet.html", html)
    return packet
