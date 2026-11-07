# PreFlight — Build Contract v5 (final gate candidate)

**Status:** Fifth revision. Supersedes v4. Adds the restored acceptance suite, tier matrix, PA-VEH-01 slice, discovery/reconstruction/assistant mechanics, API routes, target file skeletons, and demo choreography. Build starts only after the final gate in §22 records all categories ≥8 and no major gaps.
**Date:** 7 November 2026
**Repo:** `/home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration`
**Companion files:** `docs/claims-ledger.json` (canonical), `docs/claims-ledger.md` (generated), `docs/target-format.md`, `docs/security.md`, `ground_truth/PRE_REGISTRATION.md`, `ground_truth/FROZEN.json`, `ground_truth/pa_veh_01_edges.json`.

---

## 0. v4 → v5 corrections

| # | v4 issue | v5 resolution |
|---|---|---|
| 1 | Mixed Cloud Retrofit flows | Choose **Cloud Retrofit without APD App**. Source is pre-Retrofit. Files used: `pa_codegen_config_ext-1.0.yaml` + `template_gen_config.xml`. `template_gen_config.xml` is read-only input; the draft is codegen config + `_ext` schema/mapping/updater + product access file. No `template_gen_config.pa.yaml`, no APD App-only `schemaPropertyName` path. |
| 2 | Source/target artefacts mixed | Source inventory contains only pre-Retrofit artefacts (legacy product XML, extracted template, PCF, entity/typelist, Gosu, tests, `template_gen_config.xml`). Target table contains `_ext` files, codegen config, product access file. |
| 3 | Entity/template layer conflation | Three layers are explicit: installed entity `PersonalVehicle.ModelYear`; extracted APD template `PAVehicle.Year`; codegen mapping `PAVehicle.fields.Year.nameOverride: ModelYear`. PCF binds to installed entity `ModelYear`. |
| 4 | `.ttx` wrong directory | Typelist extension is `config/extensions/typelist/VehicleType.ttx`. |
| 5 | Typelist widget wrong | PCF uses `TypeKeyInput` for `VehicleType`, not `RangeInput`. |
| 6 | Impact 7.5 → 3–5 incoherent | Formula computes 7.5; range is **7–9 engineer-days** (≈20% review buffer). No cap to 3–5. Label heuristic. |
| 7 | Claims ledger orphan rules/status drift | Add `PRODUCT-CLAIM`; normalize statuses; add rows for target paths and every rule; downgrade `PF-GW-LOG-001/002`, `PF-GW-GUNIT-001` to `heuristic` (or add a verified source); add `hardening-guidance` family. |
| 8 | “Six metrics” vs ten | Six headline metrics in §7.1; all others are supporting metrics in §7.2. |
| 9 | Tier counts conflict | Demo-critical and thesis-complete have separate fixture/metric/rule counts in §9. Demo uses only measured demo-tier numbers; 5k is thesis-only. |
| 10 | Six-screen IA ambiguity | **Six routes, no drawer-only Manifest**: Workbench, Reconstruction, Findings, Evaluation, Packet, Manifest. Manifest is a full page; Workbench links to it. |
| 11 | Data contracts were names | Full field lists + enums + schema versions in §5. |
| 12 | Job/API contract missing | State machine, progress units, cancellation, atomic writes, API routes in §4.4. |
| 13 | Baselines weak | Add strong naive baseline (normalized fuzzy matching + curated regex with allowlists + PCF+grep discovery); baseline-metric matrix; pre-registered margins +10pp. |
| 14 | Independence asserted | Two independent annotators (AI or human; labelled), blind to `rules/`, 30-link/20-finding sample, κ≥0.6, adjudication log; `PRE_REGISTRATION.md`; frozen manifest. If no humans, call it “AI-assisted concordance,” not inter-annotator agreement. |
| 15 | Demo/holdout collision | Live demo uses `demo-slice-300`, carved from main fixture and feature-complete for PA-VEH-01; holdout `northstar` is never imported into the demo run or used for tuning; its aggregate may be displayed with a “not imported” label. |
| 16 | Demo findings lead generic | Cold open is cross-artefact spine + 24-char/PA long type + Cloud API draft; findings are a 20-second trust signal; Sonar/Cloud Assurance ownership is stated explicitly. |
| 17 | Delivery math | Person-days and calendar days explicit; demo-critical 20 person-days / 10 calendar days; thesis-complete 32 person-days / 16 calendar days, including buffer. |
| 18 | Packet under-specified | Six-page outline in §6.3; A16 checks each section, hashes, disclaimers, no secrets. |
| 19 | Assistant metric missing | 20-question assistant set: answerable/unanswerable, citation correctness, refusal precision/recall, no-invented-evidence rate. |
| 20 | “price/sign” overclaim | Use “review, challenge, approve”; “planning heuristic, not a quote.” |

---

## 1. Scenario contract (Cloud Retrofit without APD App)

**Estate:** a non-APD-native Personal Auto product installed in PolicyCenter. The team wants LOB-specific Cloud API endpoints before an APD conversion or SI engagement. They do **not** have APD App. The documented process is Cloud Retrofit without APD App (Guidewire notes it is not the recommended process; APD App is recommended when available).

**Why this path:** it is the only Cloud Retrofit path reproducible without APD App or a tenant, and it exercises the documented `nameOverride` mechanism. The product labels itself “non-recommended-path prototype; APD App path is future work.”

**Pipeline:**

```text
Pre-Retrofit source
  → extract product template
  → visualize/validate in PolicyCenter (not executed here)
  → codegen config + template_gen_config.xml
  → generate endpoints (not executed here)
  → _gen files (not edited) + _ext files (extension)
  → PreFlight: evidence inventory + proposed _ext/codegen draft + review packet
```

The prototype stops before generation/compile. It never claims endpoint generation or a tenant result.

---

## 2. Layer table (source semantics)

