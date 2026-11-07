# PreFlight — Product & Implementation Plan v3 (build-ready)

**Status:** Third revision. Addresses the v2 domain, architecture, evaluation, and judge reviews. Build may start only after the v3 gate in §19 records all categories ≥8 and no major gaps.
**Date:** 7 November 2026
**Supersedes:** `plans/02-preliminary-plan.md`, `plans/03-plan-v2.md`
**Repo:** `/home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration`

---

## 0. v2 → v3 corrections (read this first)

| # | v2 issue | v3 correction | Evidence |
|---|---|---|---|
| 1 | Source scenario mixed pre-APD and APD artefacts | Scenario is now **Cloud Retrofit readiness for a non-APD-native Personal Auto estate**. Source contains legacy product-model XML, not APD product/edition JSON. Target is a Cloud API LOB extension draft. | Guidewire Cloud Retrofit docs; “Files that define LOB-specific endpoints” |
| 2 | `policyperiod_pa_ext` and `apis/schemas` paths | Exact paths: `config/integration/schemas/ext/policyperiod/v1/policyperiod_<productCode>_ext-1.0.schema.json`; `config/integration/mappings/ext/policyperiod/v1/...`; `config/integration/updaters/ext/policyperiod/v1/...`; `config/integration/apis/ext/policyperiod/v1/...` (swagger); `config/integration/apis/installedlobs/<productCode>_ext-1.0.yaml` and codegen config; `gsrc/gw/rest/ext/pc/policyperiod/<productCode>/v1`. | “Files that define LOB-specific endpoints,” Guidewire docs, 22 Oct 2026 |
| 3 | `PAVehicle`/`Year` examples questioned | They are **verified** in the Personal Auto codegen config example: `PAVehicle: nameOverride: PersonalVehicle`, `PAVehicle.fields.Year: nameOverride: ModelYear`, `GarageLocation.requiredForCreate: false`, `autonumber: VehicleNumber`, `toCreateAndAdd: createAndAddVehicle`, `toRemove: removeVehicle`, `PADriver: nameOverride: VehicleDriver`, `PALine: nameOverride: PersonalAutoLine`. | “Codegen config file syntax,” Guidewire docs, 22 Oct 2026 |
| 4 | Cloud API naming normalization missing | Add the separately documented endpoint-generation normalization: `PersonalVehicle` → `Vehicle`, `VehicleDriver` → `Driver`; `VehicleDriverExtResource.finishCreate` links driver to `PALine`. | “Generating endpoints for the Personal Auto product,” Guidewire docs, 22 Oct 2026 |
| 5 | `nameOverride` scope ambiguous | State the documented scope: field-level `nameOverride` is for **Cloud Retrofit without APD App**; for APD conversion/APD-assisted Retrofit use `schemaPropertyName`. v3 targets the non-APD path. | Codegen config syntax doc |
| 6 | Rule IDs `IS-INT-1335`/`IS-SEC-1332` misuse | Removed from servlet/secret rules. `IS-INT-1335` is “Use of Guidewire Integration Framework,” not servlets. `SEC00-G` is the secret rule. | Public hardening/Gosu guidance |
| 7 | `verified-doc` not in enum | Enum is now `verified-id | verified-policy | verified-doc | secondary | heuristic`. Every finding also has `standard_family` (`cloud-standard | gosu-secure-coding | internal-guidance | none`). | v2 critic fix |
| 8 | Claims ledger missing | `docs/claims-ledger.md` is a P0 deliverable with URL, access date, exact quote, falsifier, and planning consequence. Claims linter gates build. | v2 critic fix |
| 9 | Evaluation circular/tautological | Add frozen ground truth/reference target, four baselines, κ/adjudication, estimate-moving issue recall, reference-target macro-F1, explicit denominators, Wilson intervals; demote structural validity to a conformance gate. | v2 evaluation critic |
| 10 | “Priced” overclaim | Replace with **impact range (engineer-days, heuristic)** with formula, inputs, confidence, caveat. Headline: “estimate-moving surprises,” not “six-figure.” | v2 judge critic |
| 11 | Six screens were actually ~15 views | True IA: **Workbench, Reconstruction, Findings, Evaluation, Packet, Manifest** (Manifest can be a drawer). Comparison is a Reconstruction tab. Runs/Settings/About secondary. | v2 architecture critic |
| 12 | Import job model missing | Background worker + progress polling + cancel + cleanup; live demo uses a 300-file slice; full 1,500-file run pre-seeded and measured. | v2 architecture critic |
| 13 | Evidence “file, line” breaks on JSON/YAML | `Locator` union: XML XPath + line; JSON Pointer + excerpt + optional line; YAML path + line via `ruamel.yaml`; UI says “file + line/pointer.” | v2 architecture critic |
| 14 | Spine/packet under-specified | `spine.json` contract + deterministic layered SVG + table fallback; six-page packet with print CSS, hashes, disclaimers. | v2 critics |
| 15 | Security hand-wavy | Exact CSP, CSRF synchronizer token, POST-only mutations, Host/Origin allowlist, zip limits, XSS vectors, hash-chained audit, secret redaction at capture. | v2 security critic |
| 16 | Delivery math wrong | 10-day demo path + 16-day thesis path; phase sums include a visible buffer row; 2-person capacity model. | v2 critics |

