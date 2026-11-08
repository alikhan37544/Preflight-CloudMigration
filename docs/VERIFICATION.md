# PreFlight — Independent Verification Record

**Date:** 8 November 2026
**Product:** local `R-DEMO-001` / `demo-slice-300`
**Rule:** verifier agents were read-only; every finding below was fixed and re-tested before the final freeze.

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
| 3 | Final focused confirmation | SEC redaction, evaluation labels, freeze | **SHIP** | **10/10** | 61 targeted tests, zero raw secret values in evidence/artifacts, 21/21 freeze hashes, screenshot hash match |

## Fixes applied after the final reviews

- Metrics:
  - M1/M2 require a gold anchor path; adversarial bogus-feature test.
  - M3 is a stratified 30-link excerpt-support audit; fabricated excerpts fail.
  - M4 checks source, target, disposition, and penalises extra/duplicate mappings; adversarial tests added.
  - M5 has a gold issue file with a top-8 allowance labelled 6/8, not a hidden ranking.
  - M6 uses 8 rules × 3 positives + 3 hard negatives; micro-F1 headline, macro-F1 supporting, no invalid interval.
  - Freeze now hashes fixtures, reference, annotation guide/concordance, rule pack, pre-registration, claims ledger, and all scored gold files.
- Reconstruction loads `rules/mapping_rules.yaml`; no mapping rows live in code.
- Reference target is labelled internally authored, AI-assisted, not independent.
- Holdout is excluded from importable fixtures; its aggregate is pre-computed.
- Codegen draft has exactly 12 mappings; GarageLocation override is removed.
- Deterministic rule engine fixes: comments/strings masked, SEC typed/snake/camel names, all secrets redacted from evidence, SQL custom method names, SBT XML attributes, LOG-001 call-site and multiline handling, TX multiple commits, path-segment classification.
- Product shell: `/runs` restored; failed/loading pages; accepted/rejected row persistence; packet refresh; owner/status in packet; excluded-file filter; holdout lock; responsive overflow.
- Claims: C-002/C-014/C-016 URLs, C-018/C-036 PCF wording, C-032 rules present as `emitted: false`, reference limitations disclosed.

## Final local gates (evidence)

```text
pytest -q                                 197 passed (after final freeze)
pytest tests/test_false_positives.py ...  60 passed targeted
scripts/claims_lint.py                    claims-lint: OK
test_freeze_manifest.py                   every fixture/gold/reference/rulepack/ledger hash recomputes
preflight verify-audit R-DEMO-001         OK (8 events)
packet audit head == audit log head       true
Playwright golden path                    22 passed (accept/reject, evidence drawer, packet, evaluation)
```

## Final status

**Final focused gate: SHIP, 10/10.** Settings-page regression caught in the end-to-end re-run and fixed with a route-content test. SEC redaction is closed (adjacent comments and escaped quotes), evaluation labels match the computed values, and the frozen hashes reproduce. The residual limitations below remain disclosed.

## Residual limitations (disclosed, not hidden)

- Reference target is internally authored and AI-assisted; not human-independent.
- Demo metrics are in-sample on the development slice; holdout is pre-computed and naming-shift only.
- M3 audits excerpt support, not semantic entailment.
- M5 uses a fixed two-decoy top-8 allowance, not a learned ranking.
- M6 line-level matching is deferred; path-level matching is used in the demo tier.
- No human inter-annotator study; no reviewer-effort or real-estate generalisation claim.
- The Cloud API extension draft is local and non-deployable; it is not compiled or tenant-validated.
- Official Cloud Assurance was not run.
