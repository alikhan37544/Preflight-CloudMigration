"""FastAPI product shell and JSON API for PreFlight."""

from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
import uuid
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import REPO, Settings
from app.models import (
    Assumption,
    Change,
    ComparisonRow,
    Evidence,
    Feature,
    Finding,
    Gap,
    Manifest,
    Mapping,
    Metric,
)
from app.security import SecurityMiddleware, require_csrf
from app.services.assistant import answer_question
from app.services.compare import CompareResult
from app.services.discovery import DiscoveryResult
from app.services.evaluate import EvaluationResult
from app.services.intake import UnsafeArchiveError, safe_extract_zip
from app.services.packet import DISCLAIMER, build_packet, verify_packet_artifacts
from app.services.migrator import MIGRATION_ARTIFACT, run_migration, verify_migration_log
from app.services.pipeline import RunCancelled, execute_run
from app.services.reconstruction import ReconstructionResult
from app.services.redaction import redact_excerpt
from app.services.review import ReviewResult
from app.store import RunStore, StoreError
from app.views import feature_summary, load_run_view, spine_layout

TEMPLATES = Path(__file__).resolve().parent / "templates"
STATIC = Path(__file__).resolve().parent / "static"
logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_run_id() -> str:
    return f"R-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def _json_hash(payload: Any) -> str:
    import json

    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class RunRequest(BaseModel):
    project_id: str = "demo"
    fixture_id: str = "demo-slice-300"
    force: bool = False


class DecisionRequest(BaseModel):
    object_type: str
    object_id: str
    action: str
    reason: str = Field(min_length=1)
    edited_value: str | None = None


# Artifacts load_run_view expects to parse when they are present. Missing
# optional files still default (uploaded runs may have no metrics/packet), but
# malformed JSON in any of these is corruption, not an empty run.
_CORE_ARTIFACTS = (
    "manifest.json", "features.json", "evidence.json", "review_evidence.json",
    "gaps.json", "spine.json", "findings.json", "mappings.json", "changes.json",
    "assumptions.json", "comparison.json", "metrics.json", "packet.json",
    "decisions.json", "immutability.json", "migration.json",
)
_ARTIFACT_LISTS = {
    "manifest.json": "artifacts",
    "features.json": "features",
    "evidence.json": "evidence",
    "review_evidence.json": "evidence",
    "gaps.json": "gaps",
    "findings.json": "findings",
    "mappings.json": "mappings",
    "changes.json": "changes",
    "assumptions.json": "assumptions",
    "comparison.json": "rows",
    "metrics.json": "metrics",
    "packet.json": "pages",
    "decisions.json": "decisions",
}
_ARTIFACT_DICTS = {
    "spine.json": "spines",
}
_ARTIFACT_EXTRA_LISTS = {
    "findings.json": ("readiness",),
    "metrics.json": ("supporting",),
}
# Inputs whose contents feed build_packet(). Packet outputs are checked for
# existence separately; the audit checkpoint head invalidates on decisions.
_PACKET_INPUT_ARTIFACTS = (
    "status.json", "manifest.json", "features.json", "evidence.json",
    "review_evidence.json", "gaps.json", "findings.json", "mappings.json",
    "changes.json", "assumptions.json", "comparison.json", "metrics.json",
    "decisions.json",
)

_ACTION_STATE = {
    "accept": "accepted",
    "reject": "rejected",
    "defer": "deferred",
    "edit": "edited",
}
_PENDING_STATES = {"pending", "open"}


def _read(store: RunStore, run_id: str, name: str, default: Any) -> Any:
    """Read an optional artifact; only a genuinely missing file uses ``default``."""
    try:
        return store.read_artifact(run_id, name)
    except StoreError as exc:
        if exc.code == "NOT_FOUND":
            return default
        raise


def _payload_list(store: RunStore, run_id: str, name: str, key: str,
                  default: dict[str, Any]) -> dict[str, Any]:
    payload = _read(store, run_id, name, default)
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise StoreError(
            f"artifact {name!r} is corrupt: expected a {key!r} list",
            code="CORRUPT_ARTIFACT",
        )
    return payload


def _assert_core_artifacts(store: RunStore, run_id: str) -> None:
    """Parse present core artifacts so page routes surface corruption as 500."""
    for name in _CORE_ARTIFACTS:
        if not store.exists(run_id, name):
            continue
        payload = store.read_artifact(run_id, name)
        if not isinstance(payload, dict):
            raise StoreError(
                f"artifact {name!r} is corrupt: expected a JSON object",
                code="CORRUPT_ARTIFACT",
            )
        list_key = _ARTIFACT_LISTS.get(name)
        if list_key is not None and not isinstance(payload.get(list_key), list):
            raise StoreError(
                f"artifact {name!r} is corrupt: expected a {list_key!r} list",
                code="CORRUPT_ARTIFACT",
            )
        dict_key = _ARTIFACT_DICTS.get(name)
        if dict_key is not None and not isinstance(payload.get(dict_key), dict):
            raise StoreError(
                f"artifact {name!r} is corrupt: expected a {dict_key!r} object",
                code="CORRUPT_ARTIFACT",
            )
        for extra_key in _ARTIFACT_EXTRA_LISTS.get(name, ()):
            if not isinstance(payload.get(extra_key, []), list):
                raise StoreError(
                    f"artifact {name!r} is corrupt: expected a {extra_key!r} list",
                    code="CORRUPT_ARTIFACT",
                )


def _load_view(store: RunStore, run_id: str) -> dict[str, Any]:
    _assert_core_artifacts(store, run_id)
    return load_run_view(store, run_id)


def _effective_state(object_type: str, obj: dict[str, Any],
                     previous: dict[str, Any] | None) -> str:
    """Return the reviewer-visible state, including logical defer/edit states.

    ``Change.approval_state`` has no deferred value and ``Finding.decision`` has
    no edited value, so those two logical states are reconstructed from the last
    decision for the object.
    """
    if object_type == "mapping":
        return str(obj.get("reviewer_state", "pending"))
    if object_type == "change":
        state = str(obj.get("approval_state", "pending"))
        if state == "pending" and previous and previous.get("action") == "defer":
            return "deferred"
        return state
    state = str(obj.get("decision", "open"))
    if state == "accepted" and previous and previous.get("action") == "edit":
        return "edited"
    return state