---

## 1. Positioning

**Product:** PreFlight — *Independent Cloud-Readiness Review for InsuranceSuite-Style Estates.*
**Scenario:** a non-APD-native Personal Auto estate being prepared for **Cloud Retrofit / Cloud API endpoints**, before an APD conversion or SI engagement.
**Buyer:** SI migration practice lead or insurer program director, at bid/scope time.
**Artifact:** a **review packet** — evidence-linked feature inventory, documented blockers, one Cloud API extension draft, an impact-rated assumption register, and a hash-chained review trail.
**Headline:** *Find the estimate-moving surprises before kickoff.*
**Tagline:** *Every claim has evidence; every unknown has a name; every change waits for a human.*
**Not:** APD converter, Cloud Retrofit replacement, Cloud Assurance pass/fail, generic Gosu linter, live tenant connector, autonomous migration.

---

## 2. Verified domain base (summary; full ledger in `docs/claims-ledger.md`)

| Fact | Status | Consequence |
|---|---|---|
| Olos Dec 2025, Palisades Apr 2026, Qusar Aug 2026 (current); three releases/year; N−2 support. | VERIFIED | Pin release context per run. |
| APD conversion is services-led Early Access; vendor estimate 6–8 weeks per average monoline including testing; SBT excluded in Olos. | VERIFIED vendor claim / Olos note | Readiness flag, not a converter. |
| Cloud Retrofit ≠ APD conversion. Non-APD path extracts a template, visualizes, validates, generates LOB endpoints, fixes compile errors. | VERIFIED | Target is a Cloud API extension draft, not APD product conversion. |
| Exact LOB file locations: `config/integration/schemas/ext/policyperiod/v1`, `.../mappings/ext/policyperiod/v1`, `.../updaters/ext/policyperiod/v1`, `config/integration/apis/ext/policyperiod/v1`, `config/integration/apis/installedlobs`, `gsrc/gw/rest/ext/pc/policyperiod/<productCode>/v1`. `_gen` files are generated and must not be edited; `_ext` files are extension files. | VERIFIED | Draft only `_ext`; never edit `_gen`. |
| Codegen config verified Personal Auto example: `PAVehicle: nameOverride: PersonalVehicle`; `PAVehicle.fields.Year: nameOverride: ModelYear`; `GarageLocation.requiredForCreate: false`; `autonumber: VehicleNumber`; `toCreateAndAdd: createAndAddVehicle`; `toRemove: removeVehicle`; `PADriver: nameOverride: VehicleDriver`; `PALine: nameOverride: PersonalAutoLine`. | VERIFIED | Use these as `guidewire-doc` mapping rules. |
| Endpoint-generation normalization: `PersonalVehicle` → `Vehicle`, `VehicleDriver` → `Driver`; `VehicleDriverExtResource.finishCreate` links driver to `PALine`. | VERIFIED | Show as a separate API-naming rule. |
| APD type names limited to 24 chars; truncation fixed with `nameOverride` (example `WCRetroRatingLetterOfCredit` → `WCRetroRatingLetterOfCre`). | VERIFIED | Implement `PF-GW-NAM-001` on APD type names only. |
| Cloud Assurance = TeamCity + Studio inspections + Cloud Assurance Plugin; `NEEDS WORK` over threshold; threshold/corpus gated. | VERIFIED process / GATED details | Findings advisory; “Official Cloud Assurance: not run.” |
| Verified rule IDs: `IS-TLS-1238` direct SQL/JDBC; `IS-TLS-1191` hidden package; `IS-TLS-1022` deprecated API; `SEC00-G` hard-coded secrets; `ERR00-G` swallowed exceptions. `IS-INT-1335` = Integration Framework. `IS-SEC-1289` = Gosu Secure Coding Standard document. | VERIFIED titles / GATED bodies | Use only these; no invented IDs. |
| PCF = **Page Configuration File(s)**, XML, Studio-enforced; no public canonical XSD. | VERIFIED terminology / GATED schema | No XSD-validation claim. |
| SonarQube Cloud added native Gosu in Sept 2026; generic Gosu linting is occupied. | VERIFIED | Do not compete on generic linting. |
| Developer Assistants for Gosu/Integrations/Jutro are GA in Qusar, MCP-based; docs gated. | VERIFIED | Complementary evidence/review, not an integration. |
| TrainingApp/GO/Marketplace/Cloud Standards are gated/copyrighted. | VERIFIED | Synthetic fixture; cite, don’t copy. |

