# PreFlight — Demo & Hardening PR Summary

**Branch:** `feat/deep-review-demo` (based on `main` @ `c72bb93`)
**Status:** pushed to the `alikhan37544/Preflight-CloudMigration` fork; cross-repo PR open against `SaundaryaSingh/Preflight-CloudMigration:main`.
**Scope:** demo/presentation 10/10 pass, evidence-packet integrity, evaluation
hardening, security/intake hardening, performance, and documentation.

## What this branch changes

### Demo and presentation

- 16-slide offline judge deck with speaker notes, print/PDF, keyboard/touch
  navigation, and capture-time evidence annotations:
  `docs/presentation/index.html`, `docs/presentation/PreFlight-deck.pdf`.
- 92 live screenshots and capture manifest:
  `docs/presentation/assets/`.
- Five-minute runbook, Q&A, source list, and machine-readable evidence:
  `docs/presentation/DEMO-RUNBOOK.md`, `sources.md`, `evidence.json`.
- Reproducible Playwright capture/validation/PDF script:
  `scripts/capture_demo.py`; evidence sync:
  `scripts/sync_presentation_evidence.py`.
- Demo iteration history and independent reviewer scores:
  `docs/presentation/ITERATION-LOG.md`.

### Product / demo UX

- Feature-scoped workbench summary; all eight feature spines.
- Manifest excluded filter with all four files and reasons.
- 1280/1024/390 layouts; sticky mapping decisions; accessible tabs and mobile
  nav; decision dialog with required reason, accept/reject differentiation,
  terminal state handling; inline A-DEC assumption notice and assumptions tab.
- Findings: source path/line, standard-family chips, claim colors, SBT
  readiness separated as a heuristic, 24-case precision-guard panel.
- Assistant transcript, citation cards, retryable errors, model-off scoping.
- Evaluation summary strip, interval chart, baselines, per-rule table, honest
  caveats.
- Packet page and downloadable packet: evidence-complete (126 evidence items,
  mappings, changes, readiness, excluded files, full audit trail), responsive,
  accessible tables (`main`, captions, `thead`, scoped headers), content-hash
  and audit verification.

### Integrity, security, and data handling

- Read-only snapshot manifest with symlink/special/unreadable handling.
- Hash-chained audit with per-run file locks, checkpoint, multi-process append,
  tombstone-safe delete, startup reconciliation.
- Transactional decisions with idempotency and terminal-state guards.
- Secret redaction for Gosu, XML elements/CDATA/attributes, JSON/YAML block
  scalars, reviewer reasons and edited values; redaction tests scan artifacts
  and packet output.
- Safe archive extraction (traversal, duplicate names, hardlinks, ratio/size
  caps, deep paths), XML/YAML hardening, CSRF/Host/Origin/CSP, stable demo
  secret.
- Packet tamper detection: `verify-packet` checks rendered HTML, canonical
  JSON, content digests, and audit head; `verify-audit` checks the chain only.

### Evaluation

- Metrics grounding and locator audits; all-link M3; evidence-valid M1/M2/M6;
  extra-rule/unlabelled false positives; stable M5 allowance; clamping.
- `docs/EVALUATION-SCOPE.md` states the demo-tier scope, residual limitations,
  and what a thesis/pilot tier would require.

## Verification (current branch)

```text
pytest -q                                 421 passed
claims_lint.py                            claims-lint: OK
test_freeze_manifest.py                   18/18 frozen hashes recompute
preflight verify-packet R-DEMO-001        OK (packet hash, content digests, audit chain)
preflight verify-audit R-DEMO-001         OK (9 seed events)
demo deck                                16 slides x 5 viewports, 0 failures,
                                          0 console errors, 0 external requests
PDF                                      16 pages, 1200 x 675.12 pt
independent demo panel                   8.0 judge / 8.2 UX / 8.5 domain / 8.0 engineering
```

## How to run

```bash
make install
make demo
# http://127.0.0.1:8000/?run=R-DEMO-001
python -m http.server 8090 -d docs/presentation
# http://127.0.0.1:8090/index.html
make test
```

## Push / PR

The authenticated account has read-only access to the upstream repository, so the
branch is published from a fork:

```bash
git remote add fork https://github.com/alikhan37544/Preflight-CloudMigration.git
git push -u fork feat/deep-review-demo
gh pr create --repo SaundaryaSingh/Preflight-CloudMigration \
  --base main --head alikhan37544:feat/deep-review-demo \
  --title "PreFlight: evidence-first demo, packet integrity, and evaluation hardening" \
  --body-file docs/PR-SUMMARY.md
```

The upstream owner can merge the cross-repo PR directly.

## Known limitations

- Demo metrics are in-sample on one synthetic 300-file fixture; this is not a
  benchmark or a generalisation claim.
- The reference target is internally authored and AI-assisted.
- No human inter-annotator agreement or real anonymised estate has been run.
- The `_ext` draft is a local, non-deployable JSON contract, not Guidewire
  schema/mapping/updater syntax.
- The thesis-tier protocol is planned, not delivered; see
  `docs/EVALUATION-SCOPE.md`.
- Official Cloud Assurance was not run.
