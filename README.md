# PreFlight

**Independent Cloud-Readiness Review for InsuranceSuite-Style Estates.**

PreFlight is an offline, evidence-first review product for legacy Guidewire-style estates. It scans a
snapshot read-only, assembles business features across PCF, entities, typelists, extracted templates,
Gosu, and Cloud API configuration, and produces an evidence-linked review packet with one local Cloud API
extension draft, an impact-rated assumption register, and a hash-chained review trail.

> Every claim has evidence; every unknown has a name; every change waits for a human.

**Scenario:** Cloud Retrofit without APD App for a non-APD-native Personal Auto estate. The target draft is
local and non-deployable. PreFlight is not an APD converter, Cloud Retrofit replacement, Cloud Assurance
scorer, generic Gosu linter, live-tenant connector, or autonomous migration agent. **Official Cloud
Assurance: not run.**

## Quick start

```bash
make install        # Python 3.12 venv, dependencies, Chromium
make demo           # generate fixtures, seed R-DEMO-001, start tmux session
# open http://127.0.0.1:8000/?run=R-DEMO-001
```

The demo server auto-restarts if it is stopped inside tmux. Detach with `Ctrl+b` then `d`; stop the
demo with `make stop`. Do not use `Ctrl+C` to leave the demo. `/health`, `/api/health`, and `/v1/models`
are available for local probe compatibility; `/v1/models` returns an empty model list because PreFlight
is not an LLM server.

Or foreground:

```bash
make demo-fg
```

The demo uses `fixtures/demo-slice-300` for live import; `fixtures/northstar-pc-2026.10` is a holdout and
is never imported into the demo or used to author rules.

## What the demo shows

1. **Workbench** — eight features, a cross-artefact spine, evidence drawer, grounded assistant, gaps.
2. **Manifest** — 300 files hashed; unsupported, binary, and corrupt files listed, not hidden.
3. **Reconstruction** — 12 explicit dispositions, draft files and diff, three impact-rated assumptions,
   accept/reject/defer with audit.
4. **Findings** — eight demo rules with claim strength, a deliberate `Query` hard negative, and
   “Official Cloud Assurance: not run.”
5. **Evaluation** — six headline metrics with numerators/denominators, Wilson intervals, baselines and margins, per-rule table, caveats.
6. **Packet** — six sections, assumption register, hashes, audit head, downloadable HTML.

## Tests

```bash
make test           # full pytest suite (unit, API, security, pipeline, E2E)
make e2e            # Playwright golden path + screenshots
make claims         # claims-ledger and rule-coverage gate
make verify         # verify the hash-chained audit log
```

Test-first order: models → intake → parsers → store → discovery → reconstruction → review → compare →
evaluate → assistant → pipeline → API → security → claims → E2E.

## Architecture

- Python 3.12, FastAPI, Jinja2, vanilla JS/CSS.
- `lxml` for XML/PCF, `ruamel.yaml` with line marks, Pydantic v2 contracts, JSON run store with SQLite-free
  inspectability and a hash-chained `audit.jsonl`.
- Source snapshot is read-only; hashes are checked before and after analysis.
- Draft writes only under `data/runs/<run>/draft/`; `_gen` files are never written or edited.
- Security: loopback bind, Host/Origin allowlist, CSRF synchronizer token, SameSite=Strict, CSP,
  zip-slip/bomb controls, safe XML/YAML, secret redaction at capture, POST-only mutations.
- No telemetry, no external calls, no live tenant, optional LLM off.

## Layout

```text
app/                 FastAPI routes, contracts, services, templates, static
app/services/        intake, parsers, discovery, reconstruction, review, compare, evaluate, assistant
rules/               feature, mapping, and review rule packs (YAML)
fixtures/            synthetic main estate, demo slice, naming-shift holdout
ground_truth/        pre-registration, frozen hashes, gold features/mappings/findings, reference target
scripts/             fixture generator, seed, freeze, claims lint
tests/               test-first suite and browser golden path
docs/                claims ledger, target format, security contract, screenshots
plans/               vetted build contract and handoff
```

## Claims and boundaries

- Independent research prototype; not affiliated with, endorsed by, or certified by Guidewire Software, Inc.
- Guidewire, InsuranceSuite, PolicyCenter, ClaimCenter, BillingCenter, Gosu, APD, Jutro, Integration
  Gateway, Cloud Assurance, Developer Assistants, Guidewire Cloud Platform, and InsuranceNow are
  trademarks or registered trademarks of Guidewire Software, Inc.
- Synthetic fixture only; no customer data or confidential Guidewire information.
- Findings are pattern-based heuristics and claim strength is labelled per finding. They are not official
  Cloud Standards checks.
- Impact ranges are heuristic planning ranges, not quotes or measured productivity claims.
- No reviewer-effort or real-estate generalisation claim.

See `docs/claims-ledger.json` (canonical machine-readable ledger), `docs/target-format.md`,
`docs/security.md`, and `ground_truth/PRE_REGISTRATION.md`.

## Known limitations

- The reference target is internally authored and AI-assisted; it is not independently blind.
- Demo metrics are in-sample on the development slice; the naming-shift holdout is pre-computed.
- M3 audits excerpt support at the source, not semantic entailment.
- M5 uses a fixed two-decoy top-8 allowance, not a learned ranking.
- No human inter-annotator study was run; no reviewer-effort or generalisation claim is made.
- The extension draft is local and non-deployable; it is not compiled or tenant-validated.
