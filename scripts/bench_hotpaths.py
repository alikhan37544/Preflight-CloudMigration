"""Benchmark the parser, audit-append, packet, and workbench hot paths.

Each suite builds its own synthetic input under ``--workdir`` (default
``/tmp/opencode/preflight-hotpaths``) unless the input already exists. Times are
wall-clock seconds and RSS is ``VmHWM`` from ``/proc/self/status``.

Examples:
    python scripts/bench_hotpaths.py --suite gosu
    python scripts/bench_hotpaths.py --suite pcf
    python scripts/bench_hotpaths.py --suite audit
    python scripts/bench_hotpaths.py --suite packet
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _peak_rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def _timed(fn, *args, **kwargs):
    started = time.perf_counter()
    value = fn(*args, **kwargs)
    return value, time.perf_counter() - started


def build_gosu(path: Path, classes: int = 40_000) -> None:
    if path.is_file() and path.stat().st_size >= 5 * 1024 * 1024:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    padding = "// " + ("synthetic padding " * 8) + "\n"
    with path.open("w", encoding="utf-8") as handle:
        handle.write("package bench.gosu\n\n")
        for index in range(classes):
            handle.write(padding)
            handle.write(
                f"class BenchClass{index} {{\n"
                f"  function value{index}() : int {{ return {index} }}\n"
                "}\n"
            )


def suite_gosu(workdir: Path) -> dict:
    from app.services.parsers.gosu import scan_gosu

    path = workdir / "gosu-large.gs"
    build_gosu(path)
    doc, seconds = _timed(scan_gosu, path)
    return {
        "suite": "gosu",
        "file_mb": round(path.stat().st_size / (1024 * 1024), 2),
        "classes": len(doc.classes),
        "seconds": round(seconds, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "last_class_line": doc.classes[-1].line if doc.classes else None,
    }


def build_pcf(path: Path, widgets: int = 20_000) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write('<?xml version="1.0"?>\n<PCF name="Bench"><Screen name="Bench">\n')
        for index in range(widgets):
            handle.write(
                f'  <TextInput id="Field{index}" value="Field{index}" '
                f'label="Field{index}"/>\n'
            )
        handle.write("</Screen></PCF>\n")


def suite_pcf(workdir: Path) -> dict:
    from app.services.parsers.pcf import parse_pcf

    path = workdir / "pcf-large.pcf"
    build_pcf(path)
    doc, seconds = _timed(parse_pcf, path)
    return {
        "suite": "pcf",
        "widgets": len(doc.widgets),
        "seconds": round(seconds, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "first_xpath": doc.widgets[0].xpath if doc.widgets else None,
        "last_xpath": doc.widgets[-1].xpath if doc.widgets else None,
    }


def suite_audit(workdir: Path) -> dict:
    import shutil

    from app.store import RunStore

    data = workdir / "audit-data"
    if data.exists():
        shutil.rmtree(data)
    store = RunStore(data)
    run_id = "R-AUDIT-BENCH"
    store.create_run(run_id)
    events = 2000

    started = time.perf_counter()
    for index in range(events):
        store.append_audit(
            run_id, action="mapping.reviewed", object_type="mapping",
            object_id=f"M-{index}",
        )
    append_seconds = time.perf_counter() - started
    verified, verify_seconds = _timed(store.verify_audit, run_id)
    return {
        "suite": "audit",
        "events": events,
        "append_seconds": round(append_seconds, 3),
        "appends_per_second": round(events / append_seconds, 1),
        "verify_seconds": round(verify_seconds, 3),
        "verified": verified,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }


def _synthetic_packet_run(store, run_id: str, evidence_count: int = 20_000) -> None:
    from app.models import (
        Confidence, Evidence, Feature, Locator, LocatorKind, Manifest,
        make_evidence,
    )

    store.create_run(run_id, project_id="P-BENCH", snapshot_id="S-BENCH",
                     fixture_id="demo-slice-300")
    manifest = Manifest(
        snapshot_id="S-BENCH", project_id="P-BENCH", sha256="0" * 64,
        artifacts=[], file_count=evidence_count, total_size=evidence_count * 100,
    )
    store.write_artifact(run_id, "manifest.json", manifest.model_dump(mode="json"))
    evidence = [
        make_evidence(
            evidence_id=f"EV-{index:05d}",
            path=f"generated/bench/File{index:05d}.pcf",
            locator=Locator(kind=LocatorKind.LINE, value=f"line {index % 20 + 1}",
                            line=index % 20 + 1),
            excerpt=f"Synthetic evidence excerpt number {index} for packet benchmark.",
            method="lexer", confidence=Confidence.PARSED,
        )
        for index in range(evidence_count)
    ]
    store.write_artifact(run_id, "evidence.json", {
        "schema_version": "1.0",
        "evidence": [item.model_dump(mode="json") for item in evidence],
    })
    store.write_artifact(run_id, "review_evidence.json",
                         {"schema_version": "1.0", "evidence": []})
    feature = Feature(
        feature_id="PA-VEH-01", capability="vehicle_information",
        name="Vehicle Information", lob="PersonalAuto", description="benchmark",
        evidence_ids=[item.evidence_id for item in evidence[:20]],
        dependencies=[], confidence=Confidence.PARSED, open_questions=[],
    )
    store.write_artifact(run_id, "features.json", {
        "schema_version": "1.0", "features": [feature.model_dump(mode="json")],
    })
    store.write_artifact(run_id, "gaps.json", {"schema_version": "1.0", "gaps": []})
    store.write_artifact(run_id, "spine.json", {"schema_version": "1.0", "spines": {}})
    store.write_artifact(run_id, "findings.json", {
        "schema_version": "1.0", "findings": [], "readiness": [],
    })
    store.write_artifact(run_id, "mappings.json", {"schema_version": "1.0", "mappings": []})
    store.write_artifact(run_id, "changes.json", {"schema_version": "1.0", "changes": []})
    store.write_artifact(run_id, "assumptions.json",
                         {"schema_version": "1.0", "assumptions": []})
    store.write_artifact(run_id, "comparison.json", {
        "schema_version": "1.0", "macro_f1": 0.0, "confusion": {}, "rows": [],
    })
    store.write_artifact(run_id, "decisions.json", {"schema_version": "1.0", "decisions": []})
    store.update_status(
        run_id, status="succeeded", stage="succeeded", percent=100.0,
        metadata={"release_context": "Bench 2026.08"},
    )
    store.append_audit(run_id, action="run.succeeded", object_type="run", object_id=run_id)

    from app.services.compare import CompareResult
    from app.services.discovery import DiscoveryResult
    from app.services.packet import build_packet
    from app.services.reconstruction import ReconstructionResult
    from app.services.review import ReviewResult

    build_packet(
        store=store, run_id=run_id, project_id="P-BENCH",
        fixture_id="demo-slice-300", release_context="Bench 2026.08",
        manifest=manifest, discovery=DiscoveryResult(features=[feature], evidence=evidence),
        review=ReviewResult(), reconstruction=ReconstructionResult(
            feature_id="PA-VEH-01", mappings=[], changes=[], assumptions=[],
            draft_root=Path("."), draft_files={}, patch_diff="", spines={},
        ), comparison=CompareResult(rows=[], macro_f1=0.0),
        evaluation=None, reference_path=None, reference_sha256=None,
    )


def suite_packet(workdir: Path) -> dict:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.store import RunStore

    data = workdir / "packet-data"
    store = RunStore(data)
    run_id = "R-PACKET-BENCH"
    if not store.exists(run_id, "packet.json"):
        _synthetic_packet_run(store, run_id)

    settings = Settings(
        data_dir=data, fixtures_dir=REPO / "fixtures",
        reference_path=None, secret_key="bench-secret", sync_runs=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        # Warm import/route caches, then measure a cold-enough second view.
        client.get(f"/packet?run={run_id}")
        response, seconds = _timed(client.get, f"/packet?run={run_id}")
        workbench, workbench_seconds = _timed(
            client.get, f"/?run={run_id}&feature=PA-VEH-01"
        )
    return {
        "suite": "packet",
        "packet_get_seconds": round(seconds, 3),
        "packet_bytes": len(response.content),
        "workbench_seconds": round(workbench_seconds, 3),
        "workbench_bytes": len(workbench.content),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }


SUITES = {
    "gosu": suite_gosu,
    "pcf": suite_pcf,
    "audit": suite_audit,
    "packet": suite_packet,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append",
                        choices=sorted(SUITES), dest="suites")
    parser.add_argument("--workdir", type=Path,
                        default=Path("/tmp/opencode/preflight-hotpaths"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    reports = []
    for name in args.suites or ["all"]:
        names = sorted(SUITES) if name == "all" else [name]
        for suite in names:
            report = SUITES[suite](args.workdir)
            reports.append(report)
            if not args.json:
                print(json.dumps(report, sort_keys=True))
    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
