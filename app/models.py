"""Pydantic data contracts for PreFlight.

Every persisted record carries ``schema_version`` and all enums are pinned here
so the UI, services, tests, and packet renderer share one taxonomy.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

SCHEMA_VERSION = "1.0"
HEX64 = r"^[0-9a-f]{64}$"


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class ArtifactStatus(StrEnum):
    PARSED = "parsed"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    BINARY = "binary"
    CORRUPT = "corrupt"
    EXCLUDED = "excluded"


class Confidence(StrEnum):
    PARSED = "parsed"
    LINKED = "linked"
    INFERRED_REVIEW = "inferred-review"
    UNRESOLVED = "unresolved"


class Disposition(StrEnum):
    MAPPED_EXACT = "mapped_exact"
    MAPPED_TRANSFORMED = "mapped_transformed"
    INTENTIONALLY_DROPPED = "intentionally_dropped"
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED_GAP = "unresolved_gap"
    UNSUPPORTED = "unsupported"


class Provenance(StrEnum):
    GUIDEWIRE_DOC = "guidewire-doc"
    PREFLIGHT_CONVENTION = "preflight-convention"
    REVIEWER_DECISION = "reviewer-decision"


class ClaimStrength(StrEnum):
    VERIFIED_ID = "verified-id"
    VERIFIED_POLICY = "verified-policy"
    VERIFIED_DOC = "verified-doc"
    SECONDARY = "secondary"
    HEURISTIC = "heuristic"


class StandardFamily(StrEnum):
    CLOUD_STANDARD = "cloud-standard"
    GOSU_SECURE_CODING = "gosu-secure-coding"
    HARDENING_GUIDANCE = "hardening-guidance"
    INTERNAL_GUIDANCE = "internal-guidance"
    NONE = "none"


class ComparisonClass(StrEnum):
    PRESERVED = "preserved"
    CHANGED = "changed"
    MISSING = "missing"
    ADDED = "added"
    UNRESOLVED = "unresolved"


class GapKind(StrEnum):
    MISSING_SOURCE = "missing_source"
    MISSING_TARGET = "missing_target"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    UNSUPPORTED = "unsupported"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"
    INFO = "info"


class DecisionAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    EDIT = "edit"
    DEFER = "defer"


class LocatorKind(StrEnum):
    XPATH = "xpath"
    JSON_POINTER = "json_pointer"
    YAML_PATH = "yaml_path"
    LINE = "line"


class PreflightModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_assignment=True)

    schema_version: str = SCHEMA_VERSION


def _is_hex64(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


class Locator(PreflightModel):
    kind: LocatorKind
    value: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    excerpt_sha: str | None = None

    @field_validator("excerpt_sha")
    @classmethod
    def _sha(cls, value: str | None) -> str | None:
        if value is not None and not _is_hex64(value):
            raise ValueError("excerpt_sha must be a 64-character hex digest")
        return value


class Evidence(PreflightModel):
    evidence_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    locator: Locator
    excerpt: str
    excerpt_sha: str
    method: str = Field(min_length=1)
    confidence: Confidence
    redacted: bool = False

    @field_validator("excerpt_sha")
    @classmethod
    def _sha(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("excerpt_sha must be a 64-character hex digest")
        return value


def make_evidence(
    *,
    evidence_id: str,
    path: str,
    locator: Locator,
    excerpt: str,
    method: str,
    confidence: Confidence,
    redacted: bool = False,
) -> Evidence:
    """Build evidence, fingerprinting the excerpt instead of trusting callers."""
    return Evidence(
        evidence_id=evidence_id,
        path=path,
        locator=locator,
        excerpt=excerpt,
        excerpt_sha=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        method=method,
        confidence=confidence,
        redacted=redacted,
    )


class Feature(PreflightModel):
    feature_id: str = Field(min_length=1)
    capability: str | None = None
    name: str = Field(min_length=1)
    lob: str = Field(min_length=1)
    description: str
    evidence_ids: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    confidence: Confidence
    open_questions: list[str] = Field(default_factory=list)


class Mapping(PreflightModel):
    mapping_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_layer: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    target_name: str = Field(min_length=1)
    disposition: Disposition
    rule_id: str = Field(min_length=1)
    provenance: Provenance
    confidence: Confidence
    rationale: str
    source_url: str | None = None
    quote: str | None = None
    reviewer_state: Literal["pending", "accepted", "rejected", "edited", "deferred"] = "pending"

    @model_validator(mode="after")
    def _provenance_rules(self) -> "Mapping":
        if self.provenance is Provenance.GUIDEWIRE_DOC:
            if not self.source_url or not self.quote:
                raise ValueError("guidewire-doc provenance requires source_url and quote")
        if self.provenance is Provenance.PREFLIGHT_CONVENTION and not self.rationale.strip():
            raise ValueError("preflight-convention requires a rationale")
        return self


class Change(PreflightModel):
    change_id: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    diff: str
    mapping_id: str
    approval_state: Literal["pending", "accepted", "rejected", "edited"] = "pending"
    reviewer: str | None = None
    reviewed_at: str | None = None
    edited_value: str | None = None
    previous_value: str | None = None
    edit_reason: str | None = None
    edit_history: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _edit_requires_reason(self) -> "Change":
        if self.approval_state == "edited" and not (self.edit_reason and self.edit_reason.strip()):
            raise ValueError("an edited change requires edit_reason")
        return self


class Assumption(PreflightModel):
    assumption_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    impact: Literal["high", "medium", "low"]
    impact_range_days: tuple[float, float]
    impact_basis: str
    impact_confidence: Literal["high", "medium", "low"]
    impact_caveat: str
    status: Literal["open", "resolved", "rejected"] = "open"
    owner: str = "unassigned"
    question_to_ask: str
    related_mapping_id: str | None = None
    gap_id: str | None = None

    @field_validator("impact_range_days")
    @classmethod
    def _ordered(cls, value: tuple[float, float]) -> tuple[float, float]:
        low, high = value
        if low < 0 or high < low:
            raise ValueError("impact_range_days must be non-negative and ordered")
        return value


class Gap(PreflightModel):
    gap_id: str = Field(min_length=1)
    kind: GapKind
    subject: str = Field(min_length=1)
    evidence_sought: str
    impact: Literal["high", "medium", "low"]
    owner: str = "unassigned"
    status: Literal["open", "resolved", "accepted", "rejected"] = "open"
    assumption_id: str | None = None


class Finding(PreflightModel):
    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    rule_version: str = "1.0"
    title: str
    severity: Severity
    confidence: Confidence
    claim_strength: ClaimStrength
    standard_family: StandardFamily = StandardFamily.NONE
    standard_id: str | None = None
    standard_title: str | None = None
    standard_url: str | None = None
    access: Literal["public", "gated-body", "gated-app", "mixed", "none"] = "none"
    evidence_ids: list[str] = Field(min_length=1)
    message: str
    remediation: str
    decision: Literal["open", "accepted", "rejected", "deferred"] = "open"

    @model_validator(mode="after")
    def _claim_rules(self) -> "Finding":
        if self.claim_strength is ClaimStrength.VERIFIED_ID and not self.standard_id:
            raise ValueError("verified-id findings require standard_id")
        if self.claim_strength is ClaimStrength.HEURISTIC:
            if self.standard_family is not StandardFamily.NONE:
                raise ValueError("heuristic findings must use standard_family=none")
            if self.standard_id:
                raise ValueError("heuristic findings must not claim a standard_id")
        return self


class Decision(PreflightModel):
    decision_id: str = Field(min_length=1)
    object_type: str
    object_id: str
    action: DecisionAction
    actor: str
    reason: str
    before_hash: str | None = None
    after_hash: str | None = None
    created_at: str

    @field_validator("before_hash", "after_hash")
    @classmethod
    def _hash(cls, value: str | None) -> str | None:
        if value is not None and not _is_hex64(value):
            raise ValueError("decision hashes must be 64-character hex digests")
        return value


class AuditEvent(PreflightModel):
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    ts: str
    actor: str
    action: str
    object_type: str
    object_id: str
    before_hash: str | None = None
    after_hash: str | None = None
    prev_hash: str
    hash: str

    @field_validator("prev_hash")
    @classmethod
    def _prev(cls, value: str) -> str:
        if value != "GENESIS" and not _is_hex64(value):
            raise ValueError("prev_hash must be GENESIS or a 64-character hex digest")
        return value

    @field_validator("hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("hash must be a 64-character hex digest")
        return value


class ComparisonRow(PreflightModel):
    row_id: str = Field(min_length=1)
    source_ref: str
    target_ref: str | None = None
    class_: ComparisonClass = Field(alias="class")
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str
    confidence: Confidence
    target_scope_complete: bool = False

    @model_validator(mode="after")
    def _missing_scope(self) -> "ComparisonRow":
        if self.class_ is ComparisonClass.MISSING and not self.target_scope_complete:
            raise ValueError("a missing row requires a complete target scope")
        return self


class RunProgress(PreflightModel):
    stage: str
    files_done: int = Field(default=0, ge=0)
    files_total: int = Field(default=0, ge=0)
    percent: float = Field(default=0.0, ge=0.0, le=100.0)


class Run(PreflightModel):
    run_id: str
    project_id: str
    snapshot_id: str
    status: RunStatus
    stage: str
    progress: RunProgress
    release_context: str
    parser_version: str = "1.0"
    rulepack_version: str = "1.0"
    created_at: str
    finished_at: str | None = None
    error: dict[str, Any] | None = None
    synthetic: bool = True


class Snapshot(PreflightModel):
    snapshot_id: str
    project_id: str
    root: str
    sha256: str
    file_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    created_at: str
    synthetic: bool = True

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("sha256 must be a 64-character hex digest")
        return value


class Artifact(PreflightModel):
    path: str
    sha256: str
    size: int = Field(ge=0)
    kind: str
    parser: str
    status: ArtifactStatus
    warnings: list[str] = Field(default_factory=list)
    line_count: int = Field(default=0, ge=0)

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("sha256 must be a 64-character hex digest")
        return value


class Manifest(PreflightModel):
    snapshot_id: str
    project_id: str
    sha256: str
    artifacts: list[Artifact]
    file_count: int
    total_size: int
    unsupported_paths: list[str] = Field(default_factory=list)
    notice: str = "Unsupported and corrupt files are listed, not hidden."
    warnings: list[str] = Field(default_factory=list)

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("sha256 must be a 64-character hex digest")
        return value

    def artifact(self, path: str) -> Artifact:
        for item in self.artifacts:
            if item.path == path:
                return item
        raise KeyError(path)


class Metric(PreflightModel):
    metric_id: str
    label: str
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    unit: str = "ratio"
    caveat: str
    fixture_id: str
    tier: Literal["demo", "thesis"] = "demo"
    primary: bool = True
    interval_low: float | None = None
    interval_high: float | None = None

    @model_validator(mode="after")
    def _bounds(self) -> "Metric":
        if self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")
        return self

    @computed_field
    @property
    def value(self) -> float:
        return self.numerator / self.denominator


class SpineNode(PreflightModel):
    id: str
    kind: Literal["feature", "artifact", "symbol", "config", "test"]
    label: str
    artifact_path: str | None = None
    evidence_id: str | None = None
    confidence: Confidence


class SpineEdge(PreflightModel):
    id: str
    src: str
    dst: str
    kind: Literal["contains", "declares", "references", "configures", "tested_by"]
    evidence_id: str | None = None
    confidence: Confidence


class Spine(PreflightModel):
    nodes: list[SpineNode]
    edges: list[SpineEdge]
    layout: dict[str, Any] = Field(default_factory=lambda: {
        "columns": ["pcf", "entity", "typelist", "product_template", "api_draft", "tests"]
    })

    @model_validator(mode="after")
    def _edges_resolve(self) -> "Spine":
        ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.src not in ids or edge.dst not in ids:
                raise ValueError(f"spine edge {edge.id} references an unknown node")
        return self


class Rule(PreflightModel):
    rule_id: str
    version: str = "1.0"
    title: str
    severity: Severity
    claim_strength: ClaimStrength
    standard_family: StandardFamily = StandardFamily.NONE
    standard_id: str | None = None
    standard_url: str | None = None
    detection: dict[str, Any] = Field(default_factory=dict)
    allowlist: list[str] = Field(default_factory=list)
    positive_fixtures: list[str] = Field(default_factory=list)
    negative_fixtures: list[str] = Field(default_factory=list)
    remediation: str = ""


class Packet(PreflightModel):
    packet_id: str
    run_id: str
    pages: list[str]
    hashes: dict[str, str]
    audit_head: str
    disclaimer: str
    created_at: str
    counts: dict[str, int] = Field(default_factory=dict)
    audit_verified: bool = False
    audit_event_count: int = Field(default=0, ge=0)
    hash_scope: str = ""
    packet_sha256: str | None = None

    @field_validator("packet_sha256")
    @classmethod
    def _packet_sha(cls, value: str | None) -> str | None:
        if value is not None and not _is_hex64(value):
            raise ValueError("packet_sha256 must be a 64-character hex digest")
        return value


class Project(PreflightModel):
    project_id: str
    name: str
    source_release: str
    target_context: str
    created_at: str


class AssistantAnswer(PreflightModel):
    answer: str
    grounded: bool
    citations: list[str] = Field(default_factory=list)
    searched_scopes: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class CodeFinding(PreflightModel):
    """A code-level cloud blocker with line evidence.

    ``excerpt`` is redacted at capture for secret findings. ``fingerprint`` is
    stable across runs for the same rule at the same source location and is the
    value exported as a SARIF partial fingerprint.
    """

    finding_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    rule_version: str = "1.0"
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    severity: Severity
    claim_strength: ClaimStrength
    standard_family: StandardFamily = StandardFamily.NONE
    standard_id: str | None = None
    standard_title: str | None = None
    standard_url: str | None = None
    language: str = Field(min_length=1)
    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    column: int = Field(default=1, ge=1)
    excerpt: str
    excerpt_sha: str
    fingerprint: str
    message: str = Field(min_length=1)
    remediation: str = ""
    cloud_target: str = ""
    autofix: str = "none"
    confidence: Confidence = Confidence.PARSED
    redacted: bool = False

    @field_validator("excerpt_sha", "fingerprint")
    @classmethod
    def _hex64(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("must be a 64-character hex digest")
        return value

    @model_validator(mode="after")
    def _claim_rules(self) -> "CodeFinding":
        if self.claim_strength is ClaimStrength.VERIFIED_ID and not self.standard_id:
            raise ValueError("verified-id code findings require standard_id")
        if self.claim_strength is ClaimStrength.HEURISTIC and self.standard_family is not StandardFamily.NONE:
            raise ValueError("heuristic code findings must use standard_family=none")
        return self


class CodePatch(PreflightModel):
    """An Architect-generated refactor draft with a unified diff."""

    patch_id: str = Field(min_length=1)
    source_path: str | None = None
    target_path: str = Field(min_length=1)
    finding_ids: list[str] = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    strategy: str = Field(min_length=1)
    diff: str
    source_sha256: str
    target_sha256: str
    risk: Literal["high", "medium", "low"] = "medium"
    semantic_review: bool = True
    diff_redacted: bool = False
    approval: Literal["pending", "accepted", "rejected"] = "pending"

    @field_validator("source_sha256", "target_sha256")
    @classmethod
    def _hex64(cls, value: str) -> str:
        if not _is_hex64(value):
            raise ValueError("must be a 64-character hex digest")
        return value
