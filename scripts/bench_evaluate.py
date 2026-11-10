"""Benchmark the evaluation harness on demo, 5k, and ~200MB synthetic clones.

The clone builders only add neutral synthetic files to an existing fixture; the
gold anchors and labelled paths are unchanged. Use ``--keep`` to reuse a clone.

Examples:
    python scripts/bench_evaluate.py --case demo
    python scripts/bench_evaluate.py --case 5k --case 200mb
    python scripts/bench_evaluate.py --case 200mb --no-setup

Times are wall-clock seconds; RSS is the process peak (``ru_maxrss``). Run each
case in a fresh process if you need an isolated RSS number.
"""

from __future__ import annotations

import argparse
import json
import pickle
import resource
import shutil
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.services.compare import compare_feature  # noqa: E402
from app.services.discovery import run_discovery  # noqa: E402
from app.services.evaluate import evaluate_run  # noqa: E402
from app.services.intake import build_manifest  # noqa: E402
from app.services.reconstruction import reconstruct  # noqa: E402
from app.services.review import run_review  # noqa: E402
from app.store import RunStore  # noqa: E402

GROUND = REPO / "ground_truth"
DEMO = REPO / "fixtures" / "demo-slice-300"
ACME = REPO / "fixtures" / "acme-pc-2026.10"

FIVE_K_FILES = 5000
BIG_TARGET_BYTES = 200 * 1024 * 1024
BIG_FILE_BYTES = 100 * 1024


def _peak_rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _clone(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _neutral_gosu(index: int) -> str:
    return (
        "// Synthetic benchmark filler. No anchors or finding patterns.\n"
        f"package bench.filler\nclass BenchFiller{index} {{\n"
        f"  function value() : int {{ return {index} }}\n"
        "}\n"
    )


def prepare_case(case: str, workdir: Path) -> tuple[Path, str]:
    """Return ``(fixture_root, fixture_id)`` for a named benchmark case."""
    if case == "demo":
        return DEMO, "demo-slice-300"
    if case == "acme":
        return ACME, "acme-pc-2026.10"
    if case == "5k":
        target = workdir / "scale-5k"
        if not target.exists():
            _clone(DEMO, target)
        current = sum(1 for path in target.rglob("*") if path.is_file())
        index = 0
        while current < FIVE_K_FILES:
            path = target / "generated" / "bench" / f"Filler{index}.gs"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_neutral_gosu(index), encoding="utf-8")
            current += 1
            index += 1
        return target, "demo-slice-300"
    if case == "200mb":
        target = workdir / "scale-200mb"
        if not target.exists():
            _clone(DEMO, target)
            target_bytes = sum(
                path.stat().st_size for path in target.rglob("*") if path.is_file()
            )
            index = 0
            payload = (
                "// Synthetic benchmark padding. No anchors or finding patterns.\n"
                + ("val filler = 1\n" * (BIG_FILE_BYTES // 15))
            )
            while target_bytes < BIG_TARGET_BYTES:
                path = target / "generated" / "bench" / "large" / f"Large{index}.gs"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
                target_bytes += path.stat().st_size
                index += 1
        return target, "demo-slice-300"
    raise SystemExit(f"unknown case: {case}")


def build_inputs(root: Path, fixture_id: str, store: RunStore, run_id: str):
    manifest = build_manifest(root, snapshot_id="S-BENCH", project_id="P-BENCH")
    discovery = run_discovery(root, manifest)
    reconstruction = reconstruct(
        root, manifest, discovery, "PA-VEH-01", store=store, run_id=run_id,
        draft_root=store.run_dir(run_id) / "draft",
    )
    review = run_review(root, manifest, discovery, include_thesis=False)
    reference = json.loads(
        (GROUND / "reference_target" / "pa_veh_01_reference.json").read_text(
            encoding="utf-8"
        )
    )
    comparison = compare_feature(reference, reconstruction.mappings, discovery.evidence)
    return manifest, discovery, reconstruction, review, comparison


def metric_counts(result) -> dict[str, str]:
    rows = {}
    for metric in result.metrics:
        rows[metric.metric_id] = f"{metric.numerator}/{metric.denominator}"
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=["demo", "acme", "5k", "200mb"],
                        dest="cases", help="benchmark case (repeatable)")
    parser.add_argument("--workdir", type=Path,
                        default=Path("/tmp/opencode/preflight-bench"))
    parser.add_argument("--repeat", type=int, default=3,
                        help="evaluation repetitions (default: 3)")
    parser.add_argument("--no-setup", action="store_true",
                        help="load pickled inputs from --workdir and only time evaluation")
    parser.add_argument("--cache-inputs", action="store_true",
                        help="pickle the built inputs after setup for later --no-setup runs")
    parser.add_argument("--json", action="store_true", help="emit one JSON object")
    args = parser.parse_args()
    cases = args.cases or ["demo"]
    args.workdir.mkdir(parents=True, exist_ok=True)

    reports = []
    for case in cases:
        root, fixture_id = prepare_case(case, args.workdir)
        cache_path = args.workdir / f"inputs-{case}.pkl"
        setup_seconds = 0.0
        if args.no_setup or args.cache_inputs:
            if cache_path.is_file():
                with cache_path.open("rb") as handle:
                    manifest, discovery, reconstruction, review, comparison = pickle.load(handle)
            elif args.no_setup:
                raise SystemExit(f"no cached inputs for {case}; run without --no-setup first")
            else:
                store = RunStore(args.workdir / f"data-{case}")
                run_id = "R-BENCH"
                store.create_run(run_id, project_id="P-BENCH", snapshot_id="S-BENCH",
                                 fixture_id=fixture_id)
                started = time.perf_counter()
                inputs = build_inputs(root, fixture_id, store, run_id)
                setup_seconds = time.perf_counter() - started
                manifest, discovery, reconstruction, review, comparison = inputs
                with cache_path.open("wb") as handle:
                    pickle.dump(inputs, handle, protocol=pickle.HIGHEST_PROTOCOL)
        else:
            store = RunStore(args.workdir / f"data-{case}")
            run_id = "R-BENCH"
            store.create_run(run_id, project_id="P-BENCH", snapshot_id="S-BENCH",
                             fixture_id=fixture_id)
            started = time.perf_counter()
            manifest, discovery, reconstruction, review, comparison = build_inputs(
                root, fixture_id, store, run_id
            )
            setup_seconds = time.perf_counter() - started

        timings = []
        result = None
        for _ in range(max(1, args.repeat)):
            started = time.perf_counter()
            result = evaluate_run(
                fixture_id=fixture_id, manifest=manifest, discovery=discovery,
                reconstruction=reconstruction, review=review, comparison=comparison,
                ground_truth_dir=GROUND, tier="demo", fixture_root=root,
            )
            timings.append(time.perf_counter() - started)

        report = {
            "case": case,
            "fixture_root": str(root),
            "files": manifest.file_count,
            "bytes": manifest.total_size,
            "setup_seconds": round(setup_seconds, 3),
            "eval_seconds": [round(value, 3) for value in timings],
            "eval_best_seconds": round(min(timings), 3),
            "eval_median_seconds": round(statistics.median(timings), 3),
            "peak_rss_mb": round(_peak_rss_mb(), 1),
            "metrics": metric_counts(result),
            "warnings": list(result.warnings),
        }
        reports.append(report)
        if not args.json:
            print(json.dumps(report, sort_keys=True))
    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
