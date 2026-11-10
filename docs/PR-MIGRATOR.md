# PreFlight — Autonomous Multi-Agent Migrator

**Branch:** `feat/autonomous-migrator`
**Base:** `main` (follow-up to merged PR #1)
**New commit:** `Add autonomous multi-agent migrator with live agent orchestration`

## What this adds

A live `/migrator` workflow over a completed review run. Five specialist agents
run as deterministic handoffs and produce a sealed migration bundle:

| Agent | Job | Output |
|---|---|---|
| Scout | Resolve the feature and scope the evidence | Evidence-linked inventory |
| Architect | Turn explicit dispositions into target files | `migration/target/**` |
| Guardian | Convert findings and open assumptions into gates | Gate register |
| Critic | Verify paths, evidence, parseability, duplicates, and approval state | PASS/FAIL checks |
| Scribe | Seal the plan, report, and bundle manifest | Hashes + report |

### Live demo

```bash
make demo
# http://127.0.0.1:8000/migrator?run=R-DEMO-001
```

Press **Run again** to watch the handoffs live. The page polls state and updates
the crew, progress bar, summary, and verification status.

### CLI

```bash
.venv/bin/python -m app.cli migrate R-DEMO-001
.venv/bin/python -m app.cli verify-migration R-DEMO-001
```

### What is generated

Inside `data/runs/R-DEMO-001/`:

- `migration.json` — live state, agents, packages, gates, verification
- `migration/audit.jsonl` — hash-chained agent log (separate from the review audit)
- `migration/migration-plan.json`
- `migration/MIGRATION-REPORT.md`
- `migration/bundle-manifest.json`
- `migration/target/**` — 5 generated target drafts

## Honest boundary

This is **bounded autonomy**, not deployment:

- Every generated change remains `approval: pending`.
- The orchestrator never edits `_gen` files, approves its own changes, resolves
  an assumption, or contacts a Guidewire tenant.
- The run is `completed_with_gates` while 11 gates are open (3 assumptions,
  8 review-rule groups).
- The target bundle is local JSON/YAML, not a compiled Guidewire package.
- Official Cloud Assurance was not run.

## Verification

```text
pytest -q                                 421 passed
claims_lint.py                            claims-lint: OK
migrate R-DEMO-001                        completed_with_gates · 5/5 targets · 11 gates · verification passed
verify-migration R-DEMO-001               OK - 12 events verified (fresh seed)
verify-packet R-DEMO-001                  OK (packet hash, content digests, audit chain)
verify-audit R-DEMO-001                   OK (9 seed events)
```

The migrator has its own append-only hash chain so the review-run packet and
its 9-event seed audit remain reproducible.

## UI/API

- `GET /migrator?run=R-DEMO-001`
- `GET /api/runs/{run_id}/migration`
- `POST /api/runs/{run_id}/migration` (`{"force": true}` to rerun)
- `GET /api/runs/{run_id}/migration/file?path=migration/...`

## Tests

- Pipeline: bundle generation, 5/5 targets, 11 gates, pending approval, parsed
  JSON/YAML, evidence links, audit verification, tamper detection.
- API: launch/force, completed state, five done agents, rendered page with plan
  link and draft-ready targets.
- E2E: mobile navigation includes the new Migrator route with no overflow.
