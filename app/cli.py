"""PreFlight command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import REPO, Settings
from app.services.intake import build_manifest, snapshot_hash
from app.services.packet import verify_packet_artifacts
from app.services.migrator import MIGRATION_ARTIFACT, run_migration, verify_migration_log
from app.services.pipeline import execute_run
from app.store import RunStore


def _store(args) -> RunStore:
    return RunStore(Path(args.data))


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")
    return 0


def cmd_seed(args) -> int:
    from scripts.seed_demo import seed

    result = seed(Path(args.data), "demo-slice-300", force=True)
    if result is None:
        print("demo run already exists")
        return 0
    print(f"seeded R-DEMO-001: {len(result.discovery.features)} features")
    return 0


def _frozen_fixture_hash(fixture_id: str) -> str | None:
    try:
        payload = json.loads(
            (REPO / "ground_truth" / "FROZEN.json").read_text(encoding="utf-8")
        )
        entry = payload.get("fixtures", {}).get(fixture_id, {})
        digest = entry.get("sha256") if isinstance(entry, dict) else None
    except (OSError, ValueError, TypeError):
        return None
    return digest if isinstance(digest, str) else None


def _evaluation_snapshot_matches(fixture: Path, fixture_id: str) -> bool:
    """Evaluation labels are only trustworthy for the frozen fixture or its canonical path."""
    try:
        if fixture.resolve() == (REPO / "fixtures" / fixture_id).resolve():
            return True
    except OSError:
        pass
    frozen = _frozen_fixture_hash(fixture_id)
    if frozen is None or not fixture.is_dir():
        return False
    try:
        return snapshot_hash(fixture) == frozen
    except OSError:
        return False


def cmd_analyze(args) -> int:
    store = _store(args)
    run_id = args.run_id or "R-CLI"
    if store.run_dir(run_id).exists():
        store.delete_run(run_id)
    store.create_run(run_id, project_id=args.project, snapshot_id=f"S-{run_id}",
                     fixture_id=args.fixture)
    fixture = Path(args.fixture_path) if args.fixture_path else REPO / "fixtures" / args.fixture
    reference = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"
    if args.fixture in {"demo-slice-300", "acme-pc-2026.10"} and not _evaluation_snapshot_matches(
        fixture, args.fixture
    ):
        print(
            f"warning: refusing to evaluate {fixture}: it is neither the canonical "
            f"fixtures/{args.fixture} snapshot nor a copy matching ground_truth/FROZEN.json; "
            "no metrics will be written",
            file=sys.stderr,
        )
        reference = None
    result = execute_run(fixture, store, run_id, project_id=args.project,
                         fixture_id=args.fixture, tier=args.tier,
                         reference_path=reference)
    print(f"{run_id}: {len(result.discovery.features)} features, "
          f"{len(result.review.findings)} findings")
    return 0


def cmd_verify_audit(args) -> int:
    store = _store(args)
    run_id = args.run_id
    if not run_id:
        runs = store.list_runs()
        if not runs:
            print("no runs found")
            return 1
        run_id = runs[-1]
    try:
        store.read_status(run_id)
    except Exception:
        print(f"run not found: {run_id}")
        return 1
    ok = store.verify_audit(run_id)
    events = store.read_audit(run_id)
    print(f"{run_id}: {'OK' if ok else 'TAMPERED'} ({len(events)} events, head {events[-1]['hash'][:16] if events else 'GENESIS'})")
    return 0 if ok else 1


def cmd_verify_packet(args) -> int:
    store = _store(args)
    run_id = args.run_id
    try:
        store.read_status(run_id)
    except Exception:
        print(f"run not found: {run_id}")
        return 1
    ok, reason = verify_packet_artifacts(store, run_id, include_content=True)
    detail = reason or "packet hash, content digests, and audit chain verified"
    print(f"{run_id}: {'OK' if ok else 'TAMPERED'} - {detail}")
    return 0 if ok else 1


def cmd_migrate(args) -> int:
    store = _store(args)
    try:
        state = run_migration(store, args.run_id, feature_id=args.feature, pace=0.0)
    except Exception as exc:
        print(f"migration failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        f"{args.run_id}: {state['status']} · {state['summary'].get('generated', 0)}/"
        f"{state['summary'].get('packages', 0)} targets · {state['summary'].get('gates', 0)} gates · "
        f"verification {state['verification']['status']}"
    )
    print(f"plan: {state['plan_path']} · report: {state['report_path']} · bundle: {state['bundle']['path']}")
    return 0


def cmd_verify_migration(args) -> int:
    store = _store(args)
    try:
        store.read_status(args.run_id)
    except Exception:
        print(f"run not found: {args.run_id}")
        return 1
    if not store.exists(args.run_id, MIGRATION_ARTIFACT):
        print(f"{args.run_id}: no migration artifact")
        return 1
    ok, detail = verify_migration_log(store, args.run_id)
    print(f"{args.run_id}: {'OK' if ok else 'TAMPERED'} - {detail}")
    return 0 if ok else 1


def cmd_claims_lint(args) -> int:
    from scripts.claims_lint import main as lint_main

    return lint_main()


def cmd_manifest(args) -> int:
    manifest = build_manifest(Path(args.fixture_path), snapshot_id="S-CLI", project_id="cli")
    print(f"{manifest.file_count} files, {manifest.total_size} bytes, hash {manifest.sha256}")
    print(f"{len(manifest.unsupported_paths)} unsupported/corrupt files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preflight", description="Offline cloud-readiness review")
    parser.add_argument("--data", default=str(Settings().data_dir), help="run-store directory")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the local product server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    seed = sub.add_parser("seed", help="seed the demo run")
    seed.set_defaults(func=cmd_seed)

    analyze = sub.add_parser("analyze", help="analyze a fixture")
    analyze.add_argument("--fixture", default="demo-slice-300")
    analyze.add_argument("--fixture-path", default=None)
    analyze.add_argument("--project", default="demo")
    analyze.add_argument("--run-id", default="R-CLI")
    analyze.add_argument("--tier", default="demo")
    analyze.set_defaults(func=cmd_analyze)

    verify = sub.add_parser("verify-audit", help="verify the hash-chained review log")
    verify.add_argument("run_id", nargs="?")
    verify.set_defaults(func=cmd_verify_audit)

    packet = sub.add_parser("verify-packet", help="verify the review packet hashes and content binding")
    packet.add_argument("run_id")
    packet.set_defaults(func=cmd_verify_packet)

    migrate = sub.add_parser("migrate", help="run the autonomous multi-agent migrator")
    migrate.add_argument("run_id")
    migrate.add_argument("--feature", default=None)
    migrate.set_defaults(func=cmd_migrate)

    verify_migration = sub.add_parser("verify-migration", help="verify the migrator agent log")
    verify_migration.add_argument("run_id")
    verify_migration.set_defaults(func=cmd_verify_migration)

    lint = sub.add_parser("claims-lint", help="lint the claims ledger and rule coverage")
    lint.set_defaults(func=cmd_claims_lint)

    manifest = sub.add_parser("manifest", help="print a snapshot manifest summary")
    manifest.add_argument("fixture_path")
    manifest.set_defaults(func=cmd_manifest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
