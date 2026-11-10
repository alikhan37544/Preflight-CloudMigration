"""Full analysis pipeline with persisted artifacts and stage audit events."""

from __future__ import annotations

import hashlib
import json
import traceback
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from app.models import Manifest
from app.services.compare import CompareResult, compare_feature
from app.services.discovery import DiscoveryResult, run_discovery
from app.services.evaluate import EvaluationResult, evaluate_run
from app.services.intake import build_manifest, snapshot_hash
from app.services.packet import build_packet
from app.services.reconstruction import ReconstructionResult, reconstruct
from app.services.redaction import redact_evidence
from app.services.review import ReviewResult, run_review

GROUND_TRUTH = Path(__file__).resolve().parents[2] / "ground_truth"


class RunCancelled(Exception):
    """Raised when a run is cancelled between stages."""


@dataclass
class PipelineResult:
    run_id: str
    manifest: Manifest
    discovery: DiscoveryResult
    review: ReviewResult
    reconstruction: ReconstructionResult | None
    comparison: CompareResult | None
    evaluation: EvaluationResult | None
    fixture_id: str


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


STAGE_WEIGHTS = {
    "intake": 10, "parse": 38, "discover": 25, "review": 9,
    "reconstruct": 10, "compare": 3, "evaluate": 3, "packet": 2,
}


