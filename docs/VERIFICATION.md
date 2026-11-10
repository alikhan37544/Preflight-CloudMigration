# PreFlight — Internal QA and Adversarial Review Record

**Date:** 8 November 2026
**Product:** local `R-DEMO-001` / `demo-slice-300`
**Rule:** internal verifier agents were read-only; findings below were fixed and re-tested. This is internal QA, not independent third-party certification.

## Verification rounds

| Round | Reviewer | Scope | Verdict | Score | Main findings |
|---|---|---|---|---|---|
| 1 | Domain / claims | Guidewire facts, rule IDs, target paths, claims ledger, disclaimers | REVISE → fixed | 7.2/10 | scenario/path corrections, invented mapping provenance, rule-ID misuse |
| 1 | Product / architecture | IA, target format, demo, security, test-first delivery | REVISE → fixed | 6.8/10 | fake chrome, evaluation overclaim, contract gaps |
| 1 | Evaluation | ground truth, metrics, holdout, baselines | REVISE → fixed | 4.5/10 | circular metrics, no freeze, no independent target |
| 1 | Judge / demo | hook, wow, Q&A | REVISE → fixed | 6.8/10 | dashboard-first demo, weak “so what?” |
| 2 | Domain final | claims/evaluation integrity | FIX → fixed | 6.5/10 | codegen 13th mapping, synthetic label, C-032, M4/M5, freeze |
| 2 | Product final | states, decisions, packet, responsive | FIX → fixed | 7.5/10 | evidence below fold, reject loop, stale packet head, `/runs` empty |
| 2 | Evaluation final | M1–M6, baselines, freeze, gold files | FIX → fixed | 4/10 | freeze uncommitted, gold not hashed, hardcoded mappings, M4 source hole, M5 allowance, missing margins |
| 2 | Adversarial FP | 32 + 23 near-miss cases | FIX → fixed | 6/10 | SEC concatenation/key names, LOG masking, SQL declarations, path variants |
| 3 | Product confirmation | final product gate | **SHIP** | **9/10** | no genuine blockers; only non-blocking polish |
| 3 | Evaluation confirmation | final metric gate | FIX → fixed | 7–8/10 | F1 fraction labels, baseline descriptions, M6 line-matching claim |
| 3 | Claims/FP confirmation | final precision gate | FIX → fixed | 7–8/10 | SEC adjacent-comment/escaped-quote redaction |
| 3 | Final focused confirmation | SEC redaction, evaluation labels, freeze | **SHIP** | **10/10** | targeted adversarial tests, raw-secret scan, 18/18 freeze hashes, screenshot hash match |

## Fixes applied after the final reviews

- Metrics:
  - M1/M2 require a gold anchor path; adversarial bogus-feature test.
  - M3 is an all-link excerpt-support audit (101/101 in the demo); the 30-link stratified sample is supporting only; fabricated excerpts fail.
  - M4 checks source, target, disposition, snapshot grounding, and penalises extra/duplicate mappings; adversarial tests added.
  - M5 has a gold issue file with an anchored signal and a stable top-8 allowance labelled 6/8, not a hidden ranking.
  - M6 uses 8 rules × 3 positives + 3 hard negatives; forged evidence and unlabelled false positives are penalised.
  - Freeze now hashes fixtures, reference, annotation guide/concordance, rule pack, pre-registration, claims ledger, and all scored gold files.
- Reconstruction loads `rules/mapping_rules.yaml`; no mapping rows live in code.
- Reference target is labelled internally authored, AI-assisted, not independent.
- Holdout is excluded from importable fixtures; its aggregate is pre-computed.
- Codegen draft has 12 dispositions; `GarageLocation` carries `{nameOverride: GarageLocation_Ext, requiredForCreate: false}` and the updater maps `garageLocation → GarageLocation_Ext`. The earlier “GarageLocation override removed” note is obsolete.
- Deterministic rule engine fixes: comments/strings masked, SEC typed/snake/camel names, all secrets redacted from evidence, SQL custom method names, SBT XML attributes, LOG-001 call-site and multiline handling, TX multiple commits, path-segment classification.
- Product shell: `/runs` restored; failed/loading pages; accepted/rejected row persistence; packet refresh; owner/status in packet; excluded-file filter; holdout lock; responsive overflow.
- Claims: C-002/C-014/C-016 URLs, C-018/C-036 PCF wording, C-032 rules present as `emitted: false`, reference limitations disclosed.