---

## 3. Product scope and IA

### 3.1 True six-screen IA

| Route | Screen | Contains | Demo role |
|---|---|---|---|
| `/` | **Workbench** | Snapshot header, feature list, **feature spine** SVG, evidence drawer, Grounded Assistant, unknown/gap panel | Cold open + feature trace |
| `/reconstruction` | **Reconstruction** | Tabs: Mappings, Draft & Diff, Assumptions, Comparison | Decision queue |
| `/findings` | **Findings** | Advisory findings table + detail drawer + source/claim-strength panel | Trust + domain depth |
| `/evaluation` | **Evaluation** | Six metrics, baselines, per-fixture table, limitations, scale result | Proof |
| `/packet` | **Packet** | Six-page packet preview, export HTML/JSON, audit head, assumptions | Closing artifact |
| `/manifest` | **Manifest** | File table, parser status, unsupported/corrupt/binary, hashes, pagination | Live import + honesty |

Secondary: About/Boundaries, Settings (release context, rule pack), Runs (history). No notification bell, avatar, command palette, or fake charts.

### 3.2 Feature slice

**PA-VEH-01 Vehicle Information** on a non-APD Personal Auto estate:

| Source artefact | Evidence | Target / disposition |
|---|---|---|
| `config/metadata/entity/PersonalVehicle.eti` | Year, Make, VIN, Usage | schema properties |
| `config/extensions/entity/PersonalVehicle.etx` | `GarageLocation_Ext` | `garageLocation` (PreFlight convention; review) |
| `config/metadata/typelist/VehicleType.tti` + `.ttx` | `Motorcycle_Ext` | target enum option (convention; review) |
| `config/web/pcf/policy/PAVehicleDV.pcf` | `TypeKeyInput`, `TextInput` | API field mapping |
| `config/resources/productmodel/PersonalAuto.xml` | `PAVehicle`, `PersonalVehicle`, `VehicleDriver`, long type | product/type-name evidence |
| `config/apd/model/generate/json/template_gen_config.pa.yaml` | field names, TODO | template config draft |
| `config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml` | `nameOverride` entries | codegen draft |
| `config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json` | `vehicleType`, `garageLocation` | schema extension draft |
| `config/integration/mappings/ext/policyperiod/v1/...` | field mappings | mapping draft |
| `config/integration/updaters/ext/policyperiod/v1/...` | updater | updater draft |
| `gsrc/.../PersonalVehicleValidation.gs` | validation logic | evidence only |
| `gtest/.../PersonalVehicleValidationTest.gs` | pure unit test | inventory |
| `gtest/.../PersonalVehicleRatingDBTest.gs` | DB-coupled smell | finding |

### 3.3 Out of scope

APD product conversion/import, live tenant, Cloud API deployment, PCF→Jutro, full Gosu AST/type resolution, rating/quote engine, 50-state product generation, claims payment, generic security scanner, reviewer-effort claim, second LOB feature (noise only).

---

## 4. Architecture

### 4.1 Stack