| Layer | Artefact | Field | Meaning |
|---|---|---|---|
| Installed entity | `config/metadata/entity/PersonalVehicle.eti` | `ModelYear` | Real PolicyCenter entity field. |
| Installed entity extension | `config/extensions/entity/PersonalVehicle.etx` | `GarageLocation_Ext` | Customer field. |
| Extracted APD template | `product/template/PersonalAutoTemplate.xml` | `PAVehicle.Year` | APD/template type/field extracted from the installed product. |
| Codegen config (draft) | `pa_codegen_config_ext-1.0.yaml` | `PAVehicle.nameOverride: PersonalVehicle`; `PAVehicle.fields.Year.nameOverride: ModelYear` | Maps APD/template names to installed names. Verified docs. |
| Template config (read-only input) | `template_gen_config.xml` | APD model structure | Non-APD path config. Not drafted. |
| PCF | `config/web/pcf/policy/PAVehicleDV.pcf` | `ModelYear`, `VehicleType`, `GarageLocation_Ext` | UI binds to installed entity fields. |
| API extension draft | `policyperiod_pa_ext-1.0.schema.json` | `modelYear`, `vehicleType`, `garageLocation` | Proposed API properties (conventions require review). |

This resolves the earlier “Year vs ModelYear” contradiction: `Year` is the APD/template layer; `ModelYear` is the installed/PCF layer; `modelYear` is the API layer.

---

## 3. Source vs target inventory

### 3.1 Source (pre-Retrofit; read-only)

```text
fixtures/acme-pc-2026.10/
  config/metadata/entity/PersonalVehicle.eti
  config/extensions/entity/PersonalVehicle.etx
  config/metadata/typelist/VehicleType.tti
  config/extensions/typelist/VehicleType.ttx
  config/web/pcf/policy/PAVehicleDV.pcf
  config/resources/productmodel/PersonalAuto.xml
  product/template/PersonalAutoTemplate.xml
  config/apd/model/generate/json/template_gen_config.xml
  gsrc/acme/validation/PersonalVehicleValidation.gs
  gtest/acme/PersonalVehicleValidationTest.gs
  gtest/acme/PersonalVehicleRatingDBTest.gs
  ... plus 1,500+ generated/noise files, second LOB, plugin, corrupt XML, binary
```

### 3.2 Target draft (written only to `data/runs/<id>/draft/`)

```text
config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json
config/integration/mappings/ext/policyperiod/v1/policyperiod_pa_ext-1.0.mapping.json
config/integration/updaters/ext/policyperiod/v1/policyperiod_pa_ext-1.0.updater.json
config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml
config/integration/apis/installedlobs/pa_ext-1.0.yaml
```

Out of scope: swagger extension (`config/integration/apis/ext/policyperiod/v1/...swagger.json`), Gosu resource (`gsrc/gw/rest/ext/...`), `_gen` files, deployment.

### 3.3 Mapping rules

| Rule | Source | Target | Provenance |
|---|---|---|---|
| R-CG-01 | `PAVehicle` | `nameOverride: PersonalVehicle` | guidewire-doc (codegen config syntax) |
| R-CG-02 | `PAVehicle.fields.Year` | `nameOverride: ModelYear` | guidewire-doc (without-APD-App scope) |
| R-CG-03 | `PADriver` | `nameOverride: VehicleDriver` | guidewire-doc |
| R-CG-04 | `PALine` | `nameOverride: PersonalAutoLine` | guidewire-doc |
| R-GW-24-01 | APD type name >24 chars | add `nameOverride` for truncated type | guidewire-doc (correcting compile errors) |
| R-API-01 | installed entity `PersonalVehicle.VehicleType` (PCF `TypeKeyInput@VehicleType` is evidence) | schema `vehicleType` | preflight-convention |
| R-API-02 | `GarageLocation_Ext` | schema `garageLocation` | preflight-convention |
| R-API-03 | PCF `ModelYear` | schema `modelYear` | preflight-convention |
| R-API-04 | `PersonalVehicle.Make` | schema `make` | preflight-convention |
| R-API-05 | `PersonalVehicle.VIN` | schema `vin` | preflight-convention |
| R-API-06 | `PersonalVehicle.Usage` | schema `usage` | preflight-convention |
| R-TYP-01 | `VehicleType.ttx` `Motorcycle_Ext` | schema enum option `motorcycle` | preflight-convention |
| R-UNR-01 | territory requirement | `gap` (no source) | reviewer-decision |
| R-UNS-01 | rating inputs | `unsupported` | reviewer-decision |
| R-TEST-01 | DB-coupled test | advisory finding | preflight-convention |
| R-DOC-01 | Gosu validation | evidence only; no target mapping | preflight-convention |

No APD-App-only `PersonalVehicle → Vehicle` normalization is claimed. It is documented as a separate APD-App pattern and is out of scope.

---

## 4. Architecture and contracts

### 4.1 Stack

Python 3.12, FastAPI, Jinja2, vanilla JS/CSS, `lxml`, `ruamel.yaml`, Pydantic v2, JSON run store + SQLite index, pytest, Playwright. No React/Streamlit/ANTLR4/graph DB/vector DB.

### 4.2 Pipeline

`Snapshot → Intake → Parse → Discover → Review → Reconstruct → Compare → Evaluate → Packet`.

### 4.3 Job state machine

```text
queued → running(intake|parse|discover|review|reconstruct|compare|evaluate|packet) → succeeded
                                                                                 → failed
                                                                                 → cancelled
```

- Progress units: files processed / total files; stage weights: intake 10, parse 38, discover 25, review 9, reconstruct 10, compare 3, evaluate 3, packet 2 = 100.
- Cancellation checked between files and stages; temp extraction deleted on cancel/failure.
- Atomic writes: write `*.tmp`, fsync, rename; no partial JSON exposed.
- Single-worker constraint (`max_workers=1`) to avoid concurrent runs; re-run returns existing run unless `force=true`.
- `POST /api/runs` (project_id, force), `GET /api/runs/{id}/status`, `POST /api/runs/{id}/cancel`, `GET /api/runs`, `GET /api/runs/{id}/manifest?page&size`, `GET /api/runs/{id}/{artifact}`, `POST /api/runs/{id}/decisions`, `POST /api/runs/{id}/delete`.
- Error responses: `{error: {code, message, detail, retryable}}`.