## Final local gates (evidence)

```text
pytest -q                                 421 passed
pytest tests/test_false_positives.py ...  adversarial precision suite passes
scripts/claims_lint.py                    claims-lint: OK
test_freeze_manifest.py                   every fixture/gold/reference/rulepack/ledger hash recomputes
preflight verify-packet R-DEMO-001        OK (packet hash, content digests, audit head)
preflight verify-audit R-DEMO-001         OK (9 seed events; 11 after runbook actions; audit chain only)
packet audit head == audit log head       true
Playwright golden path                    passes (accept/reject dialog, mobile layout, packet, evaluation)
```

## Final status

**Current internal gate: PASS for the demo path.** 421 tests pass; packet HTML/JSON tamper checks fail closed; XML/CDATA, inline YAML block, and reviewer-entered values are redacted; freeze hashes recompute. Independent demo reviewers scored Loop 2 at 7/10; the presentation is still being hardened. The residual limitations below remain disclosed.

## Residual limitations (disclosed, not hidden)

- Reference target is internally authored and AI-assisted; not human-independent.
- Demo metrics are in-sample on the development slice; holdout is pre-computed and naming-shift only.
- M3 audits excerpt support, not semantic entailment.
- M5 uses a fixed two-decoy top-8 allowance, not a learned ranking.
- M6 line-level matching is deferred; path-level matching is used in the demo tier.
- No human inter-annotator study; no reviewer-effort or real-estate generalisation claim.
- The Cloud API extension draft is local and non-deployable; it is not compiled or tenant-validated.
- Official Cloud Assurance was not run.

## Demo-readiness panel (10 November 2026)

Four independent reviewers inspected the live app and the offline deck with
their own screenshots at 1440x900, 1280x900, 1024x768, and 390x844. Each scored
the demo separately after five hardening loops.

| Reviewer | Loop 3 | Loop 4 final | Main evidence checked |
|---|---:|---:|---|
| Judge / demo | 7.0 | **8.0** | Full script on an isolated copy; live seed intact; packet/audit verification; deck/PDF |
| UX / accessibility | 7.5 | **8.2** | 0 axe violations; 1280/390 layouts; dialogs; packet export semantics; keyboard |
| Guidewire domain | 6.0 | **8.5** | ERR00-G, A-03 counts, CUE, APD conversion scope, GarageLocation_Ext, verify-packet |
| Engineering | 7.5 | **8.0** | 421 tests, 92/92 asset hashes, packet tamper/audit checks, CSRF, redaction |

The panel found no remaining demo blockers. Residual limitations are the
synthetic in-sample evaluation, internally authored reference target, no human
inter-annotator study, non-deployable draft, and the demo-tier scope. See
`docs/EVALUATION-SCOPE.md` and `docs/presentation/ITERATION-LOG.md`.

### Evaluation hardening after the demo

- M1/M2 anchors require locator-supported evidence.
- M3 audits every discovery link and rejects invalid XPath rather than falling
  back to a line match.
- M6 requires every evidence link on a finding to be supported; findings from
  extra (non-gold) rules count as false positives in the `UNLABELLED` row.
- `annotation_concordance.json` no longer reports kappa; it is an aggregate
  AI-assisted pass, not human IAA.
- The PCF baseline is labelled "PCF filename baseline", not "PCF+grep".
- Holdout is labelled capability recall under a naming-shift fixture.

## Autonomous migrator (10 November 2026)

- **Implementation:** `app/services/migrator.py`, `/migrator`, `/api/runs/{run_id}/migration`.
- **Fresh seed:** five agents complete; 5/5 work packages generated; 11 open gates; verification PASS.
- **Independent log:** `migration/audit.jsonl` hash chain verifies (`verify-migration`).
- **Review-run integrity:** review audit remains at its 9 seed events; `verify-packet` still passes.
- **Safety:** every package has `approval: pending`; the orchestrator writes only
  `migration/target/**` and cannot approve, deploy, or resolve an assumption.