Python 3.12 · FastAPI · Jinja2 · vanilla JS/CSS · `lxml` · `ruamel.yaml` (line marks) · Pydantic v2 · JSON run store + SQLite index · pytest · Playwright. No React, Streamlit, ANTLR4, graph DB, vector DB, or live tenant adapter.

### 4.2 Pipeline and job model

`Snapshot → Intake → Parse → Discover → Review → Reconstruct → Compare → Evaluate → Packet`.

- Analysis runs in a background worker thread; `POST /api/runs` returns `run_id` + `queued`; `GET /api/runs/{id}/status` returns stage/progress; `POST /api/runs/{id}/cancel` cancels; cleanup deletes temp extraction.
- Live demo uses a 300-file slice; full 1,500-file run is pre-seeded and measured. No unscripted wait >10s.
- Stages write JSON to `data/runs/<run_id>/`; UI reads artifacts only.

### 4.3 Target format contract (`docs/target-format.md`)

Draft files (all under `drafts/`):

```text
config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json
config/integration/mappings/ext/policyperiod/v1/policyperiod_pa_ext-1.0.mapping.json
config/integration/updaters/ext/policyperiod/v1/policyperiod_pa_ext-1.0.updater.json
config/integration/apis/ext/policyperiod/v1/policyperiod_pa_ext-1.0.swagger.yaml
config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml
config/integration/apis/installedlobs/pa_ext-1.0.yaml
config/apd/model/generate/json/template_gen_config.pa.yaml
gsrc/gw/rest/ext/pc/policyperiod/pa/v1/PersonalVehicleExtResource.gs
```

Rules: `_gen` files are never edited; only `_ext` files are proposed. Draft is local/non-deployable. JSON Schema `preflight-target-v1` validates schema/mapping/updater JSON and YAML contracts. Swagger/Gosu resource files may be scoped out if not implemented; the plan must say so.

### 4.4 Evidence locator contract

```text
Locator = {kind: xpath|json_pointer|yaml_path|line, value, line?, column?, excerpt_sha}
```

- XML: `lxml.sourceline` + `getpath`.
- JSON: JSON Pointer + excerpt hash; line optional.
- YAML: `ruamel.yaml` line/column marks.
- UI label: “file + line/pointer,” never “file, line” when only a pointer exists.

### 4.5 Data model additions

`Project/Snapshot`, `Gap/Unknown` (`missing_source|missing_target|ambiguous_reference|unsupported`), `GraphNode/Edge`, `ComparisonRow`, `Rule`, `Decision`, `AuditEvent` (`prev_hash`,`hash`), `Packet`. `Change` includes `edited_value`, `previous_value`, `edit_reason`, `edited_by`, `edited_at`. All records have `schema_version`.

### 4.6 Security contract

