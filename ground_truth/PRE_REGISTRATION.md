# PreFlight Evaluation Pre-Registration

**Status:** Draft for P1 freeze. The hashes and commit in `FROZEN.json` must be filled before any scored run.
**Date:** 7 November 2026
**Scope:** Demo-critical and thesis-complete tiers.
**Rule:** No holdout access, prompt tuning, rule tuning, or threshold changes after the freeze commit.

## 1. Research question

Can an evidence-first, deterministic pipeline produce a traceable feature inventory, a reviewable Cloud API extension draft, and explicit assumptions on a controlled Guidewire-style estate, with measurable gains over naive baselines?

**Hypothesis:** On a frozen synthetic benchmark, cross-artefact candidate assembly improves feature recall by ≥10 percentage points over PCF+grep discovery, and evidence-linked dispositions reduce silent omissions versus an identity mapper.

## 2. Fixtures

| Fixture | Role | Files | Features | Holdout? |
|---|---|---:|---:|---|
| `acme-pc-2026.10` | Main development | 1,500+ (thesis) / 600–800 (demo) | 12 / 8 | No |
| `demo-slice-300` | Live import demo | 300 | PA-VEH-01 complete | No |
| `northstar-pc-2026.10` | Naming-shift holdout | 300 / 150 | 6 / 4 | Yes |

The holdout is never imported into the demo, never used to author rules, and never used to tune thresholds. Pre-computed holdout aggregates may be displayed with a “not imported” label.

## 3. Baselines

| Baseline | Purpose | Expected comparison |
|---|---|---|
| Identity/name-match mapper | Tests whether reconstruction adds value beyond copying normalized names. | PreFlight should beat by ≥10pp disposition correctness. |
| All-unresolved mapper | Floor; proves coverage is not vacuous. | PreFlight must beat. |
| Grep-only findings scan | Tests whether masking/allowlists improve precision. | PreFlight should improve precision without losing recall. |
| PCF+grep discovery | Tests whether cross-artefact linking improves recall. | PreFlight should improve feature recall by ≥10pp. |
| Strong naive (normalized fuzzy names + curated regex + allowlists + PCF) | Realistic non-graph baseline. | PreFlight should beat on evidence precision and estimate-moving recall. |
| Always-answer assistant | Tests refusal/citation value. | PreFlight should improve refusal precision and citation correctness. |

## 3.1 Baseline × metric matrix (pre-registered margins)

| Metric | Identity mapper | All-unresolved | Grep-only | PCF+grep | Strong naive | PreFlight target |
|---|---|---|---|---|---|---|
| M1 feature recall | n/a | n/a | baseline | baseline | +10pp over PCF+grep | main ≥0.75 |
| M2 feature precision | n/a | n/a | baseline | baseline | +10pp over PCF+grep | ≥0.75 |
| M3 evidence precision | n/a | n/a | baseline | baseline | +10pp over strong naive | ≥0.90 |
| M4 disposition correctness | baseline | baseline | n/a | n/a | +10pp over identity | ≥0.75 |
| M5 estimate-moving recall | n/a | n/a | baseline | baseline | +10pp over strong naive | ≥0.75 |
| M6 finding F1 | n/a | n/a | baseline | baseline | +10pp over grep-only | ≥0.75 |

Margins are absolute percentage points and are frozen before the first scored run. If PreFlight does not beat a baseline by the margin, the claim is reported as not supported.

## 4. Headline metrics and thresholds

| ID | Metric | Denominator | Demo threshold | Thesis threshold |
|---|---|---|---|---|
| M1 | Feature recall | main 8 + holdout 4 (demo) / main 12 + holdout 6 (thesis), per fixture | main ≥0.75, holdout ≥0.60 | same |
| M2 | Feature precision | emitted candidates | ≥0.75 | ≥0.75 |
| M3 | Evidence-link precision | stratified 30-link audit sample | ≥0.90 point; Wilson lower ≥0.75 (28/30 minimum) | same |
| M4 | Disposition correctness | 12 demo / 16 thesis gold mappings (4 codegen, 1 long-type, 6 API properties, 1 typelist); split mapped vs correctly-non-mapped | ≥0.75 | ≥0.75 |
| M5 | Estimate-moving issue recall | 6 planted high-impact issues; top-8 ranked + precision guard | ≥0.75 recall; ≥0.75 top-8 precision (6 TP / 8) | same |
| M6 | Finding F1 | 8 rules demo / 10 thesis; ≥3 positives + ≥3 hard negatives per rule; macro P/R/F1 | precision ≥0.80, recall ≥0.70, F1 ≥0.75 | same |

Supporting: feature macro-F1, evidence-link recall, reference-target macro-F1 + confusion matrix, silent omission (gold scope), non-unresolved rate (mapped + correctly-non-mapped split), local schema conformance, assistant refusal/citation, 5k throughput.

### 4.1 M5 planted estimate-moving issues (six, enumerated)

1. `PersonalAutoRatingFactorConfiguration` exceeds the 24-character APD type limit.
2. `PersonalVehicle` entity has no `ModelYear`-aligned codegen override.
3. `Motorcycle_Ext` typelist value has no target enum disposition.
4. `GarageLocation_Ext` has no API schema disposition.
5. `PersonalVehicleRatingDBTest.gs` is DB-coupled and will be CI-brittle.
6. A hidden `com.guidewire.*` package reference appears in legacy Gosu.

Each issue has a gold evidence path and expected rule/mapping ID. M5 uses top-8 ranking: 6 true + 2 allowed false positives = 0.75 top-8 precision.

### 4.2 M6 finding gold set

Demo: 8 rules × 6 cases (3 positive, 3 hard negative) = 48 labelled findings. Thesis: 10 rules × 6 cases = 60. The κ sample is a 20-finding subset; the full 48/60 set is the scored corpus. Per-rule n and intervals are reported; per-rule recall thresholds are descriptive, not gating.

## 5. Matching rules

- Feature: same business capability; strict leaf match; synonyms adjudicated.
- Evidence: same claim + normalized path + span overlap ≥1 line or containing symbol.
- Mapping: source property + target property or explicit disposition; correctness adjudicated.
- Finding: rule ID + path + line overlap; per-rule TP/FP/FN.
- Comparison: property-level; target scope completeness flag.

## 6. Annotation and agreement

- Two annotators (AI or human; labelled) blind to `rules/` and tool output.
- Sample: 30 evidence links, 20 findings, 12 demo mappings (16 thesis).
- κ ≥ 0.60; adjudication log; if annotators are AI, report “AI-assisted concordance,” not human inter-annotator agreement.
- Annotation guide versioned and hashed.

## 7. Freeze

`FROZEN.json` records: fixture hashes, reference-target hash, annotation-guide hash, rule-pack hash, pre-registration hash, commit, author, date, change log. `test_freeze_manifest.py` verifies. `test_gt_import_boundary.py` asserts product code cannot import ground truth.

## 8. Reporting

Per-fixture and per-rule tables; raw counts; Wilson intervals for proportions; bootstrap CIs for F1/κ; confusion matrices; failures; limitations. No headline percentage with n<10 without raw counts and interval. No reviewer-effort claim. No “generalises to real estates” claim.