def execute_run(root: Path, store, run_id: str, *, project_id: str, fixture_id: str,
                tier: str = "demo", include_thesis: bool = False,
                feature_id: str = "PA-VEH-01",
                reference_path: Path | None = None,
                release_context: str = "Qusar 2026.08 (review context)",
                cancel_event=None) -> PipelineResult:
    root = Path(root)
    completed = 0
    stage = "intake"
    reference_sha = (
        hashlib.sha256(Path(reference_path).read_bytes()).hexdigest()
        if reference_path and Path(reference_path).is_file()
        else None
    )

    def mark(next_stage: str, percent: float, *, files_done: int = 0, files_total: int = 0) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RunCancelled("run cancelled by reviewer")
        store.update_status(run_id, status="running", stage=next_stage, percent=percent,
                            files_done=files_done, files_total=files_total)
        store.append_audit(run_id, action=f"stage.{next_stage}", object_type="run", object_id=run_id)

    try:
        mark("intake", 2)
        store.update_status(
            run_id, status="running", stage="intake", percent=2,
            metadata={
                "release_context": release_context,
                "reference_path": str(reference_path) if reference_path else None,
                "reference_sha256": reference_sha,
            },
        )
        manifest = build_manifest(root, snapshot_id=f"S-{run_id}", project_id=project_id)
        store.write_artifact(run_id, "manifest.json", manifest.model_dump(mode="json"))
        completed += STAGE_WEIGHTS["intake"]

        mark("parse", completed + 2, files_done=0, files_total=manifest.file_count)
        discovery = run_discovery(root, manifest)
        durable_evidence = redact_evidence(discovery.evidence)
        store.write_artifact(run_id, "features.json", {
            "schema_version": "1.0",
            "features": [f.model_dump(mode="json") for f in discovery.features],
        })
        store.write_artifact(run_id, "evidence.json", {
            "schema_version": "1.0",
            "evidence": [e.model_dump(mode="json") for e in durable_evidence],
        })
        store.write_artifact(run_id, "gaps.json", {
            "schema_version": "1.0",
            "gaps": [g.model_dump(mode="json") for g in discovery.gaps],
        })
        store.write_artifact(run_id, "spine.json", {
            "schema_version": "1.0",
            "spines": {k: v.model_dump(mode="json") for k, v in discovery.spines.items()},
        })
        completed += STAGE_WEIGHTS["parse"] + STAGE_WEIGHTS["discover"]
        mark("review", completed + 2, files_done=manifest.file_count, files_total=manifest.file_count)

        review = run_review(root, manifest, discovery, include_thesis=include_thesis)
        store.write_artifact(run_id, "findings.json", {
            "schema_version": "1.0",
            "findings": [f.model_dump(mode="json") for f in review.findings],
            "readiness": [f.model_dump(mode="json") for f in review.readiness],
        })
        durable_review_evidence = redact_evidence(review.evidence)
        store.write_artifact(run_id, "review_evidence.json", {
            "schema_version": "1.0",
            "evidence": [e.model_dump(mode="json") for e in durable_review_evidence],
        })
        completed += STAGE_WEIGHTS["review"]

        reconstruction: ReconstructionResult | None = None
        comparison: CompareResult | None = None
        evaluation: EvaluationResult | None = None
        feature = next((f for f in discovery.features if f.feature_id == feature_id), None)
        can_reconstruct = feature is not None and any(
            "PersonalVehicle" in (e.path + e.excerpt)
            for e in discovery.evidence
            if e.evidence_id in feature.evidence_ids
        )

        if can_reconstruct:
            mark("reconstruct", completed + 2)
            reconstruction = reconstruct(
                root, manifest, discovery, feature_id,
                store=store, run_id=run_id, draft_root=store.run_dir(run_id) / "draft",
            )
            # Keep inventory spines for every discovered feature; replace only the
            # reconstructed feature with its target-enriched spine.
            merged_spines = dict(discovery.spines)
            merged_spines.update(reconstruction.spines)
            store.write_artifact(run_id, "spine.json", {
                "schema_version": "1.0",
                "spines": {k: v.model_dump(mode="json") for k, v in merged_spines.items()},
            })
            completed += STAGE_WEIGHTS["reconstruct"]

            if reference_path and Path(reference_path).is_file():
                mark("compare", completed + 1)
                reference = json.loads(Path(reference_path).read_text(encoding="utf-8"))
                comparison = compare_feature(reference, reconstruction.mappings, discovery.evidence)
                store.write_artifact(run_id, "comparison.json", {
                    "schema_version": "1.0",
                    "macro_f1": comparison.macro_f1,
                    "confusion": comparison.confusion,
                    "rows": [r.model_dump(mode="json", by_alias=True) for r in comparison.rows],
                })
                completed += STAGE_WEIGHTS["compare"]

                if fixture_id in {"demo-slice-300", "acme-pc-2026.10"}:
                    mark("evaluate", completed + 2)
                    evaluation = evaluate_run(
                        fixture_id=fixture_id, manifest=manifest, discovery=discovery,
                        reconstruction=reconstruction, review=review, comparison=comparison,
                        ground_truth_dir=GROUND_TRUTH, tier=tier, fixture_root=root,
                    )
                    store.write_artifact(run_id, "metrics.json", {
                        "schema_version": "1.0",
                        "fixture_id": fixture_id,
                        "tier": tier,
                        "metrics": [m.model_dump(mode="json") for m in evaluation.metrics],
                        "supporting": [m.model_dump(mode="json") for m in evaluation.supporting],
                        "baselines": evaluation.baselines,
                        "margins": evaluation.margins,
                        "per_rule": evaluation.per_rule,
                        "m5_precision": evaluation.m5_precision,
                    })
                    completed += STAGE_WEIGHTS["evaluate"]

            mark("packet", completed + 2)
            completed += STAGE_WEIGHTS["packet"]

        after_hash = snapshot_hash(root)
        if after_hash != manifest.sha256:
            raise RuntimeError("source snapshot changed during analysis; refusing to continue")
        store.write_artifact(run_id, "immutability.json", {
            "schema_version": "1.0",
            "before": manifest.sha256,
            "after": after_hash,
            "unchanged": True,
            "checked_at": _now(),
        })
        store.append_audit(run_id, action="run.immutability.verified",
                           object_type="run", object_id=run_id,
                           before_hash=manifest.sha256, after_hash=after_hash)

        store.update_status(run_id, status="succeeded", stage="succeeded", percent=100.0,
                            files_done=manifest.file_count, files_total=manifest.file_count)
        store.append_audit(run_id, action="run.succeeded", object_type="run", object_id=run_id)

        if can_reconstruct:
            # The packet intentionally uses redacted copies: evaluation has already
            # consumed the original excerpts, and no secret leaves the run store.
            build_packet(
                store=store, run_id=run_id, project_id=project_id, fixture_id=fixture_id,
                release_context=release_context, manifest=manifest,
                discovery=replace(discovery, evidence=durable_evidence),
                review=replace(review, evidence=durable_review_evidence),
                reconstruction=reconstruction, comparison=comparison,
                evaluation=evaluation, reference_path=reference_path,
                reference_sha256=reference_sha,
            )

        return PipelineResult(
            run_id=run_id, manifest=manifest, discovery=discovery, review=review,
            reconstruction=reconstruction, comparison=comparison, evaluation=evaluation,
            fixture_id=fixture_id,
        )
    except RunCancelled:
        store.update_status(run_id, status="cancelled", stage="cancelled", percent=0.0)
        store.append_audit(run_id, action="run.cancelled", object_type="run", object_id=run_id)
        raise
    except Exception as exc:
        store.update_status(run_id, status="failed", stage="failed", percent=0.0,
                            error={"code": type(exc).__name__, "message": str(exc),
                                   "detail": traceback.format_exc(limit=3), "retryable": False})
        store.append_audit(run_id, action="run.failed", object_type="run", object_id=run_id)
        raise