def _last_decision(decisions: list[dict[str, Any]], object_type: str,
                   object_id: str) -> dict[str, Any] | None:
    for decision in reversed(decisions):
        if (decision.get("object_type") == object_type
                and decision.get("object_id") == object_id):
            return decision
    return None


def _conflict(object_type: str, object_id: str, current: str, action: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=(
            f"{object_type} {object_id} is already {current!r}; "
            f"cannot apply {action!r} from a terminal state"
        ),
    )


class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    feature_id: str | None = None


class MigrationRequest(BaseModel):
    feature_id: str | None = None
    force: bool = False


def _fixture_path(settings: Settings, fixture_id: str) -> Path:
    if fixture_id not in settings.allowed_fixtures:
        raise HTTPException(status_code=400, detail="unknown fixture")
    path = settings.fixtures_dir / fixture_id
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="fixture not found")
    return path


def _status_or_404(store: RunStore, run_id: str) -> dict[str, Any]:
    try:
        return store.read_status(run_id)
    except StoreError as exc:
        if exc.code == "CORRUPT_ARTIFACT":
            raise
        raise HTTPException(status_code=404, detail="run not found") from exc


def _latest_run(store: RunStore, fixture_id: str | None = None) -> str | None:
    for run_id in reversed(store.list_runs()):
        try:
            status = store.read_status(run_id)
        except StoreError:
            continue
        if status.get("status") != "succeeded":
            continue
        if fixture_id and status.get("fixture_id") not in {fixture_id, None}:
            continue
        return run_id
    return None


def _assistant_context(store: RunStore, run_id: str):
    feature_payload = _payload_list(
        store, run_id, "features.json", "features", {"features": []}
    )["features"]
    evidence_payload = _payload_list(
        store, run_id, "evidence.json", "evidence", {"evidence": []}
    )["evidence"]
    gaps_payload = _payload_list(
        store, run_id, "gaps.json", "gaps", {"gaps": []}
    )["gaps"]
    review_evidence = _payload_list(
        store, run_id, "review_evidence.json", "evidence", {"evidence": []}
    )["evidence"]
    findings_payload = _payload_list(
        store, run_id, "findings.json", "findings",
        {"findings": [], "readiness": []},
    )
    mappings_payload = _payload_list(
        store, run_id, "mappings.json", "mappings", {"mappings": []}
    )["mappings"]
    changes_payload = _payload_list(
        store, run_id, "changes.json", "changes", {"changes": []}
    )["changes"]
    assumptions_payload = _payload_list(
        store, run_id, "assumptions.json", "assumptions", {"assumptions": []}
    )["assumptions"]

    features = [Feature.model_validate(item) for item in feature_payload]
    evidence = [Evidence.model_validate(item) for item in evidence_payload]
    gaps = [Gap.model_validate(item) for item in gaps_payload]
    r_evidence = [Evidence.model_validate(item) for item in review_evidence]
    findings = [Finding.model_validate(item) for item in findings_payload.get("findings", [])]
    readiness = [
        Finding.model_validate(item) for item in findings_payload.get("readiness", [])
    ]
    mappings = [Mapping.model_validate(item) for item in mappings_payload]
    changes = [Change.model_validate(item) for item in changes_payload]
    assumptions = [Assumption.model_validate(item) for item in assumptions_payload]

    discovery = DiscoveryResult(features=features, evidence=evidence, gaps=gaps)
    review = ReviewResult(findings=findings, readiness=readiness, evidence=r_evidence)
    reconstruction = ReconstructionResult(
        feature_id="PA-VEH-01", mappings=mappings, changes=changes, assumptions=assumptions,
        draft_root=Path("."), draft_files={}, patch_diff="", spines={},
    )
    return discovery, review, reconstruction


def _refresh_packet(store: RunStore, run_id: str,
                    settings: Settings) -> tuple[bool, str | None, bool]:
    """Refresh the packet when its inputs changed; otherwise reuse the artifact.

    Returns ``(True, None, rebuilt)`` on success and ``(False, reason, False)``
    when the artifact could not be refreshed. A fresh packet is identified by
    the audit checkpoint head plus artifact mtimes/sizes, so an unchanged page
    view does not rebuild a multi-megabyte document. Callers must not present a
    stale export as current.
    """
    try:
        status = store.read_status(run_id)
        if status.get("status") != "succeeded":
            return False, f"run status is {status.get('status')!r}, not 'succeeded'", False
        # Use the persisted release context/reference from the original run. Legacy
        # runs without metadata fall back to settings for compatibility.
        release_context = status.get("release_context") or settings.release_context
        if "reference_path" in status:
            reference_path = Path(status["reference_path"]) if status["reference_path"] else None
            reference_sha256 = status.get("reference_sha256")
        elif status.get("fixture_id") in {"demo-slice-300", "acme-pc-2026.10"}:
            reference_path = settings.reference_path
            reference_sha256 = None
        else:
            reference_path = None
            reference_sha256 = None
        extra_paths = (reference_path,) if reference_path else ()
        fingerprint = store.packet_input_fingerprint(
            run_id, _PACKET_INPUT_ARTIFACTS, extra_paths
        )
        outputs_exist = (
            store.exists(run_id, "packet.json") and store.exists(run_id, "packet.html")
        )
        if outputs_exist:
            # Never trust a cached packet merely because its input mtimes look
            # unchanged: verify the rendered HTML digest, the packet JSON
            # digest, the content digests, and the live audit chain before
            # reuse. The page route uses this path too, so a packet whose
            # content digests no longer match the persisted artifacts is never
            # presented as verified (and its Download action is hidden).
            self_ok, self_reason = verify_packet_artifacts(
                store, run_id, include_audit=False
            )
            if not self_ok:
                return False, f"packet integrity check failed: {self_reason}", False
            if store.packet_cache_hit(run_id, fingerprint):
                cached_ok, cached_reason = verify_packet_artifacts(
                    store, run_id, include_content=True, include_audit=True
                )
                if not cached_ok:
                    return False, f"packet integrity check failed: {cached_reason}", False
                return True, None, False
        elif store.packet_cache_hit(run_id, fingerprint):
            # A cache entry without both outputs is not a usable hit.
            store.clear_packet_cache(run_id)

        manifest_payload = _read(store, run_id, "manifest.json", None)
        if not manifest_payload:
            return False, "manifest.json is missing", False
        manifest = Manifest.model_validate(manifest_payload)
        discovery, review, reconstruction = _assistant_context(store, run_id)
        comparison_payload = _read(store, run_id, "comparison.json", {"rows": [], "macro_f1": 0.0, "confusion": {}})
        comparison = CompareResult(
            rows=[ComparisonRow.model_validate(row) for row in comparison_payload.get("rows", [])],
            macro_f1=float(comparison_payload.get("macro_f1", 0.0)),
            confusion=comparison_payload.get("confusion", {}),
        )
        evaluation_payload = _read(store, run_id, "metrics.json", None)
        evaluation = None
        if evaluation_payload:
            def strip_value(items):
                return [{k: v for k, v in item.items() if k != "value"} for item in items]

            evaluation = EvaluationResult(
                metrics=[Metric.model_validate(item) for item in strip_value(evaluation_payload.get("metrics", []))],
                supporting=[Metric.model_validate(item) for item in strip_value(evaluation_payload.get("supporting", []))],
                baselines=evaluation_payload.get("baselines", {}),
                margins=evaluation_payload.get("margins", {}),
                per_rule=evaluation_payload.get("per_rule", {}),
                m5_precision=evaluation_payload.get("m5_precision", 0.0),
            )
        build_packet(
            store=store, run_id=run_id, project_id=status.get("project_id", "demo"),
            fixture_id=status.get("fixture_id", "demo-slice-300"),
            release_context=release_context, manifest=manifest, discovery=discovery,
            review=review, reconstruction=reconstruction, comparison=comparison,
            evaluation=evaluation, reference_path=reference_path,
            reference_sha256=reference_sha256,
        )
        after = store.packet_input_fingerprint(
            run_id, _PACKET_INPUT_ARTIFACTS, extra_paths
        )
        valid, reason = verify_packet_artifacts(
            store, run_id, include_content=True, include_audit=True
        )
        if not valid:
            return False, f"packet integrity check failed after rebuild: {reason}", True
        if after == fingerprint:
            # Do not cache a packet built across a concurrent input change.
            store.store_packet_fingerprint(run_id, after)
        return True, None, True
    except Exception as exc:
        logger.warning("packet refresh failed for %s: %s", run_id, exc)
        return False, f"{type(exc).__name__}: {exc}", False


