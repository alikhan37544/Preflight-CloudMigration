# PreFlight Evaluation Pre-Registration

**Status:** Frozen. See `FROZEN.json` for hashes and commit; after freeze, no rules or thresholds change.
**Date:** 7 November 2026
**Scope:** Demo-critical and thesis-complete tiers.
**Rule:** No holdout access, prompt tuning, rule tuning, or threshold changes after the freeze commit.

## 1. Research question

Can an evidence-first, deterministic pipeline produce a traceable feature inventory, a reviewable Cloud API extension draft, and explicit assumptions on a controlled Guidewire-style estate, with measurable gains over naive baselines?

**Hypothesis:** On a frozen synthetic benchmark, cross-artefact candidate assembly improves feature recall by ≥10 percentage points over PCF+grep discovery, and evidence-linked dispositions reduce silent omissions versus an identity mapper.

## 2. Fixtures

| Fixture | Role | Files | Features | Holdout? |
|---|---|---:|---:|---|
| `acme-pc-2026.10` | Main development | 650 (demo) / 1,500+ (thesis) | 8 / 12 | No |
| `demo-slice-300` | Live import demo | 300 | PA-VEH-01 complete | No |
| `northstar-pc-2026.10` | Naming-shift holdout | 150 (demo) / 300 (thesis) | 4 / 6 | Yes |

The holdout is never imported into the demo, never used to author rules, and never used to tune thresholds. Its aggregate is **pre-computed once before freeze** in `ground_truth/holdout_metrics.json`; the demo pipeline does not scan it. The demo slice is an in-sample subset of the development fixture and is labelled as such. The reference target is **internally authored, AI-assisted, and not independent**; this is reported as a limitation.

## 3. Baselines

| Baseline | Purpose | Expected comparison |
|---|---|---|
| Identity/name-match mapper | Tests whether reconstruction adds value beyond copying normalized names. | PreFlight should beat by ≥10pp disposition correctness. |
| All-unresolved mapper | Floor; proves coverage is not vacuous. | PreFlight must beat. |
| Grep-only findings scan | Tests whether masking/allowlists improve precision. | PreFlight should improve precision without losing recall. |
| PCF+grep discovery | Tests whether cross-artefact linking improves recall. | PreFlight should improve feature recall by ≥10pp. |
| Normalized-name mapper (demo approximation of a strong naive baseline) | Tests whether reconstruction beats copying normalized names. | PreFlight should beat on disposition correctness. |
| Always-answer assistant | Tests refusal/citation value. | PreFlight should improve refusal precision and citation correctness. |

## 3.1 Baseline × metric matrix (pre-registered margins)

| Metric | Identity mapper | All-unresolved | Grep-only | PCF+grep | Strong naive | PreFlight target |
|---|---|---|---|---|---|---|
| M1 feature recall | n/a | n/a | baseline | baseline | +10pp over PCF+grep | main ≥0.75 |
| M2 feature precision | n/a | n/a | descriptive | descriptive | descriptive | ≥0.75 |
| M3 evidence precision | n/a | n/a | descriptive | descriptive | descriptive | ≥0.90 |
| M4 disposition correctness | baseline | baseline | n/a | n/a | +10pp over identity | ≥0.75 |
| M5 estimate-moving recall | n/a | n/a | descriptive | descriptive | descriptive | ≥0.75 |
| M6 finding F1 | n/a | n/a | baseline | baseline | +10pp over grep-only | ≥0.75 |

Frozen margins are reported for M1, M4, and M6 where an independent or naive comparator exists. M2, M3, and M5 baselines are descriptive because no comparable independent scanner was built in the demo tier. If PreFlight does not beat a frozen baseline by the margin, the claim is reported as not supported.

## 4. Headline metrics and thresholds