- Bind `127.0.0.1`; Host/Origin allowlist; CSRF synchronizer token; SameSite=Strict; POST-only mutations.
- Jinja autoescape; no `|safe`; JS `textContent`; CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`.
- Zip: max 20k files, 500 MB compressed, 2 GB uncompressed, ratio 100:1, reject encrypted entries, symlinks, absolute paths, `..`, NUL, drive letters; random temp dir; no execution.
- XML: `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`.
- YAML: `safe_load`; no tags.
- Secrets redacted at capture; store fingerprint only; packet/logs tested for raw secrets.
- Hash-chained `audit.jsonl`; `preflight verify-audit`; label “tamper-evident local log, not non-repudiation.”
- No network calls by default; optional LLM adapter off; no telemetry.

---

## 5. Discovery

- Parsers: inventory, PCF, entity/typelist, legacy product XML, config YAML, Gosu scanner, GUnit mode.
- Feature candidate assembly is YAML-rule + explicit-reference based; call it **candidate assembly**, not semantic discovery.
- `linked` only when an explicit identifier/XPath/JSON Pointer resolves; name-only = `inferred-review`.
- Every feature has ≥1 parsed anchor; unsupported/corrupt/binary files listed.
- Main fixture: 1,500+ files, two LOBs, 12 labelled features, generated code, plugin, duplicate customisation, shared entities, 1 corrupt XML, 1 binary, noise. Holdout: 300 files, 6 features, different naming, same generator (labelled as naming-shift holdout, not distribution shift).
- 5,000-file throughput test: report time/memory; not a generalisation claim.
- Rule leakage test: `rules/` must not contain main-fixture-only literals; use structural seeds + public conventions.

---

## 6. Reconstruction

### 6.1 Mapping provenance

`provenance: guidewire-doc | preflight-convention | reviewer-decision`; `guidewire-doc` requires URL + exact quote; `preflight-convention` requires reviewer approval; `confidence` and `rationale` required.

### 6.2 Mapping rules (verified + conventions)

| Rule | Source | Target / disposition | Provenance |
|---|---|---|---|
| R-CG-01 | `PAVehicle` (APD type) | `nameOverride: PersonalVehicle` | guidewire-doc (codegen config syntax) |
| R-CG-02 | `PAVehicle.fields.Year` | `nameOverride: ModelYear` | guidewire-doc (codegen config syntax; Cloud Retrofit without APD App) |
| R-CG-03 | `PADriver` | `nameOverride: VehicleDriver` | guidewire-doc |
| R-CG-04 | `PALine` | `nameOverride: PersonalAutoLine` | guidewire-doc |
| R-API-01 | `PersonalVehicle` | API type `Vehicle` | guidewire-doc (Personal Auto endpoint generation) |
| R-API-02 | `VehicleDriver` | API type `Driver` | guidewire-doc |
| R-API-03 | `VehicleDriverExtResource` | `finishCreate` links driver → `PALine` | guidewire-doc |
| R-GW-24-01 | APD type name >24 chars | add `nameOverride` for truncated type | guidewire-doc (correcting compile errors) |
| R-API-04 | PCF `VehicleType` | schema property `vehicleType` | preflight-convention |
| R-API-05 | `GarageLocation_Ext` | schema property `garageLocation` | preflight-convention |
| R-TYP-01 | `Motorcycle_Ext` | target option `motorcycle` | preflight-convention |
| R-UNR-01 | territory requirement | `gap` (no source) | reviewer-decision |
| R-UNS-01 | rating inputs | `unsupported` | reviewer-decision |
| R-TEST-01 | DB-coupled test | advisory finding, not target mapping | preflight-convention |

### 6.3 Draft, diff, assumptions

- Target skeleton under `templates/target/`; draft writer writes only `data/runs/<id>/draft/`.
- Emits `mapping.json`, `changes.json`, `assumptions.json`, `patch.diff`, draft files.
- Every `gap`/`unsupported` creates an assumption with impact, owner, question, `impact_range` (engineer-days), `impact_basis` (formula), `impact_confidence`, `impact_caveat`.
- Impact formula (heuristic, not a quote): `references × 0.5 + artefact_types × 0.25 + tests × 0.5`, rounded to a 1–2 day range; label “heuristic, not a price.”
- Unresolved assumptions cannot be approved as verified.

---

## 7. Review (Agent 2, deterministic)

| Rule | Check | Claim strength | Standard family | Severity |
|---|---|---|---|---|
| PF-GW-SQL-001 | Direct JDBC/SQL | verified-id `IS-TLS-1238` | cloud-standard | error |
| PF-GW-SEC-001 | Hard-coded secret | verified-id `SEC00-G` | gosu-secure-coding | error |
| PF-GW-PKG-001 | Hidden/internal package | verified-id `IS-TLS-1191` | cloud-standard | error |
| PF-GW-EXC-001 | Swallowed exception | verified-id `ERR00-G` | gosu-secure-coding | warning |
| PF-GW-TX-001 | Commit inside `runWithNewBundle` | secondary | internal-guidance | warning |
| PF-GW-SRV-001 | Custom servlet | verified-policy | internal-guidance | warning |
| PF-GW-LOG-001 | PII/credential in logs | verified-policy | internal-guidance | warning |
| PF-GW-LOG-002 | `print` / `printStackTrace` | verified-policy | internal-guidance | warning |
| PF-GW-GUNIT-001 | DB access in pure unit test | verified-policy | internal-guidance | warning |
| PF-GW-NAM-001 | APD type name >24 chars | verified-doc | none | warning |

No `IS-INT-1335` for servlets; no `IS-SEC-1332`/`IS-SEC-1008`/`IS-IMP-1017` in MVP; `IS-TLS-1022` parked (no public symbol list). Findings show claim strength + standard family + “pattern match, not a determination” + “Official Cloud Assurance: not run.”

---

## 8. Comparison

Compare source feature properties to an **independently authored, sealed reference target** and to the tool draft. Classes: `preserved`, `changed`, `missing`, `added`, `unresolved`. `missing` requires complete target scope; otherwise `unresolved`. `preserved` requires positive equivalence evidence, not name similarity. Report reference-target macro-F1 + confusion matrix.

---

## 9. Grounded Assistant

Deterministic retrieval over evidence graph; answers only with citations; refuses when evidence is missing; shows retrieval trace (“searched these evidence IDs; no rating table; these files would answer it”). Optional `LLMAdapter` (`NullLLM` default) narrates from evidence IDs only; every claim validated. UI badge: “Grounded assistance · retrieval-only · model off.”

---

## 10. Evaluation

### 10.1 Fixtures and freeze

- Main: `acme-pc-2026.10` (1,500+ files, 2 LOBs, 12 features, 10 findings, 4 gaps, 2 ambiguities, corrupt/binary/generated/plugin).
- Holdout: `northstar-pc-2026.10` (300 files, 6 features, different naming; same generator; naming-shift only).
- Reference target: separately authored, sealed before mapping rules; hash + timestamp in `ground_truth/FROZEN.json`.
- Ground truth: features, evidence, mappings, findings, gaps; 30-link and 20-finding adjudication samples; annotation guide; Cohen’s κ.
- Rule leakage test: no fixture-specific literals in `rules/`.
- GT import boundary: product code must not import `ground_truth/`.

### 10.2 Baselines

1. Identity/name-match mapper (preserve if normalized names match; else unresolved).
2. All-unresolved mapper (floor).
3. Grep-only findings scan (no masking/allowlists).
4. PCF-only discovery (no cross-artefact linking).

Thresholds are **baseline + margin**, pre-registered before the first holdout run.

### 10.3 Headline metrics

| Metric | Definition | Denominator | Caveat |
|---|---|---|---|
| Feature discovery recall | gold features found / all gold features | 12 main + 6 holdout | naming-shift holdout, not generalisation |
| Feature discovery precision | correct candidates / all emitted candidates | emitted | decoys included |
| Evidence-link precision | audited links that resolve and support / audited links | stratified 30-link sample | double-audited, κ reported |
| Disposition correctness | correct target/disposition / gold mappings | 12 gold mappings | split by provenance |
| Estimate-moving issue recall | planted high-impact issues surfaced with evidence / planted issues | 6 planted issues | triage proxy |
| Reference-target agreement | macro-F1 vs sealed reference target | per-class support | not a deployability claim |
| Finding precision/recall | per-rule TP/(TP+FP), TP/(TP+FN) | 10 rules × ≥3 positive + ≥3 hard negative | per-rule n reported |
| Silent omission | gold-scope fields with no disposition / gold-scope fields | gold field list | separate estate coverage number |
| Non-unresolved disposition rate | mapped/dropped/N-A / gold fields | gold fields | prevents “mark everything unresolved” |
| Local schema conformance | draft files passing `preflight-target-v1` / draft files | draft files | sanity gate, not headline |

Report raw counts, Wilson 95% intervals, per-fixture/per-rule tables, failures, and all caveats. No reviewer-effort claim.

### 10.4 Scale

5,000-file throughput test; report wall time, peak RSS, hardware. Label throughput, not estate complexity.

---

## 11. Test-first plan

Order: models → intake → parsers → discovery → reconstruction → review → compare → evaluate → assistant → API → security → E2E.

Acceptance A1–A19:

| ID | Test | Pass condition |
|---|---|---|
| A1 | Manifest | 100% files listed/hashed; 0 source writes |
| A2 | Discovery | main ≥9/12, holdout ≥4/6; links resolve |
| A3 | Disposition | 100% explicit; correctness ≥75%; non-unresolved ≥70% |
| A4 | Draft | 100% local schema conformance; all pending |
| A5 | Review | accept/reject/edit persists; audit verifies; source unchanged |
| A6 | Findings | per-rule precision/recall reported; thresholds baseline+margin |
| A7 | Comparison | five classes unit-tested; no false `missing` |
| A8 | Evaluation | metrics with numerators/denominators/CIs/caveats |
| A9 | Product | six primary screens; empty/error/partial states |
| A10 | Live import | 300-file zip <10s; progress/cancel/cleanup; re-run |
| A11 | Scale | 5k run completes; time/RSS reported |
| A12 | Boundary | no tenant/assets; disclaimers visible |
| A13 | Offline | no network requests after setup |
| A14 | Claims linter | zero prohibited phrases/unverified IDs; provenance URLs present |
| A15 | Assistant | 10 scripted questions; citations/refusal; no invented evidence |
| A16 | Packet | six sections; hashes; offline open; no raw secrets |
| A17 | Spine | expected nodes/edges; click opens evidence; table fallback |
| A18 | States/a11y | empty/loading/partial/error matrix; keyboard/focus; WCAG basics |
| A19 | Audit/security | tamper/verify; CSRF; XSS; zip-slip; secret leak |

---

## 12. Demo (5 minutes)

| Time | Screen | Action | Message |
|---|---|---|---|
| 0:00 | Workbench | Cold open on `Motorcycle_Ext` / long type | “This is the pattern that shows up at week 5: one typelist value, 11 references, four artefact types, two tests. The estimate moves. We find it before kickoff.” |
| 0:25 | Manifest | Live import 300-file slice; show hash/progress/unsupported | “Read-only, hashed, offline. Unsupported files listed, not hidden.” |
| 0:55 | Workbench | Spine reveal; click node; gap toggle | “PCF → entity → typelist → product → API → test. File + line/pointer. This unknown becomes an assumption.” |
| 1:45 | Reconstruction | Reject territory; accept `PAVehicle → PersonalVehicle`; show impact range | “A decision queue, not a JSON dump. Rejection creates an assumption with owner, impact range, and the question to ask. Source untouched.” |
| 2:45 | Findings | SQL, secret, hidden package, servlet; show `Query` negative; claim strength | “Verified ID, verified policy, heuristic. We would rather be useful than sound official. Cloud Assurance: not run.” |
| 3:30 | Assistant | Ask “Does this estate use territory rating?” | “Cannot determine — no rating table. These three files would answer it.” Show trace. |
| 3:50 | Packet | Export; assumption register; audit head | “The output is a scope you can price, challenge, and sign.” |
| 4:30 | Evaluation | Holdout, baselines, per-rule table, scale | “Raw counts, intervals, failures, caveats. Triage, not an exhaustive audit.” |
| 4:50 | Close | Tagline | “Every claim has evidence; every unknown has a name; every change waits for a human.” |

Synthetic badge from second zero. No fake 201, no official pass, no auto-pay, no 50 states, no live tenant.

---

## 13. Product content, claims, legal

- Footer/About disclaimer: independent research prototype; not affiliated/endorsed/certified by Guidewire; Guidewire, InsuranceSuite, PolicyCenter, ClaimCenter, BillingCenter, Gosu, APD, Jutro, Integration Gateway, Cloud Assurance, Developer Assistants, and InsuranceNow are trademarks/registered trademarks of Guidewire Software, Inc.; all other trademarks belong to their owners; Source Sans 3 under SIL OFL; synthetic fixture; no customer data or confidential Guidewire information; pattern-based heuristics, not official Cloud Standards checks; not legal/security/compliance advice.
- Claim legend: Designed / Implemented / Measured / Proposed / Gated.
- Prohibited-phrase linter: “Guidewire-certified”, “Cloud Assurance pass”, “APD converter”, “production-ready”, “100% detection”, “replaces Cloud Assurance”, “6–8 weeks → 5 minutes”, “first AI migration tool”, “six-figure”, unverified IDs.
- AI disclosure: AI assistance used in planning/reviews; product LLM off by default; no customer code leaves the machine.

---

## 14. Impact range (replaces “priced”)

Each assumption has:

```json
{
  "impact_range_days": [3.0, 5.0],
  "impact_basis": "11 references × 0.5 + 4 artefact types × 0.25 + 2 tests × 0.5 = 7.5, capped and rounded to 3–5 with review buffer",
  "impact_confidence": "low|medium|high",
  "impact_caveat": "Heuristic planning range; not a quote or measured productivity claim."
}
```

The UI and packet show the formula and inputs. Headline says “estimate-moving,” not “six-figure.”

---

## 15. Delivery

### 15.1 Two tiers

| Tier | Scope | Time |
|---|---|---|
| Demo-critical | 600–800 files + 150 holdout; 8 features; 8 rules; 8 mappings; Workbench/Reconstruction/Findings/Evaluation/Packet + Manifest drawer; 4 metrics + finding P/R; assistant optional; no 5k gate | 10 days |
| Thesis-complete | 1,500 files + 300 holdout; 12 features; 10 rules; 12 mappings; six metrics; assistant; 5k measurement; full audit | 16 days |

### 15.2 Phase plan (thesis-complete)

| Phase | Days | Output | Gate |
|---|---|---|---|
| P0 Plan gate | 0.5 | v3 scorecard + claims ledger | all ≥8, no major gaps |
| P1 Contracts + fixtures | 4 | Tests, seed fixture, 1,500-file generator, holdout, GT, reference target, target-format doc | tests fail for right reasons |
| P2 Core pipeline | 4 | intake, parsers, discovery, reconstruction | A1–A5 |
| P3 Review/compare/eval/assistant | 3 | findings, comparison, metrics, baselines, assistant | A6–A8, A15 |
| P4 Product UI | 4 | six screens, states, spine, packet | A9, A16–A18 |
| P5 Hardening | 1 | security, scale, offline, claims linter | A10–A14, A19 |
| P6 Independent verification | 1 | critic scorecards + fixes | all ≥8 |
| P7 Demo package | 0.5 | screenshots, packet, rehearsal | offline demo |
| **Buffer** | **2** | 20% of 10 build days | — |
| **Total** | **20.0** | includes buffer; thesis tier can cut to 16 by dropping assistant/5k | |

For this session, implement the **demo-critical tier first**, then extend.

### 15.3 Cut order

Assistant → 5k scale → second LOB feature → extra metrics → packet PDF. Never cut: evidence, hashes, unsupported reporting, pending approvals, assumptions, denominators, disclaimers.

---

## 16. Deviations from the report

| Report | v3 | Rationale |
|---|---|---|
| Streamlit | FastAPI + Jinja2 + vanilla JS | Product shell, testability. |
| Three autonomous agents | Deterministic stages labelled Agent 1A/1B/2/3 | Evidence discipline; “agent” is product language. |
| APD conversion draft | Cloud API LOB extension draft | Source is non-APD; target format is documented. |
| “AI-powered” | Evidence-first + optional grounded narration | No unverifiable AI claim. |
| 8 features | 12 main + 6 holdout | Evaluation needs holdout. |
| Reviewer effort | Future work | No credible pilot. |
| Simulated figures | Real screenshots + synthetic labels | Integrity. |

---

## 17. Risks

| Risk | Mitigation |
|---|---|
| Target format challenged | Exact paths + `docs/target-format.md` + conformance tests + “local/non-deployable.” |
| Mapping rules challenged | Verified quotes; only documented rules use `guidewire-doc`; conventions require review. |
| Fixture realism challenged | Two LOBs, generated/plugin/corrupt/binary, fidelity appendix, holdout, scale test. |
| Evaluation challenged | Frozen GT, baselines, κ, intervals, per-rule n, limitations. |
| Demo failure | Pre-seeded + 300-file live import + progress + backup; tmux health check. |
| Scope slip | Two tiers; cut list; 2-day buffer. |
| Human domain sign-off unavailable | Record AI domain review + user review; label external human sign-off as pending before public submission. |

---

## 18. Final positioning statement

> **PreFlight** is an offline, evidence-first cloud-readiness review product for Guidewire-style legacy estates. It assembles feature candidates across product models, PCF, entities, typelists, Gosu, and Cloud API configuration; links every claim to file evidence; surfaces documented blockers and gaps; and produces a reviewable Cloud API extension draft plus an impact-rated assumption register for one feature slice. It does not convert, certify, or deploy. Every claim has evidence; every unknown has a name; every change waits for a human.

---

## 19. v3 gate

Independent critics score: domain accuracy, product/UX, architecture, evaluation rigor, claims/legal/security, delivery realism (1–10). **Pass:** all ≥8, no major gap, at least two BUILD verdicts. Implementation proceeds only after `plans/04-critic-review-v3.md` records the result.