def _reconcile_interrupted_runs(store: RunStore) -> None:
    """Cancel runs left queued/running by a previous process.

    The worker that owned these runs no longer exists after a restart, so
    leaving them ``running`` forever would also block every decision (which
    requires ``succeeded``).  Mark them cancelled with an explicit audit reason.
    """
    for run_id in store.list_runs():
        try:
            status = store.read_status(run_id)
            if status.get("status") not in {"queued", "running"}:
                continue
            with store.locked(run_id):
                status = store.read_status(run_id)
                if status.get("status") not in {"queued", "running"}:
                    continue
                reason = (
                    "marked cancelled at startup: no worker survived the restart "
                    f"(previous status {status.get('status')!r}, stage {status.get('stage')!r})"
                )
                store.update_status(
                    run_id, status="cancelled", stage="cancelled", percent=0.0,
                    error={
                        "code": "RunInterrupted",
                        "message": "Server restarted before this run finished; marked cancelled at startup.",
                        "retryable": True,
                    },
                )
                store.append_audit(
                    run_id, action="run.cancelled", object_type="run",
                    object_id=run_id, actor="system", reason=reason,
                )
        except StoreError as exc:
            logger.warning("startup reconciliation failed for %s: %s", run_id, exc)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="PreFlight", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = RunStore(settings.data_dir)
    app.state.cancel_events = {}
    app.state.run_workers = {}
    app.state.migration_workers = {}
    app.state.migration_lock = threading.Lock()
    _reconcile_interrupted_runs(app.state.store)

    app.add_middleware(
        SecurityMiddleware,
        secret_key=settings.secret_key,
        allowed_hosts=settings.allowed_hosts,
    )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {"code": f"HTTP_{exc.status_code}", "message": message,
                          "detail": exc.detail, "retryable": False},
                "detail": message,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "VALIDATION_ERROR", "message": "Request validation failed",
                          "detail": exc.errors(), "retryable": False},
                "detail": "Request validation failed",
            },
        )

    @app.exception_handler(StoreError)
    async def store_error(request: Request, exc: StoreError):
        code = getattr(exc, "code", "STORE_ERROR")
        if code == "NOT_FOUND":
            status_code = 404
        elif code in {"INVALID_RUN_ID", "INVALID_ARTIFACT"}:
            status_code = 400
        else:
            status_code = 500
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {"code": code, "message": str(exc),
                          "detail": str(exc), "retryable": False},
                "detail": str(exc),
            },
        )

    templates = Jinja2Templates(directory=str(TEMPLATES))
    templates.env.globals["disclaimer"] = DISCLAIMER
    templates.env.globals["release_context"] = settings.release_context
    templates.env.filters["percent"] = lambda value: f"{float(value) * 100:.0f}%"
    templates.env.filters["num"] = lambda value: f"{float(value):.2f}"
    templates.env.filters["short"] = lambda value, n=12: str(value)[:n]

    if STATIC.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    def context(request: Request, run_id: str | None, view: dict[str, Any] | None,
                title: str, **extra: Any) -> dict[str, Any]:
        payload = {
            "request": request,
            "run_id": run_id,
            "view": view,
            "title": title,
            "csrf_token": getattr(request.state, "csrf_token", ""),
            "settings": settings,
            "product_version": "0.1.0",
            "now": _now(),
        }
        payload.update(extra)
        return payload

    def guard(request: Request, run_id: str, title: str):
        try:
            view = _load_view(app.state.store, run_id)
        except StoreError as exc:
            if exc.code == "CORRUPT_ARTIFACT":
                raise
            return None, templates.TemplateResponse(
                request=request, name="error.html",
                context=context(request, run_id, None, title, error="This run no longer exists."),
                status_code=404,
            )
        if view["status"]["status"] in {"queued", "running"}:
            return view, templates.TemplateResponse(
                request=request, name="loading.html",
                context=context(request, run_id, view, title),
            )
        if view["status"]["status"] in {"failed", "cancelled"}:
            error = (view["status"].get("error") or {}).get("message") or "The run stopped before producing artifacts."
            return view, templates.TemplateResponse(
                request=request, name="error.html",
                context=context(request, run_id, view, title, error=error),
                status_code=200,
            )
        return view, None

    # -- pages ---------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def workbench(request: Request, run: str | None = Query(default=None),
                  feature: str | None = Query(default=None),
                  evidence: str | None = Query(default=None)):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Workbench"),
            )
        try:
            view = _load_view(app.state.store, run_id)
        except StoreError as exc:
            if exc.code == "CORRUPT_ARTIFACT":
                raise
            return templates.TemplateResponse(
                request=request, name="error.html",
                context=context(request, run_id, None, "Run not found", error="This run no longer exists."),
                status_code=404,
            )
        if feature:
            selected = next((f for f in view["features"] if f["feature_id"] == feature), None)
            if selected:
                view["selected_feature"] = selected
                view["selected_spine"] = view["spines"].get(feature)
                view["spine_layout"] = spine_layout(view["selected_spine"])
                view["feature_summary"] = feature_summary(view)
        selected_evidence = view["evidence_by_id"].get(evidence) if evidence else None
        if selected_evidence is None and view.get("selected_feature"):
            for candidate in view["selected_feature"].get("evidence_ids", []):
                if candidate in view["evidence_by_id"]:
                    selected_evidence = view["evidence_by_id"][candidate]
                    break
        # The workbench only lets the user inspect evidence attached to the
        # selected feature's spine. Scope the JSON island to that working set
        # instead of inlining the whole estate on every view. The unscoped
        # records remain available from /api/runs/<id>/evidence/<evidence_id>.
        scoped_ids: set[str] = set()
        if view.get("selected_feature"):
            scoped_ids.update(view["selected_feature"].get("evidence_ids", []))
        selected_spine = view.get("selected_spine")
        if selected_spine:
            spine_payload = (
                selected_spine.model_dump(mode="json")
                if hasattr(selected_spine, "model_dump") else selected_spine
            )
            scoped_ids.update(
                node["evidence_id"] for node in spine_payload.get("nodes", [])
                if node.get("evidence_id")
            )
        if evidence:
            scoped_ids.add(evidence)
        view["evidence_by_id"] = {
            evidence_id: view["evidence_by_id"][evidence_id]
            for evidence_id in scoped_ids
            if evidence_id in view["evidence_by_id"]
        }
        return templates.TemplateResponse(
            request=request, name="workbench.html",
            context=context(request, run_id, view, "Workbench",
                            selected_evidence=selected_evidence),
        )

    @app.get("/manifest", response_class=HTMLResponse)
    def manifest_page(request: Request, run: str | None = Query(default=None),
                      page: int = Query(default=1, ge=1), q: str = Query(default=""),
                      status_filter: str = Query(default="", alias="status"),
                      excluded: int = Query(default=0)):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Manifest"),
            )
        view, response = guard(request, run_id, "Manifest")
        if response:
            return response
        artifacts = view["manifest"].get("artifacts", [])
        unsupported = set(view["manifest"].get("unsupported_paths", []))
        excluded_artifacts = [a for a in artifacts if a["path"] in unsupported]
        excluded_counts = {
            status: len([a for a in excluded_artifacts if a["status"] == status])
            for status in ("binary", "corrupt", "unsupported")
        }
        if excluded:
            artifacts = excluded_artifacts
        if q:
            artifacts = [a for a in artifacts if q.lower() in a["path"].lower()]
        if status_filter:
            artifacts = [a for a in artifacts if a["status"] == status_filter]
        total = len(artifacts)
        size = 100
        start = (page - 1) * size
        return templates.TemplateResponse(
            request=request, name="manifest.html",
            context=context(request, run_id, view, "Manifest",
                            artifacts=artifacts[start:start + size], total=total,
                            page=page, size=size, q=q, status_filter=status_filter,
                            excluded=excluded, excluded_artifacts=excluded_artifacts,
                            excluded_counts=excluded_counts,
                            pages=max(1, (total + size - 1) // size)),
        )

    @app.get("/reconstruction", response_class=HTMLResponse)
    def reconstruction_page(request: Request, run: str | None = Query(default=None),
                            tab: str = Query(default="mappings")):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Reconstruction"),
            )
        view, response = guard(request, run_id, "Reconstruction")
        if response:
            return response
        if tab not in {"mappings", "draft", "assumptions", "comparison"}:
            tab = "mappings"
        return templates.TemplateResponse(
            request=request, name="reconstruction.html",
            context=context(request, run_id, view, "Reconstruction", tab=tab),
        )

    @app.get("/migrator", response_class=HTMLResponse)
    def migrator_page(request: Request, run: str | None = Query(default=None)):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Migrator"),
            )
        view, response = guard(request, run_id, "Migrator")
        if response:
            return response
        return templates.TemplateResponse(
            request=request, name="migrator.html",
            context=context(request, run_id, view, "Migrator"),
        )

    @app.get("/findings", response_class=HTMLResponse)
    def findings_page(request: Request, run: str | None = Query(default=None),
                      selected: str | None = Query(default=None)):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Findings"),
            )
        view, response = guard(request, run_id, "Findings")
        if response:
            return response
        finding = next((f for f in view["findings"] if f["finding_id"] == selected), None)
        if finding is None and view["findings"]:
            finding = view["findings"][0]
        return templates.TemplateResponse(
            request=request, name="findings.html",
            context=context(request, run_id, view, "Findings", selected_finding=finding),
        )

    @app.get("/evaluation", response_class=HTMLResponse)
    def evaluation_page(request: Request, run: str | None = Query(default=None)):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Evaluation"),
            )
        view, response = guard(request, run_id, "Evaluation")
        if response:
            return response
        return templates.TemplateResponse(
            request=request, name="evaluation.html",
            context=context(request, run_id, view, "Evaluation"),
        )

    @app.get("/packet", response_class=HTMLResponse)
    def packet_page(request: Request, run: str | None = Query(default=None)):
        run_id = run or _latest_run(app.state.store)
        if not run_id:
            return templates.TemplateResponse(
                request=request, name="empty.html",
                context=context(request, None, None, "Packet"),
            )
        view, response = guard(request, run_id, "Packet")
        if response:
            return response
        refreshed, refresh_error, rebuilt = _refresh_packet(
            app.state.store, run_id, settings
        )
        if rebuilt or not refreshed:
            view = _load_view(app.state.store, run_id)
        if not refreshed:
            # A stale or tampered packet must not be presented as verified even
            # when the audit log itself happens to be intact.
            view["audit_verified"] = False
            if isinstance(view.get("packet"), dict):
                view["packet"]["audit_verified"] = False
        return templates.TemplateResponse(
            request=request, name="packet.html",
            context=context(request, run_id, view, "Packet",
                            packet_refresh_error=None if refreshed else refresh_error),
        )

    @app.get("/packet/export")
    def packet_export(run: str = Query(...)):
        store: RunStore = app.state.store
        status = _status_or_404(store, run)
        if status.get("status") != "succeeded":
            raise HTTPException(
                status_code=409,
                detail=f"packet refresh requires a succeeded run; status is {status.get('status')!r}",
            )
        refreshed, refresh_error, _rebuilt = _refresh_packet(store, run, settings)
        if not refreshed:
            integrity = "integrity" in str(refresh_error).lower()
            raise HTTPException(
                status_code=409 if integrity else 503,
                detail=(
                    "review packet integrity check failed; refusing to export "
                    f"tampered or unverifiable HTML: {refresh_error}"
                    if integrity else
                    "review packet refresh failed; refusing to export a stale artifact: "
                    f"{refresh_error}"
                ),
            )
        valid, reason = verify_packet_artifacts(
            store, run, include_content=True, include_audit=True
        )
        if not valid:
            raise HTTPException(
                status_code=409,
                detail=(
                    "review packet integrity check failed; refusing to export "
                    f"tampered or unverifiable HTML: {reason}"
                ),
            )
        try:
            html = store.read_artifact(run, "packet.html")
        except StoreError:
            raise HTTPException(status_code=404, detail="packet not generated")
        return PlainTextResponse(
            html, media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="{run}-review-packet.html"'},
        )

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request):
        store: RunStore = app.state.store
        runs = []
        for run_id in reversed(store.list_runs()):
            try:
                runs.append(store.read_status(run_id))
            except StoreError:
                continue
        return templates.TemplateResponse(
            request=request, name="runs.html",
            context=context(request, None, None, "Runs", runs=runs),
        )

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request):
        return templates.TemplateResponse(
            request=request, name="empty.html",
            context=context(request, None, None, "Import snapshot"),
        )

    @app.get("/about", response_class=HTMLResponse)
    def about_page(request: Request):
        return templates.TemplateResponse(
            request=request, name="about.html",
            context=context(request, None, None, "About and boundaries"),
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return templates.TemplateResponse(
            request=request, name="settings.html",
            context=context(request, None, None, "Settings"),
        )

    # -- JSON API ------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/health")
    def health_alias():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/v1/models")
    def openai_models_compat():
        # PreFlight is not an LLM server. Some local AI/IDE extensions probe this
        # OpenAI-compatible path; return a truthful empty model list instead of 404.
        return {"object": "list", "data": [], "preflight": "not an LLM; no models"}

    @app.get("/api/runs")
    def list_runs():
        store: RunStore = app.state.store
        runs = []
        for run_id in store.list_runs():
            try:
                runs.append(store.read_status(run_id))
            except StoreError:
                continue
        return {"runs": runs}

    @app.post("/api/runs", dependencies=[Depends(require_csrf)])
    def create_run(body: RunRequest, request: Request):
        store: RunStore = app.state.store
        fixture = _fixture_path(settings, body.fixture_id)
        if not body.force:
            existing = _latest_run(store, body.fixture_id)
            if existing:
                return {"run_id": existing, "status": store.read_status(existing)["status"], "reused": True}

        run_id = _new_run_id()
        store.create_run(run_id, project_id=body.project_id, snapshot_id=f"S-{run_id}",
                         fixture_id=body.fixture_id)
        cancel_event = threading.Event()
        app.state.cancel_events[run_id] = cancel_event
        reference = settings.reference_path if body.fixture_id in {"demo-slice-300", "acme-pc-2026.10"} else None

        def target() -> None:
            try:
                execute_run(
                    fixture, store, run_id, project_id=body.project_id,
                    fixture_id=body.fixture_id, tier=settings.tier,
                    reference_path=reference, release_context=settings.release_context,
                    cancel_event=cancel_event,
                )
            except RunCancelled:
                return
            except Exception:
                return
            finally:
                app.state.cancel_events.pop(run_id, None)
                app.state.run_workers.pop(run_id, None)

        if settings.sync_runs:
            target()
        else:
            worker = threading.Thread(target=target, daemon=True, name=f"preflight-{run_id}")
            app.state.run_workers[run_id] = worker
            worker.start()
        status = store.read_status(run_id)
        return {"run_id": run_id, "status": status["status"],
                "progress": status.get("progress", {})}

    @app.post("/api/imports", dependencies=[Depends(require_csrf)])
    async def import_snapshot(file: UploadFile = File(...)):
        store: RunStore = app.state.store
        run_id = _new_run_id()
        run_dir = store.create_run(run_id, project_id="uploaded", snapshot_id=f"S-{run_id}",
                                   fixture_id="uploaded")
        source = run_dir / "source"
        source.mkdir(parents=True, exist_ok=True)
        archive = run_dir / "upload.zip"
        data = await file.read()
        if len(data) > settings.max_upload_bytes:
            store.delete_run(run_id)
            raise HTTPException(status_code=413, detail="archive exceeds the size limit")
        archive.write_bytes(data)
        try:
            safe_extract_zip(archive, source)
        except UnsafeArchiveError as exc:
            store.delete_run(run_id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
            store.delete_run(run_id)
            raise HTTPException(
                status_code=400,
                detail=f"archive is corrupt or truncated: {type(exc).__name__}: {exc}",
            ) from exc
        except Exception as exc:
            # Extraction can fail on filesystem or decoder errors that are not
            # UnsafeArchiveError; never leave a half-created run behind.
            store.delete_run(run_id)
            raise HTTPException(
                status_code=400,
                detail=f"archive could not be extracted: {type(exc).__name__}: {exc}",
            ) from exc
        finally:
            if archive.exists():
                archive.unlink()
        if not any(p.is_file() for p in source.rglob("*")):
            store.delete_run(run_id)
            raise HTTPException(status_code=400, detail="archive contains no files")

        reference = settings.reference_path if (source / "config/metadata/entity/PersonalVehicle.eti").is_file() else None
        cancel_event = threading.Event()
        app.state.cancel_events[run_id] = cancel_event

        def target_upload() -> None:
            try:
                execute_run(
                    source, store, run_id, project_id="uploaded", fixture_id="uploaded",
                    tier=settings.tier, reference_path=reference,
                    release_context=settings.release_context, cancel_event=cancel_event,
                )
            except RunCancelled:
                return
            except Exception:
                return
            finally:
                app.state.cancel_events.pop(run_id, None)
                app.state.run_workers.pop(run_id, None)

        if settings.sync_runs:
            target_upload()
        else:
            worker = threading.Thread(
                target=target_upload, daemon=True, name=f"preflight-{run_id}"
            )
            app.state.run_workers[run_id] = worker
            worker.start()
        status = store.read_status(run_id)
        return {"run_id": run_id, "status": status["status"]}

    @app.get("/api/runs/{run_id}/status")
    def run_status(run_id: str):
        return _status_or_404(app.state.store, run_id)

    @app.post("/api/runs/{run_id}/cancel", dependencies=[Depends(require_csrf)])
    def cancel_run(run_id: str):
        store: RunStore = app.state.store
        status = _status_or_404(store, run_id)
        event = app.state.cancel_events.get(run_id)
        if event:
            event.set()
        active = status.get("status") in {"queued", "running"}
        if active:
            with store.locked(run_id):
                current = _status_or_404(store, run_id)
                if current.get("status") in {"queued", "running"}:
                    store.update_status(
                        run_id, status="cancelled", stage="cancelled", percent=0.0,
                        error={
                            "code": "RunCancelled",
                            "message": "Run cancelled by reviewer.",
                            "retryable": True,
                        },
                    )
                    store.append_audit(
                        run_id, action="run.cancelled", object_type="run",
                        object_id=run_id, actor="reviewer",
                        reason="cancelled by reviewer via API",
                    )
        return {"run_id": run_id, "cancelling": active}

    @app.get("/api/runs/{run_id}/manifest")
    def manifest_api(run_id: str, page: int = Query(default=1, ge=1),
                     size: int = Query(default=100, ge=1, le=500)):
        _status_or_404(app.state.store, run_id)
        view = _load_view(app.state.store, run_id)
        artifacts = view["manifest"].get("artifacts", [])
        start = (page - 1) * size
        return {
            "run_id": run_id,
            "total": len(artifacts),
            "snapshot_hash": view["manifest"].get("sha256", ""),
            "unsupported_paths": view["manifest"].get("unsupported_paths", []),
            "artifacts": artifacts[start:start + size],
        }

    @app.get("/api/runs/{run_id}/features")
    def features_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        return _payload_list(store, run_id, "features.json", "features",
                             {"features": []})

    @app.get("/api/runs/{run_id}/features/{feature_id}")
    def feature_api(run_id: str, feature_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        features = _payload_list(store, run_id, "features.json", "features",
                                 {"features": []})["features"]
        feature = next((f for f in features if f["feature_id"] == feature_id), None)
        if not feature:
            raise HTTPException(status_code=404, detail="feature not found")
        evidence = _payload_list(store, run_id, "evidence.json", "evidence",
                                 {"evidence": []})["evidence"]
        by_id = {e["evidence_id"]: e for e in evidence}
        return {"feature": feature, "evidence": [by_id[e] for e in feature["evidence_ids"] if e in by_id]}

    @app.get("/api/runs/{run_id}/evidence/{evidence_id}")
    def evidence_api(run_id: str, evidence_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        evidence = _payload_list(
            store, run_id, "evidence.json", "evidence", {"evidence": []}
        )["evidence"]
        review_evidence = _payload_list(
            store, run_id, "review_evidence.json", "evidence", {"evidence": []}
        )["evidence"]
        for item in evidence + review_evidence:
            if item.get("evidence_id") == evidence_id:
                return item
        raise HTTPException(status_code=404, detail="evidence not found")

    @app.get("/api/runs/{run_id}/spine")
    def spine_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        view = _load_view(app.state.store, run_id)
        return {"schema_version": "1.0", "spines": view["spines"]}

    @app.get("/api/runs/{run_id}/migration")
    def migration_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        try:
            state = store.read_artifact(run_id, MIGRATION_ARTIFACT)
        except StoreError as exc:
            if exc.code == "NOT_FOUND":
                return {"run_id": run_id, "status": "not_started", "progress": 0, "agents": []}
            raise
        state["audit"]["verified"], state["audit"]["detail"] = verify_migration_log(store, run_id)
        return state

    @app.post("/api/runs/{run_id}/migration", dependencies=[Depends(require_csrf)])
    def start_migration(run_id: str, body: MigrationRequest):
        store: RunStore = app.state.store
        status = _status_or_404(store, run_id)
        if status.get("status") != "succeeded":
            raise HTTPException(status_code=409, detail="migration requires a succeeded analysis run")
        existing = None
        try:
            existing = store.read_artifact(run_id, MIGRATION_ARTIFACT)
        except StoreError as exc:
            if exc.code != "NOT_FOUND":
                raise
        with app.state.migration_lock:
            worker = app.state.migration_workers.get(run_id)
            if worker is not None and worker.is_alive():
                return {"run_id": run_id, "status": "running", "agents": existing.get("agents", []) if existing else []}
            if existing and existing.get("status") in {"completed", "completed_with_gates"} and not body.force:
                return existing

            def target() -> None:
                try:
                    run_migration(store, run_id, feature_id=body.feature_id, pace=0.35)
                except Exception:
                    logger.exception("migration failed for %s", run_id)
                finally:
                    app.state.migration_workers.pop(run_id, None)

            thread = threading.Thread(target=target, daemon=True, name=f"preflight-migrator-{run_id}")
            app.state.migration_workers[run_id] = thread
            thread.start()
        return {"run_id": run_id, "status": "starting", "feature_id": body.feature_id}

    @app.get("/api/runs/{run_id}/migration/file")
    def migration_file(run_id: str, path: str = Query(min_length=1)):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        if not path.startswith("migration/") or ".." in Path(path).parts:
            raise HTTPException(status_code=400, detail="invalid migration path")
        target = (store.run_dir(run_id) / path).resolve()
        root = (store.run_dir(run_id) / "migration").resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="migration file not found")
        media = "text/markdown" if target.suffix == ".md" else "application/json"
        return FileResponse(target, media_type=media, filename=target.name)

    @app.get("/api/runs/{run_id}/findings")
    def findings_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        return _payload_list(store, run_id, "findings.json", "findings",
                             {"findings": [], "readiness": []})

    @app.get("/api/runs/{run_id}/mappings")
    def mappings_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        return _payload_list(store, run_id, "mappings.json", "mappings",
                             {"mappings": []})

    @app.get("/api/runs/{run_id}/assumptions")
    def assumptions_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        return _payload_list(store, run_id, "assumptions.json", "assumptions",
                             {"assumptions": []})

    @app.get("/api/runs/{run_id}/gaps")
    def gaps_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        return _payload_list(store, run_id, "gaps.json", "gaps", {"gaps": []})

    @app.get("/api/runs/{run_id}/comparison")
    def comparison_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        payload = _read(store, run_id, "comparison.json",
                        {"rows": [], "macro_f1": 0.0})
        if not isinstance(payload, dict) or not isinstance(payload.get("rows", []), list):
            raise StoreError(
                "artifact 'comparison.json' is corrupt: expected a 'rows' list",
                code="CORRUPT_ARTIFACT",
            )
        return payload

    @app.get("/api/runs/{run_id}/metrics")
    def metrics_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        payload = _read(store, run_id, "metrics.json",
                        {"metrics": [], "supporting": []})
        if (not isinstance(payload, dict)
                or not isinstance(payload.get("metrics", []), list)
                or not isinstance(payload.get("supporting", []), list)):
            raise StoreError(
                "artifact 'metrics.json' is corrupt: expected metric lists",
                code="CORRUPT_ARTIFACT",
            )
        return payload

    @app.get("/api/runs/{run_id}/packet")
    def packet_api(run_id: str):
        store: RunStore = app.state.store
        status = _status_or_404(store, run_id)
        if status.get("status") != "succeeded":
            raise HTTPException(
                status_code=409,
                detail=f"packet refresh requires a succeeded run; status is {status.get('status')!r}",
            )
        refreshed, refresh_error, _rebuilt = _refresh_packet(store, run_id, settings)
        if not refreshed:
            integrity = "integrity" in str(refresh_error).lower()
            raise HTTPException(
                status_code=409 if integrity else 503,
                detail=(
                    "review packet integrity check failed: "
                    f"{refresh_error}"
                    if integrity else
                    f"review packet refresh failed: {refresh_error}"
                ),
            )
        valid, reason = verify_packet_artifacts(
            store, run_id, include_content=True, include_audit=True
        )
        if not valid:
            raise HTTPException(
                status_code=409,
                detail=f"review packet integrity check failed: {reason}",
            )
        packet = _read(app.state.store, run_id, "packet.json", None)
        if packet is None:
            raise HTTPException(status_code=404, detail="packet not generated")
        return packet

    @app.get("/api/runs/{run_id}/draft")
    def draft_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        draft = store.run_dir(run_id) / "draft"
        files = sorted(p.relative_to(draft).as_posix() for p in draft.rglob("*") if p.is_file()) if draft.exists() else []
        return {"files": files}

    @app.get("/api/runs/{run_id}/diff")
    def diff_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        try:
            return {"diff": store.read_artifact(run_id, "patch.diff")}
        except StoreError:
            return {"diff": ""}

    @app.get("/api/runs/{run_id}/audit")
    def audit_api(run_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        return {"events": store.read_audit(run_id), "verified": store.verify_audit(run_id)}

    @app.post("/api/runs/{run_id}/decisions", dependencies=[Depends(require_csrf)])
    def decision_api(run_id: str, body: DecisionRequest):
        store: RunStore = app.state.store
        if body.action not in _ACTION_STATE:
            raise HTTPException(status_code=400, detail="unknown action")
        if body.object_type not in {"mapping", "change", "finding"}:
            raise HTTPException(status_code=400, detail="unsupported object_type")
        if body.action == "edit" and not body.edited_value:
            raise HTTPException(status_code=400, detail="edit requires edited_value")
        # Reviewer free text is persisted into assumptions, decisions, audit and
        # the packet. Redact it at the API boundary before any of that happens.
        body.reason = redact_excerpt(body.reason)[0]
        if body.edited_value is not None:
            body.edited_value = redact_excerpt(body.edited_value)[0]
        _status_or_404(store, run_id)

        response: dict[str, Any] | None = None
        with store.locked(run_id):
            # Re-read status under the transaction lock: a run may have been
            # cancelled or deleted after the cheap 404 check above.
            status = _status_or_404(store, run_id)
            if status.get("status") != "succeeded":
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"run {run_id} is {status.get('status')!r}; "
                        "review decisions require a succeeded run"
                    ),
                )
            # Refuse to mutate a run whose core evidence is unreadable; a
            # decision must never be based on silently substituted empties.
            _assert_core_artifacts(store, run_id)

            decisions_payload = _payload_list(
                store, run_id, "decisions.json", "decisions", {"decisions": []}
            )
            previous = _last_decision(
                decisions_payload["decisions"], body.object_type, body.object_id
            )
            target_state = _ACTION_STATE[body.action]
            created_assumption: dict[str, Any] | None = None
            rollback: dict[str, Any] = {}
            writes: list[tuple[str, Any]] = []
            decision_reason = body.reason
            before = after = None

            if body.object_type == "mapping":
                payload = _payload_list(
                    store, run_id, "mappings.json", "mappings", {"mappings": []}
                )
                obj = next((m for m in payload["mappings"]
                            if m.get("mapping_id") == body.object_id), None)
                if not obj:
                    raise HTTPException(status_code=404, detail="mapping not found")
                current = _effective_state("mapping", obj, previous)
                if current == target_state:
                    assumptions = _payload_list(
                        store, run_id, "assumptions.json", "assumptions",
                        {"assumptions": []},
                    )
                    existing = next(
                        (a for a in assumptions["assumptions"]
                         if a.get("related_mapping_id") == body.object_id),
                        None,
                    )
                    response = {"decision": previous, "object": obj,
                                "assumption": existing, "idempotent": True}
                else:
                    if current not in _PENDING_STATES:
                        raise _conflict(body.object_type, body.object_id, current, body.action)
                    rollback["mappings.json"] = copy.deepcopy(payload)
                    before = _json_hash(obj)
                    obj["reviewer_state"] = target_state
                    if body.action == "edit":
                        obj["target_name"] = body.edited_value
                    new_assumption = False
                    if body.action == "reject":
                        assumptions = _payload_list(
                            store, run_id, "assumptions.json", "assumptions",
                            {"assumptions": []},
                        )
                        existing = next(
                            (a for a in assumptions["assumptions"]
                             if a.get("related_mapping_id") == body.object_id),
                            None,
                        )
                        if existing is not None:
                            created_assumption = existing
                        else:
                            rollback["assumptions.json"] = copy.deepcopy(assumptions)
                            used = {a.get("assumption_id") for a in assumptions["assumptions"]}
                            number = len(assumptions["assumptions"]) + 1
                            while f"A-DEC-{number:02d}" in used:
                                number += 1
                            created_assumption = {
                                "schema_version": "1.0",
                                "assumption_id": f"A-DEC-{number:02d}",
                                "statement": (
                                    f"Mapping {body.object_id} was rejected by a reviewer: "
                                    f"{body.reason}"
                                ),
                                "impact": "medium", "impact_range_days": [1.0, 2.0],
                                "impact_basis": "Reviewer rejection of one mapping; rework and re-review.",
                                "impact_confidence": "low",
                                "impact_caveat": "Heuristic planning range; not a quote.",
                                "status": "open", "owner": "unassigned",
                                "question_to_ask": "What target should replace the rejected mapping?",
                                "related_mapping_id": body.object_id, "gap_id": None,
                            }
                            assumptions["assumptions"].append(created_assumption)
                            new_assumption = True
                    writes.append(("mappings.json", payload))
                    if new_assumption:
                        writes.append(("assumptions.json", assumptions))
                    after = _json_hash(obj)
            elif body.object_type == "change":
                payload = _payload_list(
                    store, run_id, "changes.json", "changes", {"changes": []}
                )
                obj = next((c for c in payload["changes"]
                            if c.get("change_id") == body.object_id), None)
                if not obj:
                    raise HTTPException(status_code=404, detail="change not found")
                current = _effective_state("change", obj, previous)
                if current == target_state:
                    response = {"decision": previous, "object": obj,
                                "assumption": None, "idempotent": True}
                else:
                    if current not in _PENDING_STATES:
                        raise _conflict(body.object_type, body.object_id, current, body.action)
                    rollback["changes.json"] = copy.deepcopy(payload)
                    before = _json_hash(obj)
                    # Change has no persisted deferred state; the decision log
                    # carries the logical defer while approval_state stays pending.
                    obj["approval_state"] = "pending" if body.action == "defer" else target_state
                    obj["reviewer"] = "reviewer"
                    obj["reviewed_at"] = _now()
                    if body.action == "edit":
                        obj["edited_value"] = body.edited_value
                        obj["edit_reason"] = body.reason
                    writes.append(("changes.json", payload))
                    after = _json_hash(obj)
            else:  # finding
                payload = _payload_list(
                    store, run_id, "findings.json", "findings",
                    {"findings": [], "readiness": []},
                )
                obj = next((f for f in payload["findings"]
                            if f.get("finding_id") == body.object_id), None)
                if not obj:
                    raise HTTPException(status_code=404, detail="finding not found")
                current = _effective_state("finding", obj, previous)
                if current == target_state:
                    response = {"decision": previous, "object": obj,
                                "assumption": None, "idempotent": True}
                else:
                    if current not in _PENDING_STATES:
                        raise _conflict(body.object_type, body.object_id, current, body.action)
                    rollback["findings.json"] = copy.deepcopy(payload)
                    before = _json_hash(obj)
                    # Finding.decision has no edited value; editing retains the
                    # accepted disposition and records the value in the decision.
                    obj["decision"] = "accepted" if body.action == "edit" else target_state
                    if body.action == "edit":
                        decision_reason = (
                            f"{body.reason} (edited value: {body.edited_value})"
                        )
                    writes.append(("findings.json", payload))
                    after = _json_hash(obj)

            if response is None:
                applied: list[str] = []
                try:
                    # Artifact writes and the audit/decision commit are one
                    # transaction. Mapping rejection writes the mapping before
                    # the assumption; a failure rolls both artifacts back.
                    for artifact_name, artifact_payload in writes:
                        store.write_artifact(run_id, artifact_name, artifact_payload)
                        applied.append(artifact_name)
                    decision = store.record_decision(
                        run_id, object_type=body.object_type,
                        object_id=body.object_id, action=body.action,
                        actor="reviewer", reason=decision_reason,
                        before_hash=before, after_hash=after,
                    )
                except BaseException:
                    # Restore only artifacts that were actually written. A
                    # failed first write must not create an empty companion
                    # artifact during rollback.
                    for name in reversed(applied):
                        data = rollback.get(name)
                        if data is None:
                            continue
                        try:
                            store.write_artifact(run_id, name, data)
                        except Exception:
                            pass
                    raise
                response = {"decision": decision, "object": obj,
                            "assumption": created_assumption}

        if not response.get("idempotent"):
            # Packet rendering is slow and must not hold the transaction lock.
            _refresh_packet(store, run_id, settings)
        return response

    @app.post("/api/runs/{run_id}/assistant", dependencies=[Depends(require_csrf)])
    def assistant_api(run_id: str, body: AssistantRequest):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        discovery, review, reconstruction = _assistant_context(store, run_id)
        answer = answer_question(
            body.question, discovery, review, reconstruction, feature_id=body.feature_id
        )
        return answer.model_dump(mode="json")

    @app.post("/api/runs/{run_id}/delete", dependencies=[Depends(require_csrf)])
    def delete_run(run_id: str):
        store: RunStore = app.state.store
        status = _status_or_404(store, run_id)
        active = status.get("status") in {"queued", "running"}
        event = app.state.cancel_events.get(run_id)
        if event is not None:
            event.set()
        if active:
            with store.locked(run_id):
                try:
                    current = store.read_status(run_id)
                except StoreError:
                    current = None
                if current and current.get("status") in {"queued", "running"}:
                    store.update_status(
                        run_id, status="cancelled", stage="cancelled", percent=0.0,
                        error={
                            "code": "RunCancelled",
                            "message": "Run cancelled because the reviewer deleted it.",
                            "retryable": False,
                        },
                    )
                    store.append_audit(
                        run_id, action="run.cancelled", object_type="run",
                        object_id=run_id, actor="reviewer",
                        reason="run deleted by reviewer while queued or running",
                    )
            # Give the worker a brief chance to unwind before removing the
            # directory. If it is still mid-stage, the deletion tombstone makes
            # every later store write fail instead of recreating the run.
            worker = app.state.run_workers.get(run_id)
            if worker is not None and worker is not threading.current_thread():
                worker.join(2.0)
            deadline = time.monotonic() + 2.0
            while (run_id in app.state.cancel_events
                   and time.monotonic() < deadline):
                time.sleep(0.01)
        app.state.cancel_events.pop(run_id, None)
        app.state.run_workers.pop(run_id, None)
        store.delete_run(run_id)
        return {"deleted": True, "run_id": run_id}

    return app


app = create_app()