| ID | Metric | Denominator | Demo threshold | Thesis threshold |
|---|---|---|---|---|
| M1 | Feature recall | main 8 (demo) / 12 (thesis); holdout reported separately from the pre-computed aggregate | main ≥0.75, holdout ≥0.60 | same |
| M2 | Feature precision | emitted candidates | ≥0.75 | ≥0.75 |
| M3 | Evidence-link support precision | stratified 30-link audit sample; path resolves and excerpt appears at the source | ≥0.90 point; Wilson lower ≥0.75 (28/30 minimum) | same |
| M4 | Disposition correctness | 12 demo / 16 thesis gold mappings; source, target, and disposition must all match; extra mappings reduce the score | ≥0.75 | ≥0.75 |
| M5 | Estimate-moving issue recall | 6 planted high-impact issues; top-8 allowance (6 TP + 2 fixed decoys) | ≥0.75 recall; ≥0.75 top-8 allowance | same |
| M6 | Finding micro-F1 | 8 rules demo / 10 thesis; 3 positives + 3 hard negatives per rule; per-rule macro-F1 reported as supporting | precision ≥0.80, recall ≥0.70, micro-F1 ≥0.75 | same |

Supporting: feature macro-F1, evidence-link recall, reference-target macro-F1 + confusion matrix, silent omission (gold scope), non-unresolved rate (mapped + correctly-non-mapped split), local schema conformance, assistant refusal/citation, 5k throughput.

### 4.1 M5 planted estimate-moving issues (six, enumerated)

1. `PersonalAutoRatingFactorConfiguration` exceeds the 24-character APD type limit.
2. `PersonalVehicle` entity has no `ModelYear`-aligned codegen override.
3. `Motorcycle_Ext` typelist value has no target enum disposition.
4. `GarageLocation_Ext` has no API schema disposition.
5. `PersonalVehicleRatingDBTest.gs` is DB-coupled and will be CI-brittle.
6. A hidden `com.guidewire.*` package reference appears in legacy Gosu.

Each issue is enumerated in `ground_truth/estimate_moving_issues.json` with a signal type and expected rule/mapping ID. M5 uses top-8 ranking: 6 true + 2 allowed false positives = 0.75 top-8 precision, reported as `M5-TOP8`.

### 4.2 M6 finding gold set

Demo: 8 rules × 6 cases (3 positive, 3 hard negative) = 48 labelled findings. Thesis: 10 rules × 6 cases = 60. The κ sample is a 20-finding subset; the full 48/60 set is the scored corpus. Per-rule n and intervals are reported; per-rule recall thresholds are descriptive, not gating.

## 5. Matching rules

- Feature: same business capability **and** at least one gold anchor path present in the candidate evidence.
- Evidence: path resolves, locator is in range, and the excerpt appears at the source after whitespace normalization. This is a support audit, not semantic entailment.
- Mapping: source property + target property + disposition must all match; extra mappings are penalised.
- Finding: rule ID + path overlap; line-level matching is deferred to the thesis tier.
- Comparison: property-level; target scope completeness flag.

## 6. Annotation and agreement

- Two AI passes (labelled). This is **AI-assisted concordance**, not human inter-annotator agreement.
- Sample: 30 evidence links, 20 findings, 12 demo mappings (16 thesis).
- κ ≥ 0.60; adjudication log; if annotators are AI, report “AI-assisted concordance,” not human inter-annotator agreement.
- Annotation guide and concordance record versioned and hashed (`ANNOTATION_GUIDE.md`, `annotation_concordance.json`).

## 7. Freeze

`FROZEN.json` records: fixture hashes, reference-target hash, annotation-guide and concordance hashes, rule-pack hash, pre-registration hash, commit, author, date, change log. `test_freeze_manifest.py` recomputes and compares every hash. `test_gt_import_boundary.py` asserts product code cannot import ground truth.

## 8. Reporting

Per-fixture and per-rule tables; raw counts; Wilson intervals for proportions; per-rule macro-F1; confusion matrices; known limitations. F1 bootstrap intervals are proposed for the thesis tier. No headline percentage with n<10 without raw counts and interval. No reviewer-effort claim. No “generalises to real estates” claim.
