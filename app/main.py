"""FastAPI product shell and JSON API for PreFlight."""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
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
from app.services.packet import DISCLAIMER, build_packet
from app.services.pipeline import RunCancelled, execute_run
from app.services.reconstruction import ReconstructionResult
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


class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    feature_id: str | None = None


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
    except StoreError:
        raise HTTPException(status_code=404, detail="run not found")


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


def _read(store: RunStore, run_id: str, name: str, default: Any) -> Any:
    try:
        return store.read_artifact(run_id, name)
    except StoreError:
        return default


def _assistant_context(store: RunStore, run_id: str):
    feature_payload = _read(store, run_id, "features.json", {"features": []})["features"]
    evidence_payload = _read(store, run_id, "evidence.json", {"evidence": []})["evidence"]
    gaps_payload = _read(store, run_id, "gaps.json", {"gaps": []})["gaps"]
    review_evidence = _read(store, run_id, "review_evidence.json", {"evidence": []})["evidence"]
    findings_payload = _read(
        store, run_id, "findings.json", {"findings": [], "readiness": []}
    )
    mappings_payload = _read(store, run_id, "mappings.json", {"mappings": []})["mappings"]
    changes_payload = _read(store, run_id, "changes.json", {"changes": []})["changes"]
    assumptions_payload = _read(store, run_id, "assumptions.json", {"assumptions": []})["assumptions"]

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
                    settings: Settings) -> tuple[bool, str | None]:
    """Rebuild the packet from current artifacts so its audit head is never stale.

    Returns ``(True, None)`` on success and ``(False, reason)`` when the artifact
    could not be refreshed. Callers must not present a stale export as current.
    """
    try:
        status = store.read_status(run_id)
        if status.get("status") != "succeeded":
            return False, f"run status is {status.get('status')!r}, not 'succeeded'"
        manifest_payload = _read(store, run_id, "manifest.json", None)
        if not manifest_payload:
            return False, "manifest.json is missing"
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
        build_packet(
            store=store, run_id=run_id, project_id=status.get("project_id", "demo"),
            fixture_id=status.get("fixture_id", "demo-slice-300"),
            release_context=release_context, manifest=manifest, discovery=discovery,
            review=review, reconstruction=reconstruction, comparison=comparison,
            evaluation=evaluation, reference_path=reference_path,
            reference_sha256=reference_sha256,
        )
        return True, None
    except Exception as exc:
        logger.warning("packet refresh failed for %s: %s", run_id, exc)
        return False, f"{type(exc).__name__}: {exc}"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="PreFlight", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.store = RunStore(settings.data_dir)
    app.state.cancel_events = {}

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
            view = load_run_view(app.state.store, run_id)
        except StoreError:
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
            view = load_run_view(app.state.store, run_id)
        except StoreError:
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
        refreshed, refresh_error = _refresh_packet(app.state.store, run_id, settings)
        view = load_run_view(app.state.store, run_id)
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
                status_code=503,
                detail=f"packet is unavailable for run status {status.get('status')!r}",
            )
        refreshed, refresh_error = _refresh_packet(store, run, settings)
        if not refreshed:
            raise HTTPException(
                status_code=503,
                detail=f"review packet refresh failed; refusing to export a stale artifact: {refresh_error}",
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

        if settings.sync_runs:
            target()
        else:
            threading.Thread(target=target, daemon=True, name=f"preflight-{run_id}").start()
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

        if settings.sync_runs:
            target_upload()
        else:
            threading.Thread(target=target_upload, daemon=True, name=f"preflight-{run_id}").start()
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
        if status.get("status") == "queued":
            store.update_status(run_id, status="cancelled", stage="cancelled", percent=0.0)
            store.append_audit(run_id, action="run.cancelled", object_type="run", object_id=run_id)
        return {"run_id": run_id, "cancelling": True}

    @app.get("/api/runs/{run_id}/manifest")
    def manifest_api(run_id: str, page: int = Query(default=1, ge=1),
                     size: int = Query(default=100, ge=1, le=500)):
        _status_or_404(app.state.store, run_id)
        view = load_run_view(app.state.store, run_id)
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
        _status_or_404(app.state.store, run_id)
        return {"features": _read(app.state.store, run_id, "features.json", {"features": []})["features"]}

    @app.get("/api/runs/{run_id}/features/{feature_id}")
    def feature_api(run_id: str, feature_id: str):
        store: RunStore = app.state.store
        _status_or_404(store, run_id)
        features = _read(store, run_id, "features.json", {"features": []})["features"]
        feature = next((f for f in features if f["feature_id"] == feature_id), None)
        if not feature:
            raise HTTPException(status_code=404, detail="feature not found")
        evidence = _read(store, run_id, "evidence.json", {"evidence": []})["evidence"]
        by_id = {e["evidence_id"]: e for e in evidence}
        return {"feature": feature, "evidence": [by_id[e] for e in feature["evidence_ids"] if e in by_id]}

    @app.get("/api/runs/{run_id}/spine")
    def spine_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        view = load_run_view(app.state.store, run_id)
        return {"schema_version": "1.0", "spines": view["spines"]}

    @app.get("/api/runs/{run_id}/findings")
    def findings_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        return _read(app.state.store, run_id, "findings.json", {"findings": [], "readiness": []})

    @app.get("/api/runs/{run_id}/mappings")
    def mappings_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        return _read(app.state.store, run_id, "mappings.json", {"mappings": []})

    @app.get("/api/runs/{run_id}/assumptions")
    def assumptions_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        return _read(app.state.store, run_id, "assumptions.json", {"assumptions": []})

    @app.get("/api/runs/{run_id}/gaps")
    def gaps_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        return _read(app.state.store, run_id, "gaps.json", {"gaps": []})

    @app.get("/api/runs/{run_id}/comparison")
    def comparison_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        return _read(app.state.store, run_id, "comparison.json", {"rows": [], "macro_f1": 0.0})

    @app.get("/api/runs/{run_id}/metrics")
    def metrics_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        return _read(app.state.store, run_id, "metrics.json", {"metrics": [], "supporting": []})

    @app.get("/api/runs/{run_id}/packet")
    def packet_api(run_id: str):
        _status_or_404(app.state.store, run_id)
        refreshed, refresh_error = _refresh_packet(app.state.store, run_id, settings)
        if not refreshed:
            raise HTTPException(
                status_code=503,
                detail=f"review packet refresh failed: {refresh_error}",
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
        _status_or_404(store, run_id)
        if body.action not in {"accept", "reject", "edit", "defer"}:
            raise HTTPException(status_code=400, detail="unknown action")
        created_assumption: dict[str, Any] | None = None
        if body.object_type == "mapping":
            payload = _read(store, run_id, "mappings.json", {"mappings": []})
            obj = next((m for m in payload["mappings"] if m["mapping_id"] == body.object_id), None)
            if not obj:
                raise HTTPException(status_code=404, detail="mapping not found")
            before = _json_hash(obj)
            state = {"accept": "accepted", "reject": "rejected", "defer": "deferred", "edit": "edited"}[body.action]
            obj["reviewer_state"] = state
            if body.action == "edit":
                if not body.edited_value:
                    raise HTTPException(status_code=400, detail="edit requires edited_value")
                obj["target_name"] = body.edited_value
            store.write_artifact(run_id, "mappings.json", payload)
            after = _json_hash(obj)
            if body.action == "reject":
                assumptions = _read(store, run_id, "assumptions.json", {"assumptions": []})
                next_id = f"A-DEC-{len(assumptions['assumptions']) + 1:02d}"
                created_assumption = {
                    "schema_version": "1.0", "assumption_id": next_id,
                    "statement": f"Mapping {body.object_id} was rejected by a reviewer: {body.reason}",
                    "impact": "medium", "impact_range_days": [1.0, 2.0],
                    "impact_basis": "Reviewer rejection of one mapping; rework and re-review.",
                    "impact_confidence": "low",
                    "impact_caveat": "Heuristic planning range; not a quote.",
                    "status": "open", "owner": "unassigned",
                    "question_to_ask": "What target should replace the rejected mapping?",
                    "related_mapping_id": body.object_id, "gap_id": None,
                }
                assumptions["assumptions"].append(created_assumption)
                store.write_artifact(run_id, "assumptions.json", assumptions)
        elif body.object_type == "change":
            payload = _read(store, run_id, "changes.json", {"changes": []})
            obj = next((c for c in payload["changes"] if c["change_id"] == body.object_id), None)
            if not obj:
                raise HTTPException(status_code=404, detail="change not found")
            before = _json_hash(obj)
            obj["approval_state"] = {"accept": "accepted", "reject": "rejected", "defer": "pending", "edit": "edited"}[body.action]
            obj["reviewer"] = "reviewer"
            obj["reviewed_at"] = _now()
            if body.action == "edit":
                obj["edited_value"] = body.edited_value
                obj["edit_reason"] = body.reason
            store.write_artifact(run_id, "changes.json", payload)
            after = _json_hash(obj)
        elif body.object_type == "finding":
            payload = _read(store, run_id, "findings.json", {"findings": [], "readiness": []})
            obj = next((f for f in payload["findings"] if f["finding_id"] == body.object_id), None)
            if not obj:
                raise HTTPException(status_code=404, detail="finding not found")
            before = _json_hash(obj)
            obj["decision"] = {"accept": "accepted", "reject": "rejected", "defer": "deferred", "edit": "accepted"}[body.action]
            store.write_artifact(run_id, "findings.json", payload)
            after = _json_hash(obj)
        else:
            raise HTTPException(status_code=400, detail="unsupported object_type")

        decision = store.record_decision(
            run_id, object_type=body.object_type, object_id=body.object_id,
            action=body.action, actor="reviewer", reason=body.reason,
            before_hash=before, after_hash=after,
        )
        _refresh_packet(store, run_id, settings)
        return {"decision": decision, "object": obj, "assumption": created_assumption}

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
        _status_or_404(store, run_id)
        app.state.cancel_events.pop(run_id, None)
        store.delete_run(run_id)
        return {"deleted": True, "run_id": run_id}

    return app


app = create_app()