### 4.4 Evidence locator

`Locator = {kind: xpath|json_pointer|yaml_path|line, value, line?, column?, excerpt_sha}`. XML uses `sourceline` + XPath; JSON uses JSON Pointer + excerpt; YAML uses `ruamel.yaml` line/column. UI says “file + line/pointer.”

### 4.5 Security

- 127.0.0.1 bind; Host/Origin allowlist; CSRF synchronizer token per session; SameSite=Strict; POST-only mutations; token rotation on login/session change.
- Jinja autoescape; no `|safe`; JS `textContent`; CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`.
- Zip limits: 20k files, 500 MB compressed, 2 GB uncompressed, ratio 100:1; reject encrypted entries, symlinks, absolute paths, `..`, NUL, drive letters; random temp; no execution.
- XML: `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`.
- YAML: `safe_load`; no tags.
- Secrets redacted at capture; packet/logs tested for raw secrets.
- Hash-chained audit: `event_id`, `run_id`, `seq`, `ts`, `actor`, `action`, `object_type`, `object_id`, `before_hash`, `after_hash`, `prev_hash`, `hash`; canonical JSON; `preflight verify-audit`.
- Retention: `POST /api/runs/{id}/delete` removes run + draft + temp; no telemetry; optional local LLM off.

### 4.6 API and UI contracts

- Workbench URL state: `?run=...&feature=...&evidence=...`; feature list + spine + evidence drawer + assistant + gap panel.
- Manifest page: 100 rows/page, filters, hash copy, unsupported banner.
- Reconstruction tabs: mappings, draft/diff, assumptions, comparison.
- Findings page: table + detail drawer.
- Evaluation page: six headline metrics + supporting table.
- Packet page: six sections + export.
- Every page has empty/loading/partial/error/success states.

---

## 5. Data contracts (required fields)

| Record | Fields |
|---|---|
| `Project` | `project_id`, `name`, `source_release`, `target_context`, `created_at` |
| `Snapshot` | `snapshot_id`, `project_id`, `root`, `sha256`, `file_count`, `size_bytes`, `created_at`, `synthetic` |
| `Run` | `run_id`, `project_id`, `snapshot_id`, `status`, `stage`, `progress`, `release_context`, `parser_version`, `rulepack_version`, `created_at`, `finished_at`, `error` |
| `Artifact` | `path`, `sha256`, `size`, `kind`, `parser`, `status`, `warnings`, `line_count` |
| `Evidence` | `evidence_id`, `path`, `locator`, `excerpt_sha`, `excerpt`, `method`, `confidence`, `redacted` |
| `Feature` | `feature_id`, `name`, `lob`, `description`, `evidence_ids`, `dependencies`, `confidence`, `open_questions` |
| `Mapping` | `mapping_id`, `source_ref`, `source_name`, `source_layer`, `target_path`, `target_name`, `disposition`, `rule_id`, `provenance`, `confidence`, `rationale`, `reviewer_state` |
| `Change` | `change_id`, `target_path`, `diff`, `mapping_id`, `approval_state`, `reviewer`, `reviewed_at`, `edited_value`, `previous_value`, `edit_reason`, `edit_history` |
| `Assumption` | `assumption_id`, `statement`, `impact`, `impact_range_days`, `impact_basis`, `impact_confidence`, `impact_caveat`, `status`, `owner`, `question_to_ask`, `related_mapping_id`, `gap_id` |
| `Gap` | `gap_id`, `kind` (`missing_source|missing_target|ambiguous_reference|unsupported`), `subject`, `evidence_sought`, `impact`, `owner`, `status`, `assumption_id` |
| `Finding` | `finding_id`, `rule_id`, `rule_version`, `title`, `severity`, `confidence`, `claim_strength`, `standard_family`, `standard_id`, `standard_title`, `standard_url`, `access`, `evidence_ids`, `message`, `remediation`, `decision` |
| `Decision` | `decision_id`, `object_type`, `object_id`, `action` (`accept|reject|edit|defer`), `actor`, `reason`, `before_hash`, `after_hash`, `created_at` |
| `ComparisonRow` | `row_id`, `source_ref`, `target_ref`, `class` (`preserved|changed|missing|added|unresolved`), `evidence_ids`, `rationale`, `confidence`, `target_scope_complete` |
| `Rule` | `rule_id`, `version`, `title`, `severity`, `claim_strength`, `standard_family`, `standard_id`, `standard_url`, `detection`, `allowlist`, `positive_fixtures`, `negative_fixtures` |
| `AuditEvent` | `event_id`, `run_id`, `seq`, `ts`, `actor`, `action`, `object_type`, `object_id`, `before_hash`, `after_hash`, `prev_hash`, `hash` |
| `Packet` | `packet_id`, `run_id`, `pages`[6], `hashes`, `audit_head`, `disclaimer`, `created_at` |
| `Metric` | `metric_id`, `label`, `value`, `numerator`, `denominator`, `unit`, `caveat`, `fixture_id`, `tier`, `primary` |

Canonical taxonomies:
- `disposition`: `mapped_exact`, `mapped_transformed`, `intentionally_dropped`, `not_applicable`, `unresolved_gap`, `unsupported`.
- `gap_kind`: as above.
- `comparison_class`: as above.
- `claim_strength`: `verified-id`, `verified-policy`, `verified-doc`, `secondary`, `heuristic`.
- `standard_family`: `cloud-standard`, `gosu-secure-coding`, `hardening-guidance`, `internal-guidance`, `none`.

---

## 6. Product IA and packet

### 6.1 Six routes

1. `/` Workbench — feature list, spine, evidence drawer, assistant, gaps.
2. `/reconstruction` — mappings, draft/diff, assumptions, comparison.
3. `/findings` — advisory findings + detail.
4. `/evaluation` — six metrics + supporting.
5. `/packet` — six-page packet + export + audit.
6. `/manifest` — full manifest, pagination, unsupported.

Secondary: `/about`, `/settings`, `/runs`.

### 6.2 Workbench layout

- Top: snapshot/run header, synthetic badge, coverage banner.
- Left: feature list (search, LOB, confidence, gaps).
- Center: **feature spine** (left-to-right columns: PCF → entity → typelist → product/template → API draft → tests). Highlight selected feature path; dim others; edge labels `declares/references/configures/tested_by`; count badges.
- Right: evidence drawer (path, line/pointer, snippet, confidence) and Grounded Assistant.
- Bottom: gaps/assumptions summary.

Table fallback for spine; keyboard navigation; no physics.

### 6.3 Packet pages

1. Cover: estate, snapshot hash, date, release context, synthetic badge.
2. Executive summary: posture, top estimate-moving items, decisions required.
3. Coverage & confidence: files parsed, unsupported, parser warnings, confidence ceiling.
4. Assumption register: statement, impact range, owner, question, evidence gap.
5. Findings: migration-specific first, claim strength, “official Cloud Assurance: not run,” handoff.
6. Evidence & audit appendix: evidence index, unsupported list, review log head, disclaimers.

---

## 7. Metric register

### 7.1 Six headline metrics

| ID | Metric | Definition | Denominator | Threshold |
|---|---|---|---|---|
| M1 | Feature recall | gold features found / gold features | demo: main 8 + holdout 4; thesis: main 12 + holdout 6; per fixture | main ≥0.75, holdout ≥0.60 |
| M2 | Feature precision | correct candidates / emitted candidates | emitted | ≥0.75 |
| M3 | Evidence-link precision | audited links resolving and supporting / audited links | stratified 30-link sample; 28/30 minimum for Wilson lower ≥0.75 | point ≥0.90, Wilson lower ≥0.75 |
| M4 | Disposition correctness | correct mapped + correct non-mapped / gold mappings (12 mapping rules: 4 codegen, 1 long-type, 6 API properties, 1 typelist) | demo: 12; thesis: 16 | ≥0.75 |
| M5 | Estimate-moving issue recall | planted high-impact issues surfaced with evidence / 6 planted; top-8 precision guard | 6 planted issues; top-8 ranked list | recall ≥0.75; top-8 precision ≥0.75 (6 TP / 8 = 0.75) |
| M6 | Finding F1 | per-rule precision/recall, macro-F1 | demo: 8 rules; thesis: 10 rules; ≥3 positive + ≥3 hard negative per rule | macro precision ≥0.80, recall ≥0.70, F1 ≥0.75 |

### 7.2 Supporting metrics

Feature macro-F1, evidence-link recall, reference-target macro-F1 + confusion matrix, silent omission (gold scope), non-unresolved rate (mapped + correctly-non-mapped split), local schema conformance, assistant refusal/citation metrics, 5k throughput (time/RSS), per-class table.

### 7.3 Measurement rules

- Pre-register thresholds, baselines, margins (+10pp), matching rules, interval methods in `ground_truth/PRE_REGISTRATION.md` before holdout.
- Wilson intervals for proportions; bootstrap CIs for F1/κ; raw counts always.
- Feature match: same business capability, strict leaf match; evidence match: path + span overlap + symbol.
- Finding match: rule ID + path + line overlap; report per-rule n.
- No headline percentage with n<10 without raw counts and interval.
- No reviewer-effort claim.

### 7.4 Baselines

| Baseline | Tests |
|---|---|
| Identity/name-match mapper | Does reconstruction beat copying names? |
| All-unresolved mapper | Proves disposition coverage is not vacuous |
| Grep-only findings scan | Does masking/allowlisting improve precision? |
| PCF+grep discovery | Does cross-artefact linking improve recall? |
| Strong naive (normalized fuzzy names + curated regex + allowlists + PCF) | Realistic non-graph baseline |
| Always-answer assistant | Shows refusal/citation value |

Baseline-metric matrix in `PRE_REGISTRATION.md`; margins pre-registered.

### 7.5 Independence and freeze

- Two annotators (AI or human; labelled) blind to `rules/` and tool output; annotation guide; 30 links + 20 findings; κ≥0.60; adjudication log.
- The reference target is authored by the annotator who did not author the mapping rules, blind to the tool’s draft, and sealed (hash + commit) before the first scored run. If the same person/agent authors both, label the result “internally authored, not independent.”
- If annotators are AI, report “AI-assisted concordance,” not human inter-annotator agreement.
- `FROZEN.json`: fixture hash, reference-target hash, annotation-guide hash, author, date, commit, change log.
- Rule leakage test: no fixture-specific literals in `rules/`.
- GT import boundary: product code cannot import `ground_truth/`.
- Holdout never imported into the demo run or used for tuning; `demo-slice-300` is carved from the main fixture. Pre-computed holdout aggregates may be displayed with a “not imported” label.

---

## 8. Review rules

| Rule | Check | Claim strength | Standard family | Severity |
|---|---|---|---|---|
| PF-GW-SQL-001 | Direct JDBC/SQL | verified-id `IS-TLS-1238` | cloud-standard | error |
| PF-GW-SEC-001 | Hard-coded secret | verified-id `SEC00-G` | gosu-secure-coding | error |
| PF-GW-PKG-001 | Hidden/internal package | verified-id `IS-TLS-1191` | cloud-standard | error |
| PF-GW-EXC-001 | Swallowed exception | verified-id `ERR00-G` | gosu-secure-coding | warning |
| PF-GW-TX-001 | Commit inside `runWithNewBundle` | secondary | internal-guidance | warning |
| PF-GW-SRV-001 | Custom servlet | verified-policy | hardening-guidance | warning |
| PF-GW-LOG-001 | PII/credential in logs | heuristic | none | warning |
| PF-GW-LOG-002 | `print`/`printStackTrace` | heuristic | none | warning |
| PF-GW-GUNIT-001 | DB access in pure unit test | heuristic | none | warning |
| PF-GW-NAM-001 | APD type name >24 chars | verified-doc | none | error (documented compile-error cause) |

`PF-GW-SBT-001` (SBT readiness flag) is a separate advisory check backed by C-005, not counted in the 10 review rules.

Rule contract: detection pattern/parser query, masking rules, allowlist/negative cases, severity, claim strength, standard family, source URL, positive/hard-negative fixtures, version. Every rule has a claims-ledger row or is `heuristic`.

---

## 9. Delivery

### 9.1 Units

- 1 person-day = 6 focused hours.
- Demo-critical: 2 people × 10 calendar days × 6h = 120h ≈ 20 person-days.
- Thesis-complete: 2 people × 16 calendar days × 6h = 192h ≈ 32 person-days.

### 9.2 Demo-critical tier (10 calendar days)

| Phase | Person-days | Output |
|---|---:|---|
| P0 Plan/claims freeze | 1 | v5 gate, claims ledger, target format |
| P1 Contracts + seed fixture | 4 | tests, 300-file demo slice, 150 holdout, GT, reference target |
| P2 Core pipeline | 5 | intake, parsers, discovery, reconstruction |
| P3 Review/compare/eval | 2 | findings, comparison, all six metrics (M1–M6), baseline |
| P4 UI | 4 | Workbench, Reconstruction, Findings, Evaluation, Packet, Manifest |
| P5 Hardening | 1 | security, offline, claims linter |
| P6 Verification | 1 | critic fixes |
| P7 Demo | 1 | screenshots, rehearsal |
| Buffer | 1 | 5% |
| **Total** | **20** | **10 calendar days for 2 people** |

Demo-critical scope: 600–800 files, 8 features, 8 rules, 12 mappings, all six headline metrics (M1–M6 with demo-tier denominators), no 5k, 10-question assistant included.

### 9.3 Thesis-complete tier (16 calendar days)

| Phase | Person-days | Output |
|---|---:|---|
| P0 | 1 | gate/claims |
| P1 | 6 | 1,500 files, 300 holdout, GT, reference target |
| P2 | 7 | full pipeline |
| P3 | 5 | 10 rules, all six metrics (M1–M6), baselines, assistant |
| P4 | 6 | six screens, packet, spine |
| P5 | 2 | security, 5k, offline |
| P6 | 2 | verification |
| P7 | 1 | demo |
| Buffer | 2 | 6.25% of 32 total person-days |
| **Total** | **32** | **16 calendar days for 2 people** |

### 9.4 Cut order

Assistant → 5k → second LOB feature → extra metrics → packet PDF. Never cut: evidence, hashes, unsupported reporting, pending approvals, assumptions, denominators, disclaimers.

---

## 10. Demo (5 minutes; thesis numbers only if measured)

| Time | Screen | Action | Message |
|---|---|---|---|
| 0:00 | Workbench | Cold open on PA long type `PersonalAutoRatingFactorConfiguration` (37 chars) and `Motorcycle_Ext` spine | “At week 5, one long type name truncates to 24 characters in APD and breaks the build. This pattern touches 11 references, four artefact types, and two tests. We find it before kickoff.” |
| 0:25 | Manifest | Live import `demo-slice-300`; show run ID, hash, progress, unsupported | “Read-only, hashed, offline. Unsupported files listed, not hidden.” |
| 0:55 | Workbench | Spine reveal; click `Motorcycle_Ext`; toggle gaps | “PCF → entity → typelist → template → API draft → tests. File + line/pointer. The territory requirement has no source — that becomes an assumption.” |
| 1:45 | Reconstruction | Accept `PAVehicle → PersonalVehicle` and `Year → ModelYear`; reject the territory assumption; show the **long-type** 7–9 day range | “A decision queue, not a JSON dump. The long type is a 7–9 engineer-day planning range. Rejection creates a territory assumption with owner, impact, and the question to ask. Source untouched.” |
| 2:45 | Findings | Brief: 24-char, hidden package, DB-coupled test; show claim strength; explicit “Sonar/Cloud Assurance own generic linting” | “Migration-specific checks first. Generic linting is not our moat. Official Cloud Assurance: not run.” |
| 3:15 | Assistant | Ask “Does this estate use territory rating?” | “Cannot determine — no rating artefacts. Searched scopes: product model, rating Gosu, rate tables. These files would answer it.” |
| 3:35 | Packet | Export; show assumption register, audit head, “planning heuristic, not a quote” | “The output is a scope you can review, challenge, and approve.” |
| 4:15 | Evaluation | Show measured demo-tier M1–M6, baselines, per-rule table, holdout aggregate labelled “not imported” | “Raw counts, intervals, failures. Triage, not an exhaustive audit.” |
| 4:50 | Close | Tagline | “Every claim has evidence; every unknown has a name; every change waits for a human.” |

Synthetic badge from second zero. No fake 201, official pass, auto-pay, 50 states, live tenant. Demo uses only measured demo-tier numbers; thesis-only 5k is labelled “not run in this demo.”

---

## 11. Claims/legal

- Footer/About: independent research prototype; not affiliated/endorsed/certified by Guidewire; Guidewire, InsuranceSuite, PolicyCenter, ClaimCenter, BillingCenter, Gosu, APD, Jutro, Integration Gateway, Cloud Assurance, Developer Assistants, Guidewire Cloud Platform, and InsuranceNow are trademarks or registered trademarks of Guidewire Software, Inc. in the United States and/or other countries; all other trademarks belong to their owners; Source Sans 3 under SIL OFL; synthetic fixture; no customer data or confidential Guidewire information; pattern-based heuristics, not official Cloud Standards checks; not legal/security/compliance advice.
- Use “review, challenge, approve,” not “price/sign.”
- Prohibited-phrase linter: “Guidewire-certified”, “Cloud Assurance pass”, “APD converter”, “production-ready”, “100% detection”, “replaces Cloud Assurance”, “6–8 weeks → 5 minutes”, “first AI migration tool”, “six-figure”, “priced assumption register”, unverified IDs.
- AI disclosure: planning/reviews used AI; product LLM off by default; no customer code leaves the machine.

---

## 12. Impact range

Formula: `references × 0.5 + artefact_types × 0.25 + tests × 0.5`; for 11 references, 4 types, 2 tests = 7.5; display **7–9 engineer-days** (≈20% review buffer); `impact_confidence` and `impact_caveat`: “Heuristic planning range; not a quote or measured productivity claim.” UI/packet show inputs.

---

## 13. Residual risks

| Risk | Mitigation |
|---|---|
| Non-recommended Cloud Retrofit path | Label explicitly; APD App path future work; no deployment claim. |
| Synthetic fixture realism | Layer table, fidelity appendix, two LOBs, generated/plugin/corrupt/binary, holdout, scale. |
| Target format | Exact paths, `docs/target-format.md`, conformance tests, `_gen` prohibition. |
| Evaluation independence | Two blind annotators (labelled AI/human), κ, pre-registration, freeze manifest. |
| Demo risk | Pre-seeded + 300-file live import + progress + backup. |
| Human Guidewire sign-off | AI domain review + user review; external human sign-off labelled pending before public submission. |

---

## 14. Tier matrix and demo subset

| Dimension | Demo-critical (10 days) | Thesis-complete (16 days) |
|---|---|---|
| Files | 600–800 main + 150 holdout + `demo-slice-300` | 1,500 main + 300 holdout + `demo-slice-300` |
| Features | 8 main + 4 holdout | 12 main + 6 holdout |
| Review rules | 8 (SQL, SEC, PKG, EXC, TX, SRV, NAM, GUNIT heuristic) | 10 (adds LOG-001, LOG-002) |
| Mappings | 12 | 16 |
| Headline metrics | M1–M6 (demo-tier denominators) | M1–M6 (thesis-tier denominators) |
| Assistant | 10-question set (included) | 20-question set |
| 5k throughput | Not run | Measured |
| Packet | Six sections | Six sections + PDF print |
| Demo numbers | Only measured demo-tier values | Only measured thesis values |

**Demo subset (8 features):** PA-VEH-01, PA-DRV-01, PA-COV-01, PA-VEH-02, PA-DRV-02, PA-COV-02, PA-POL-01, PA-POL-02. **8 rules:** PF-GW-SQL-001, PF-GW-SEC-001, PF-GW-PKG-001, PF-GW-EXC-001, PF-GW-TX-001, PF-GW-SRV-001, PF-GW-NAM-001, PF-GW-GUNIT-001. **12 mappings:** R-CG-01, R-CG-02, R-CG-03, R-CG-04, R-GW-24-01, R-API-01, R-API-02, R-API-03, R-API-04, R-API-05, R-API-06, R-TYP-01. **Holdout:** never imported into the demo or used for rule tuning; pre-computed aggregate may be displayed with a “not imported” label. **Assistant:** 10-question set is included in the demo tier.

---

## 15. PA-VEH-01 slice (v5, corrected)

| Layer | Source evidence | Target / disposition | Rule |
|---|---|---|---|
| Installed entity | `PersonalVehicle.eti` field `ModelYear` | schema `modelYear` | R-API-03 |
| Entity extension | `PersonalVehicle.etx` field `GarageLocation_Ext` | schema `garageLocation` | R-API-02 |
| Typelist | `VehicleType.tti` + `extensions/typelist/VehicleType.ttx` typecode `Motorcycle_Ext` | schema enum option `motorcycle` | R-TYP-01 (convention) |
| PCF | `PAVehicleDV.pcf` `TypeKeyInput@VehicleType`, `TextInput@ModelYear`, `TextInput@GarageLocation_Ext` | evidence for `vehicleType`, `modelYear`, `garageLocation` | R-API-01/02/03 |
| Extracted template | `product/template/PersonalAutoTemplate.xml` `PAVehicle`, `Year` | codegen `nameOverride` | R-CG-01/02 |
| Codegen config | `pa_codegen_config_ext-1.0.yaml` | draft with `PAVehicle`, `Year`, `GarageLocation`, `autonumber`, `toCreateAndAdd`, `toRemove` | R-CG-01..04 |
| Gosu | `PersonalVehicleValidation.gs` | evidence only; no rewrite | R-DOC-01 |
| GUnit | `PersonalVehicleValidationTest.gs` (clean), `PersonalVehicleRatingDBTest.gs` (DB-coupled) | inventory + finding | R-TEST-01 |
| Gap | territory requirement | `Gap(missing_source)` + assumption | R-UNR-01 |
| Unsupported | rating inputs | `unsupported` + assumption | R-UNS-01 |

`template_gen_config.xml` is read-only input; no template YAML is drafted. The long-type example is `PersonalAutoRatingFactorConfiguration` (37 chars) in the extracted template, synthetic and labelled.

**SBT readiness:** the second LOB fixture carries an SBT marker. PreFlight emits a `PF-GW-SBT-001` readiness flag (`verified-doc` Olos note, severity warning, `standard_family: none`) and a gap in the packet. It is not part of the PA-VEH-01 demo slice; it proves the tool can surface the documented SBT limitation without attempting conversion.

### 15.1 Demo feature definitions (8)

| Feature | One-line definition | Primary anchor |
|---|---|---|
| PA-VEH-01 | Vehicle information and model year | `PersonalVehicle.eti`, `PersonalVehicle.etx`, `PAVehicleDV.pcf` |
| PA-DRV-01 | Driver information and policy driver link | `PersonalVehicleDriver.eti`, driver PCF, `PADriver` template |
| PA-COV-01 | Coverage selection (liability/collision) | coverage PCF, `PACoverage` template |
| PA-VEH-02 | Vehicle rating factors | rating factor XML, `PAVehicle` template |
| PA-DRV-02 | Driver eligibility and violations | driver eligibility Gosu, violation typelist |
| PA-COV-02 | Coverage terms and limits | coverage term PCF, limit typelist |
| PA-POL-01 | Policy line and editions | `PALine` template, edition metadata |
| PA-POL-02 | Policy questions and availability | question set XML, availability rules |

Each feature has gold evidence anchors and is included in `ground_truth/features.json`; PA-VEH-01 is the only reconstruction slice.

---

## 16. Discovery, reconstruction, comparison, assistant mechanics

### 16.1 Discovery

1. Inventory every file; classify by extension/path/content sniff; hash; list unsupported/corrupt/binary.
2. Parse PCF (`lxml` XPath/line), entity/typelist XML, legacy product XML, extracted template XML, YAML config (`ruamel.yaml`), Gosu scanner (comment/string masked).
3. Extract symbols: PCF widget IDs/bindings, entity fields, typelist codes, product/template types/fields, codegen keys, Gosu declarations/calls/strings, GUnit class/method/base.
4. Assemble feature candidates from `feature_rules.yaml` seeds:
   - seed patterns: PCF screen ID prefix (`PAVehicleDV`), entity name (`PersonalVehicle`), template type (`PAVehicle`), product code (`pa`);
   - link keys: normalized names (`vehicle`, `driver`, `coverage`, `policy`);
   - explicit references resolve first; name-only matches are `inferred-review`;
   - every feature has ≥1 parsed anchor; no feature from a single filename.
5. Emit `features.json`, `spine.json`, `gaps.json`, `manifest.json`.

`spine.json` contract:

```json
{
  "schemaVersion": "1.0",
  "nodes": [{"id": "n1", "kind": "feature|artifact|symbol|config|test", "label": "...", "artifactPath": "...", "evidenceId": "...", "confidence": "parsed|linked|inferred-review"}],
  "edges": [{"id": "e1", "src": "n1", "dst": "n2", "kind": "contains|declares|references|configures|tested_by", "evidenceId": "...", "confidence": "parsed|linked|inferred-review"}],
  "layout": {"columns": ["pcf", "entity", "typelist", "product_template", "api_draft", "tests"]}
}
```

6. Rule-leakage test: no main-fixture literals in `rules/` except public conventions (`_Ext`, `PAVehicle`, `ModelYear`) documented in the ledger.

### 16.2 Reconstruction

1. Select feature + source properties.
2. Apply mapping rules in order; each rule produces a `Mapping` with provenance and confidence.
3. Generate target skeleton files:
   - schema JSON with properties/enums;
   - mapping JSON with source→target entries;
   - updater JSON with create/update paths;
   - codegen YAML with verified overrides;
   - product access YAML.
4. Generate `patch.diff` against an empty target skeleton.
5. Create assumptions for gaps/unsupported.
6. Validate with `preflight-target-v1` JSON Schema + YAML schema; any failure is a visible warning.
7. All changes `pending`; reviewer can accept/reject/edit; edit stores before/after/reason.

### 16.3 Comparison

Compare source property list to sealed reference target and tool draft. Classes as §5. `missing` requires `target_scope_complete=true`; otherwise `unresolved`. `preserved` requires positive equivalence evidence. Emit confusion matrix.

### 16.4 Assistant

- Intent router over question keywords (territory, rating, vehicle, driver, coverage, tests, blockers).
- Retrieves evidence from features/spine/gaps/findings; answers with citations.
- If no evidence: refusal with searched scopes and a question-to-evidence map; never invent files.
- Demo 10-question set: 5 answerable, 5 unanswerable; thesis 20-question set: 10/10.
- Metrics: answer accuracy ≥0.80, citation correctness ≥0.90, refusal precision ≥0.80, refusal recall ≥0.80, no-invented-evidence rate = 0.
- Optional `LLMAdapter` off; deterministic mode is the demo.

### 16.5 API routes

```text
POST /api/projects                 {name, source_root}
POST /api/projects/{id}/snapshots  multipart zip or bundled path
POST /api/runs                     {project_id, force}
GET  /api/runs/{id}/status
POST /api/runs/{id}/cancel
GET  /api/runs
GET  /api/runs/{id}/manifest?page=&size=
GET  /api/runs/{id}/features
GET  /api/runs/{id}/features/{feature_id}
GET  /api/runs/{id}/spine
GET  /api/runs/{id}/findings
GET  /api/runs/{id}/mappings
GET  /api/runs/{id}/assumptions
GET  /api/runs/{id}/gaps
GET  /api/runs/{id}/draft
GET  /api/runs/{id}/diff
GET  /api/runs/{id}/audit
GET  /api/runs/{id}/comparison
GET  /api/runs/{id}/metrics
GET  /api/runs/{id}/packet
POST /api/runs/{id}/decisions
POST /api/runs/{id}/delete        (POST-only mutation; no DELETE)
POST /api/runs/{id}/assistant     {question}
GET  /api/health
```

All artifact reads use a path allowlist resolved under the run directory.

---

## 17. Data-contract enums and versions

Add `schema_version: "1.0"` to every record. Enums:

- `Artifact.status`: `parsed|partial|unsupported|binary|corrupt|excluded`.
- `Mapping.reviewer_state`: `pending|accepted|rejected|edited|deferred`.
- `Change.approval_state`: `pending|accepted|rejected|edited`.
- `Assumption.status`: `open|resolved|rejected`.
- `Gap.status`: `open|resolved|accepted|rejected`.
- `Finding.decision`: `open|accepted|rejected|deferred`.
- `Finding.severity`: `error|warning|note|info`.
- `Finding.access`: `public|gated-body|gated-app|mixed|none`.
- `Mapping.provenance`: `guidewire-doc|preflight-convention|reviewer-decision`.
- `Evidence.method`: `xml_xpath|json_pointer|yaml_path|lexer|regex_masked|graph_link|human`.
- `Evidence.confidence`: `parsed|linked|inferred-review|unresolved`.
- `Run.progress`: `{stage, files_done, files_total, percent}`.
- `Run.error`: `{code, message, detail, retryable}`.
- `Snapshot.sha256`: SHA-256 over sorted `(relative_path, file_sha256)` pairs, excluding mtimes.
- `Packet.hashes`: `{snapshot, reference_target, rulepack, audit_head}`.

---

## 18. Target file skeletons (`docs/target-format.md`)

- `policyperiod_pa_ext-1.0.schema.json`: `$schema`, `$id: preflight-target-v1`, `type: object`, `properties` for `modelYear` (integer), `vehicleType` (string enum), `garageLocation` (string), `vin` (string), `make` (string), `usage` (string); `additionalProperties: false`.
- `policyperiod_pa_ext-1.0.mapping.json`: array of `{source, source_layer, target, rule_id, provenance}`.
- `policyperiod_pa_ext-1.0.updater.json`: `{create: {...}, update: {...}}` paths.
- `pa_codegen_config_ext-1.0.yaml`: `types: PAVehicle: {nameOverride: PersonalVehicle, autonumber: VehicleNumber, toCreateAndAdd: createAndAddVehicle, toRemove: removeVehicle, fields: {Year: {nameOverride: ModelYear}, GarageLocation: {requiredForCreate: false}}}, PADriver: {nameOverride: VehicleDriver}, PALine: {nameOverride: PersonalAutoLine}`.
- `pa_ext-1.0.yaml`: `{productCode: pa, productName: PersonalAuto, enabled: true}`.
- Local schema validates JSON files; YAML schema validates codegen/product access. `_gen` files are absent from the draft. Draft is labelled non-deployable.

---

## 19. Demo run-state choreography

| Beat | Run used | Label |
|---|---|---|
| 0:00 cold open | Pre-seeded full run `R-DEMO-THESIS` (or `R-DEMO-CRITICAL`) | “Synthetic demo estate” |
| 0:25 Manifest live import | `demo-slice-300`, run `R-LIVE-...` | “Live import, 300-file slice” |
| 0:55 Workbench spine | Return to pre-seeded run | “Full snapshot, pre-seeded for the demo” |
| 1:45 Reconstruction | Pre-seeded run | “Draft pending review” |
| 2:45 Findings | Pre-seeded run | “Advisory findings” |
| 3:15 Assistant | Pre-seeded run | “Retrieval-only, model off” |
| 3:35 Packet | Pre-seeded run | “Local packet, not a quote” |
| 4:15 Evaluation | Pre-seeded run; holdout aggregate labelled | “Demo-tier metrics; holdout not imported” |

No unscripted wait >10s; backup screenshots from the frozen run; `preflight verify-audit` shown once.

---

## 20. Claims-ledger mechanics

- `docs/claims-ledger.json` is the canonical machine-readable ledger; `docs/claims-ledger.md` is the human-readable companion.
- JSON fields: `id`, `claim`, `status`, `access`, `source_url`, `quote`, `falsifier`, `consequence`, `rule_ids`.
- `PRODUCT-CLAIM` and `access: none` are valid for conventions/heuristics; `source_url` may be empty only for `PRODUCT-CLAIM`.
- Every rule ID in `rules/*.yaml` must appear in at least one `rule_ids` entry or be labelled `heuristic` with a C-027/C-032 row.
- `PF-GW-NAM-001` is `verified-doc`; `PF-GW-LOG-001/002` and `PF-GW-GUNIT-001` are `heuristic`; `PF-GW-SBT-001` uses C-005.
- Linter checks: status enum, URL (unless PRODUCT-CLAIM), access date, quote/paraphrase, falsifier, consequence, rule-ID coverage.

---

## 21. Acceptance suite (restored, tier-scoped)

| ID | Test | Demo pass | Thesis pass |
|---|---|---|---|
| A1 | Manifest completeness | 100% files hashed; 0 source writes | same |
| A2 | Discovery | main ≥6/8, holdout ≥3/4; precision ≥0.75 | main ≥9/12, holdout ≥4/6; precision ≥0.75 |
| A3 | Disposition | 100% explicit; correctness ≥0.75; non-unresolved ≥0.70 | same |
| A4 | Draft | 100% local schema conformance; all pending; `_gen` absent | same |
| A5 | Review | accept/reject/edit persists; audit verifies; source unchanged | same |
| A6 | Findings | 8 rules; precision ≥0.80/recall ≥0.70 macro; per-rule n reported | 10 rules; same |
| A7 | Comparison | five classes tested; no false `missing`; reference macro-F1 reported | same |
| A8 | Metrics | M1–M6 with numerators/denominators/CIs/caveats; measured only | same |
| A9 | Product | six routes; empty/loading/partial/error states | same |
| A10 | Live import | 300-file zip <10s; progress/cancel/cleanup; re-run | same |
| A11 | Scale | not run (labelled) | 5k completes; time/RSS reported |
| A12 | Boundary | no tenant/assets; disclaimers visible | same |
| A13 | Offline | no network requests after setup | same |
| A14 | Claims linter | zero prohibited phrases/unverified IDs; ledger fields valid | same |
| A15 | Assistant | 10 questions; citation/refusal; no invented evidence | 20 questions |
| A16 | Packet | six sections; hashes; offline open; no raw secrets | same + PDF |
| A17 | Spine | expected nodes/edges; click opens evidence; table fallback | same |
| A18 | States/a11y | empty/loading/partial/error; keyboard/focus; contrast; reduced motion | same |
| A19 | Security | tamper/verify; CSRF; XSS; zip-slip; XXE; YAML tags; secret leak; path traversal; CSP | same |
| A20 | Target contract | schema/mapping/updater/codegen/product-access validate; `_gen` untouched | same |
| A21 | Job/API | state machine; progress; cancel; atomic writes; re-run idempotency; error shapes | same |
| A22 | PA-VEH-01 invariants | 11 references, 4 artefact types, 2 tests; counts derived from a labelled edge list in `ground_truth/pa_veh_01_edges.json`, not hard-coded | same |
| A23 | Holdout isolation | holdout not in demo config; no holdout path in `rules/`; freeze manifest verifies | same |

---

## 22. Final gate

Three independent critics score: domain accuracy, product/UX, architecture/data, evaluation rigor, claims/legal/security, delivery realism (1–10). **Pass:** all ≥8, no major gap, at least two BUILD verdicts. Record in `plans/07-critic-review-v5.md`. Implementation proceeds only after pass.
