# Autonomous multi-agent migrator

`/migrator` is the autonomy layer on top of a completed PreFlight review run. It
is the answer to “what changes would a migration team actually make, and what
must a human decide before those changes ship?”

Five specialist agents run as deterministic handoffs over the persisted review
artifacts:

| Agent | Job | Output |
|---|---|---|
| **Scout** | Resolve the feature, scope the evidence, refuse an ungrounded slice | Evidence-linked inventory summary |
| **Architect** | Turn every explicit disposition into a target file | `migration/target/**` |
| **Guardian** | Convert open assumptions and review findings into blocking gates | Gate register |
| **Critic** | Adversarially verify paths, targets, evidence links, parseability, and approval state | PASS/FAIL checks |
| **Scribe** | Seal the plan, report, and bundle manifest | Plan + report + hashes |

## What “autonomous” means here

The agents run without a human in the loop and produce a complete draft bundle.
They **do not** deploy, edit `_gen` files, approve their own changes, resolve an
assumption, or contact a Guidewire tenant. Every work package is generated with
`approval: pending`. The run is intentionally reported as
`completed_with_gates` while assumptions or review findings remain open.

This is bounded autonomy: the machine does the repetitive reconstruction and
verification; a human still owns the change.

## Live demo

The seeded run already contains a completed migrator pass:

```bash
make demo
# http://127.0.0.1:8000/migrator?run=R-DEMO-001
```

Press **Run again** to watch the five agent handoffs live. The page polls the
run store and updates the crew, progress bar, and summary while the orchestrator
works.

## CLI

```bash
.venv/bin/python -m app.cli migrate R-DEMO-001
.venv/bin/python -m app.cli verify-migration R-DEMO-001
```

`verify-migration` checks the migrator’s own hash-chained
`migration/audit.jsonl`; it is separate from the review-run audit because the
review packet and its seed hashes remain reproducible.

## Artifacts

Inside `data/runs/<run_id>/`:

- `migration.json` — live state, agent results, packages, gates, verification
- `migration/audit.jsonl` — append-only, hash-chained agent log
- `migration/migration-plan.json` — sealed work plan
- `migration/MIGRATION-REPORT.md` — human-readable report
- `migration/bundle-manifest.json` — hashes and file inventory
- `migration/target/**` — generated, non-deployable target drafts

## API

- `GET /api/runs/{run_id}/migration` — current state
- `POST /api/runs/{run_id}/migration` — start/restart (`{"feature_id": "...", "force": true}`)
- `GET /api/runs/{run_id}/migration/file?path=migration/...` — plan/report download

## Optional AI QCer

The five deterministic agents are the evidence contract. An optional sixth
reviewer can challenge the sealed plan:

```bash
PREFLIGHT_AI_PROVIDER=ollama PREFLIGHT_AI_MODEL=qwen2.5:1.5b \
  .venv/bin/python -m app.cli ai-review R-DEMO-001
```

The AI receives only the plan and the evidence records cited by its packages.
It returns structured claims/risks/missing-checks/critique, and a deterministic
validator rejects the whole response on an unknown evidence ID, path, number,
overclaim, or malformed JSON. The AI has no tools, write path, approval, or
deployment. Its review is advisory and is **not** part of the sealed
deterministic bundle. See [`docs/AI.md`](AI.md) for the research and threat
model.

## Boundaries

This is not Guidewire Cloud Assurance, not a deployment tool, and not a live
tenant connector. The generated target files are local JSON/YAML drafts for
review, not a compiled Guidewire package. Official Cloud Assurance was not run.

For code-level refactoring, anti-pattern detection, SARIF export, and mid-migration
upgrade handling, see [`CODEBASE-MIGRATION.md`](CODEBASE-MIGRATION.md) and the
`/codebase` lab. The migrator and the codebase lab keep separate agent logs and
artifacts; neither edits the other.
