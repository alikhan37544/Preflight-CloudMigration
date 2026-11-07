# PreFlight — Product & Implementation Plan (v2, post-critique)

**Status:** Revised after independent domain and judge reviews. This version must pass the re-review scorecard in §19 before build.
**Date:** 7 November 2026
**Supersedes:** `plans/02-preliminary-plan.md`
**Repo:** `/home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration`

---

## 0. What changed from v1

| # | v1 problem | v2 resolution |
|---|---|---|
| 1 | Pseudo-APD JSON target with no public schema | Target is now a documented **Cloud API LOB extension draft** (`_ext.schema.json`, `_ext.mapping.json`, `_ext.updater.json`, `codegen_config_ext`, `template_gen_config`), explicitly labelled local/non-deployable. |
| 2 | Invented mapping transformations (`_Ext` strip, `year→modelYear`, arbitrary `nameOverride`) | Every mapping has provenance: `guidewire-doc`, `preflight-convention`, or `reviewer-decision`. The only “verified” mapping example is the documented 24-char truncation + `nameOverride` case. Other renames are labelled PreFlight conventions and require review. |
| 3 | Unverified rule IDs (`IS-INT-1335` for servlets, `IS-SEC-1332`, `IS-SEC-1008`, `IS-IMP-1017`, `IS-INT-1268`) | Removed. Rule catalog uses only verified IDs (`IS-TLS-1238`, `IS-TLS-1191`, `SEC00-G`, `ERR00-G`) or `verified-policy` labels with no ID. |
| 4 | No claims ledger / no source URLs | `docs/claims-ledger.md` required before build; claims linter in tests. |
| 5 | Circular evaluation / self-graded 100% metrics | Holdout fixture, independent reference target, disposition **correctness**, finding precision/recall on labelled hard negatives, audited evidence sample, explicit limitations. Reviewer effort cut from headline metrics. |
| 6 | PCF syntax/path errors and “Page Configuration Format” | Corrected to **Page Configuration File(s)**. Fixture paths are labelled **illustrative** unless verified. PCF examples use valid XML shapes. No XSD-validation claim. |
| 7 | 10 routes, fake chrome, dashboard-first demo | Six primary screens; no notification bell/avatar/command palette. Demo opens on the **feature spine** and a live import, not a dashboard. |
| 8 | Toy 128-file fixture | 1,500+ file, two-LOB synthetic estate generator; 12 labelled features; corrupt/binary/generated/plugin noise; 5,000-file scale test. |
| 9 | CSRF dismissed; no XSS/CSP; audit log not tamper-evident | 127.0.0.1 bind, Host/Origin checks, CSRF token, autoescape, CSP, hash-chained review log, retention/delete. |
| 10 | “AI-powered” but no AI in demo | Positioned as **evidence-first review with optional bounded narration**. A deterministic Grounded Assistant answers from the evidence graph and refuses when evidence is missing. LLM adapter is off by default. |
| 11 | Report/plan divergence undocumented | Deviations register in §18. |
| 12 | Delivery unrealistic | 2-person capacity stated; 14-day build with a 20% buffer; thin vertical slice first; explicit cut list. |

---

## 1. Positioning

**Product name:** PreFlight — *Independent Cloud-Readiness Review for InsuranceSuite-Style Estates.*

**Buyer/trigger:** an SI migration practice lead or insurer program director, before an APD conversion or Cloud Retrofit engagement, when a fixed-price bid or scope decision depends on unknown legacy customisations.

**Artifact sold:** a **review packet** — evidence-linked feature inventory, documented blockers, one cloud-extension draft, a priced assumption register (impact + owner + question to ask), and a hash-chained review trail.

**One sentence:** *Find the six-figure surprises before kickoff.*

**Tagline:** *Every claim has evidence; every unknown has a name; every change waits for a human.*

**What it is not:** APD converter, Cloud Retrofit replacement, Cloud Assurance pass/fail, generic Gosu linter, autonomous migration, live tenant connector.

---

## 2. Verified domain base

All facts below are recorded with URL, access date, exact quote, and planning consequence in `docs/claims-ledger.md`. Summary:

| Fact | Status | Consequence |
|---|---|---|
| Releases: Olos Dec 2025, Palisades Apr 2026, Qusar Aug 2026 (current); 3/year; N−2 support. | VERIFIED | Pin release context per run; never hard-code one release. |
| APD conversion is a services-led Early Access offering; vendor estimate 6–8 weeks per average monoline including testing. | VERIFIED as vendor claim | Do not claim to replace or reproduce it. |
| SBT lines could not convert to APD-managed lines per Olos; re-verify on target release. | VERIFIED for Olos | Readiness flag, not a conversion attempt. |
| Cloud Retrofit ≠ APD conversion. It generates LOB-specific Cloud API endpoints; APD-assisted path imports then deletes the product. | VERIFIED | Keep product-model readiness and API-extension readiness separate. |
| APD type names limited to **24 characters**; truncation causes compile errors fixed with `nameOverride` in codegen config (verified example: `WCRetroRatingLetterOfCredit` → `WCRetroRatingLetterOfCre`). | VERIFIED | Implement the 24-char warning and the documented example. Do not apply 24 to all names. |
| Cloud Assurance = TeamCity Automated Cloud Assurance + Studio inspections + Cloud Assurance Plugin; `NEEDS WORK` over threshold; threshold and full corpus gated. | VERIFIED process; GATED details | Findings are advisory. UI always shows “Official Cloud Assurance: not run.” |
| Verified public IDs/titles: `IS-TLS-1238` direct SQL/JDBC; `IS-TLS-1191` hidden package; `SEC00-G` hard-coded secrets; `ERR00-G` swallowed exceptions. | VERIFIED titles; bodies gated | Use only these IDs in MVP. |
| `IS-INT-1335` = Use of Guidewire Integration Framework, not custom servlets. `IS-SEC-1289` is the Gosu Secure Coding Standard document. `IS-INT-1268` has no public evidence. | VERIFIED / UNSUPPORTED | Remove the bad associations. |
| PCF = **Page Configuration File(s)**, XML-like, Studio-enforced; no public canonical XSD. | VERIFIED terminology; GATED schema | No XSD-validation claim. |
| APD product/edition exports are JSON/XML; codegen/template config is YAML. No public APD JSON schema. | VERIFIED / GATED | Do not claim official APD importability. |
| SonarQube Cloud added native Gosu in Sept 2026; Server/DC uses Guidewire/third-party plugins. Cloud Assurance does not use SonarQube. | VERIFIED | No generic Gosu linter competition. |
| Developer Assistants for Gosu/Integrations/Jutro are GA in Qusar, MCP-based; technical docs gated. | VERIFIED | Do not plan an integration; position as complementary evidence/review. |
| TrainingApp, GO products, Marketplace content, full Cloud Standards are gated/copyrighted. | VERIFIED | Synthetic fixtures only; cite, don’t copy. |

---

## 3. Product scope

### 3.1 Primary screens (six)

1. **Overview** — snapshot, readiness summary, feature spine preview, attention list.
2. **Features** — feature inventory + evidence detail + **feature spine** (SVG graph) + Grounded Assistant.
3. **Reconstruction** — mapping table, draft files, diff, assumptions, accept/reject.
4. **Findings** — advisory rules with claim strength, evidence, remediation, decision.
5. **Packet** — exportable review packet, assumption register, audit trail.
6. **Manifest** — full-file manifest, parser status, unsupported files (drawer/page from any screen).

Secondary: Runs, Settings, About/Boundaries. No notification bell, avatar, command palette, or fake charts.

### 3.2 Feature slice

**PA-VEH-01 Vehicle Information** — cross-artefact:

| Artefact | Evidence | Target |
|---|---|---|
| `config/metadata/entity/Vehicle.eti` | fields Year, Make, VIN, Usage | schema properties |
| `config/extensions/entity/Vehicle.etx` | `GarageLocation_Ext` | `garageLocation` (PreFlight convention; review) |
| `config/metadata/typelist/VehicleType.tti` + `.ttx` | `Motorcycle_Ext` | target enum option (convention; review) |
| `config/web/pcf/.../PAVehicleDV.pcf` | `RangeInput`, `TextInput` | API field mapping |
| `product/PersonalAuto.json` | `PAVehicle`, attribute `VehicleType` | product/API draft |
| `config/integration/apis/schemas/ext/.../policyperiod_pa_ext-1.0.schema.json` | `vehicleType`, `garageLocation` | schema extension draft |
| `config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml` | `nameOverride` entries | codegen draft |
| `gsrc/.../VehicleValidation.gs` | validation logic | evidence only; no rewrite |
| `gtest/.../VehicleValidationTest.gs` | pure unit test | test inventory |
| `gtest/.../VehicleRatingDBTest.gs` | DB-coupled smell | finding |

### 3.3 Out of scope

Second LOB as a demo feature (it is fixture noise only), live tenant, APD import, Cloud API deployment, PCF→Jutro, full Gosu AST, rating/quote engine, 50-state generation, claims payment, generic security scanner, reviewer-effort claim.

---

## 4. Architecture

### 4.1 Stack

Python 3.12 · FastAPI · Jinja2 · vanilla JS/CSS · `lxml` · Pydantic v2 · YAML rules · SQLite/JSON run store · pytest · Playwright. No React, no Streamlit, no ANTLR4, no graph DB, no vector DB.

### 4.2 Modules

```text
preflight/
  app/
    main.py, config.py, models.py, store.py, security.py
    services/
      intake.py
      parsers/{pcf,entity,typelist,product,config,gosu}.py
      discovery.py
      reconstruction.py
      review.py
      compare.py
      evaluate.py
      assistant.py          # deterministic grounded Q&A
      llm.py                # NullLLM default; optional adapter
    templates/
    static/
  rules/{feature_rules,mapping_rules,review_rules}.yaml
  fixtures/acme-pc-2026.10/        # 1,500+ files, 2 LOBs
  fixtures/northstar-pc-2026.10/   # holdout, 300 files
  ground_truth/
  templates/target/                # Cloud API extension skeleton
  tests/
  scripts/{generate_fixture.py,seed_demo.py,evaluate.py,claims_lint.py}
  docs/{claims-ledger.md,target-format.md,deviations.md,security.md}
  pyproject.toml, Makefile, README.md
```

### 4.3 Pipeline

`Snapshot → Intake → Parse → Discover → Review → Reconstruct → Compare → Evaluate → Packet`.

Each stage writes JSON to `data/runs/<run_id>/`; the UI reads artifacts only. Source snapshot is read-only; hashes before/after must match.

### 4.4 Target format contract

`docs/target-format.md` defines:

- `drafts/config/integration/apis/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json`
- `drafts/config/integration/apis/mappings/ext/policyperiod/v1/policyperiod_pa_ext-1.0.mapping.json`
- `drafts/config/integration/apis/updaters/ext/policyperiod/v1/policyperiod_pa_ext-1.0.updater.json`
- `drafts/config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml`
- `drafts/config/apd/model/generate/json/template_gen_config.pa.yaml`

The draft is a **local, non-deployable extension proposal**, not an APD import. The UI says this on every draft screen and in the packet. `_gen` files are read-only and never edited; only `_ext` files are proposed. The local JSON Schema is named `preflight-target-v1`, never “official Guidewire schema”.

### 4.5 Security

- Bind `127.0.0.1`; validate Host/Origin; per-session CSRF token; SameSite=Strict cookie.
- Jinja2 autoescape; CSP `default-src 'self'`; no inline event handlers; sanitize snippets.
- Zip: reject absolute paths, `..`, symlinks, NUL, drive letters; size/ratio limits; random temp dir; no execution.
- XML: `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`; parser errors are warnings.
- YAML: `safe_load`.
- No network by default; no telemetry; optional LLM adapter off.
- Hash-chained review log (`audit.jsonl` with `prev_hash`); verify command.
- Retention: delete run; no real customer data required; document local-only mode.
- Dependency lockfile + `pip-audit`/`ruff` in CI.

---

## 5. Data model

| Record | Key fields |
|---|---|
| `Run` | run_id, project_id, snapshot_hash, release_context, status, stages, parser_version, rulepack_version, created_at |
| `Artifact` | path, sha256, size, kind, parser, status, warnings, line_count |
| `Evidence` | evidence_id, path, start_line, end_line, xpath, json_pointer, yaml_path, excerpt_sha, excerpt, method, confidence |
| `Feature` | feature_id, name, lob, description, evidence_ids, dependencies, confidence, open_questions |
| `Mapping` | mapping_id, source_ref, source_name, source_type, target_path, target_name, disposition, rule_id, provenance, confidence, rationale, reviewer_state |
| `Change` | change_id, target_path, diff, mapping_id, approval_state, reviewer, reviewed_at, edited_value, previous_value, edit_reason |
| `Assumption` | assumption_id, statement, impact, status, owner, related_mapping_id, question_to_ask |
| `Finding` | finding_id, rule_id, title, severity, confidence, claim_strength, standard_id, standard_title, standard_url, evidence_ids, message, remediation, decision |
| `Metric` | metric_id, label, value, numerator, denominator, unit, caveat, fixture_id |

Confidence: `parsed` / `linked` / `inferred-review` / `unresolved`. Claim strength: `verified-id` / `verified-policy` / `secondary` / `heuristic`. Product status: `designed` / `implemented` / `measured` / `proposed` / `gated`.

---

## 6. Discovery

- Six parsers: inventory, PCF, entity/typelist, product JSON, config YAML, Gosu scanner. GUnit is a scanner mode.
- Feature candidate assembly via YAML rules + explicit references. **Not** “semantic discovery”; call it candidate assembly.
- `linked` only when an explicit identifier/XPath/JSON Pointer resolves to a parsed symbol; name-only matches are `inferred-review`.
- Every feature has at least one parsed anchor.
- Unsupported/corrupt/binary files are listed, never dropped.
- 1,500-file fixture includes generated code, plugin, duplicate customisation, shared entities, two LOBs, noise, one corrupt XML, one binary.
- 5,000-file scale test: target <60s and <1GB RAM; if exceeded, report actual.

---

## 7. Reconstruction

### 7.1 Mapping provenance

Every rule has:

```yaml
provenance: guidewire-doc | preflight-convention | reviewer-decision
source_url: "..."          # required for guidewire-doc
reviewer_approved: false   # required for convention
confidence: high | medium | low
rationale: "..."
```

### 7.2 Mapping set (MVP)

| Rule | Source | Target / disposition | Provenance |
|---|---|---|---|
| R-GW-24-01 | APD type name >24 chars | add `nameOverride` for truncated type | `guidewire-doc` (verified example) |
| R-CG-01 | codegen `PAVehicle` | `nameOverride: PersonalVehicle` | `guidewire-doc` (documented Personal Auto example) |
| R-CG-02 | codegen `Year` | `nameOverride: ModelYear` | `guidewire-doc` (documented Personal Auto example) |
| R-API-01 | PCF `VehicleType` | schema property `vehicleType` | `preflight-convention` |
| R-API-02 | entity `GarageLocation_Ext` | schema property `garageLocation` | `preflight-convention` |
| R-TYP-01 | typelist `Motorcycle_Ext` | target option `motorcycle` | `preflight-convention` |
| R-UNR-01 | `Vehicle.territory` | `needs_decision` | `reviewer-decision` |
| R-UNS-01 | rating inputs | `unsupported` | `reviewer-decision` |
| R-TEST-01 | DB-coupled test | advisory finding, not target mapping | `preflight-convention` |
| R-DOC-01 | evidence-only artefact | no target mapping | `preflight-convention` |

No rule may claim `guidewire-doc` without a URL and exact quote. No rename is labelled “documented” unless it is.

### 7.3 Draft and assumptions

- Target skeleton in `templates/target/`; draft writer only writes to `data/runs/<id>/draft/`.
- `mapping.json`, `changes.json`, `assumptions.json`, `patch.diff`.
- `needs_decision`/`unsupported` create assumptions with impact, owner, and question to ask.
- Unresolved assumptions cannot be approved as verified.
- Draft files validate against `preflight-target-v1` JSON Schema; label “local schema, not official”.

---

## 8. Review (Agent 2, deterministic)

### 8.1 Rule catalog (MVP)

| Rule | Check | Claim strength | Severity | Detection |
|---|---|---|---|---|
| `PF-GW-SQL-001` | Direct JDBC/SQL | verified-id `IS-TLS-1238` | error | masked source regex; negative for `gw.api.database.Query` |
| `PF-GW-SEC-001` | Hard-coded secret | verified-id `SEC00-G` | error | key/value patterns; redact; placeholders allowlisted |
| `PF-GW-PKG-001` | Hidden/internal package | verified-id `IS-TLS-1191` | error | `gw.internal.*`, `com.guidewire.*`; allow `gw.api.*`, `gw.pl.*` |
| `PF-GW-EXC-001` | Swallowed exception | verified-id `ERR00-G` | warning | empty/comment-only catch |
| `PF-GW-TX-001` | Explicit commit in `runWithNewBundle` | secondary (Guidewire developer blog) | warning | brace-matched block containing `.commit()` |
| `PF-GW-SRV-001` | Custom servlet | verified-policy (hardening guidance; no ID) | warning | `HttpServlet`, `javax.servlet`, `@WebServlet`, `<servlet>` |
| `PF-GW-LOG-001` | PII/credential in logs | verified-policy (hardening guidance; no ID) | warning | sensitive field names in log calls |
| `PF-GW-LOG-002` | `print` / `printStackTrace` | verified-policy (hardening guidance; no ID) | warning | `print(`, `System.out`, `printStackTrace` |
| `PF-GW-GUNIT-001` | DB access in pure unit test | verified-policy (unit-test guidance) | warning | `*UnitTestClassBase` + `Query.make`/`commit`/`loadSampleData` |
| `PF-GW-NAM-001` | APD type name >24 chars | verified-doc | warning | APD product model type names only; suggest `nameOverride` |

### 8.2 Discipline

- Finding UI shows claim strength + standard ID/title + “official Cloud Assurance: not run”.
- No “Cloud Assurance violation”.
- `IS-TLS-1022` (deprecated API) is parked: no public symbol list; do not ship a fake rule.
- `IS-INT-1335` is not used for servlets.

---

## 9. Comparison (Agent 3)

Compare source feature properties to an **independently authored reference target** (`ground_truth/reference_target/`), not only the tool’s draft. Classes: `preserved`, `changed`, `missing`, `added`, `unresolved`. Rules:

- `missing` requires complete target scope; otherwise `unresolved`.
- `preserved` requires positive equivalence evidence, not name similarity.
- Every row links to source and target evidence.
- Report agreement between tool draft and reference target.

---

## 10. Grounded Assistant (optional narration)

- Deterministic retrieval over the evidence graph; answers only with citations.
- If evidence is missing, it refuses: “Cannot determine — no rating table in this snapshot. These files would answer it: …”
- Optional `LLMAdapter` (`NullLLM` default, `OllamaAdapter` off) provides prose narration; every claim must cite evidence IDs and pass validation.
- Demo uses deterministic mode; no network, no model download.
- UI badge: “Grounded assistance · retrieval-only · model off”.

---

## 11. Evaluation

### 11.1 Fixtures

- **Main:** `acme-pc-2026.10` — 1,500+ files, 2 LOBs, 12 labelled features, 10 findings, 4 gaps, 2 ambiguities, 1 corrupt XML, 1 binary, generated code, plugin, duplicate customisation, shared entities.
- **Holdout:** `northstar-pc-2026.10` — 300 files, 6 features, different naming, never used to author rules.
- **Reference target:** independently authored from the source and public conventions, frozen before the tool runs.
- **Ground truth:** features, evidence links, mappings, findings, ambiguities, gaps; hashed and versioned.

### 11.2 Metrics (six headline)

| Metric | Definition | Denominator | Caveat |
|---|---|---|---|
| Feature discovery recall | gold features found / all gold features | 12 main + 6 holdout | one synthetic estate; not a benchmark |
| Feature discovery precision | correct features / reported features | reported features | adjudicated labels |
| Evidence-link precision | audited links that resolve and support / audited links | 30-link audit sample | reviewer audit |
| Disposition correctness | correct target/disposition / gold mappings | 12 gold mappings | not coverage-by-construction |
| Silent omission rate | source fields with no disposition / source fields | source fields | planted gaps; target 0 |
| Draft structural validity | draft files passing `preflight-target-v1` / draft files | draft files | local schema, not official |

Additional reported: finding precision/recall on 20 labelled cases (10 positive, 10 hard negatives); comparison macro-F1 vs reference target; scale time/memory. **Reviewer effort is future work, not claimed.**

### 11.3 Test assertions

- Main recall ≥ 0.75; holdout recall ≥ 0.60 (demonstration, not generalisation).
- Evidence audit precision ≥ 0.90 on sample.
- Disposition correctness ≥ 0.75 on 12 gold mappings.
- Silent omission = 0 (all gaps explicit).
- Structural validity = 100% against local schema.
- Finding precision ≥ 0.80; recall ≥ 0.70 on labelled corpus.
- No source writes; hashes match before/after.
- 5,000-file scale run completes and reports time/memory.

---

## 12. Test-first plan

### 12.1 Order

1. `tests/test_models.py` — contracts, validation, serialization.
2. `tests/test_intake.py` — hashing, classification, unsupported files, zip safety.
3. `tests/test_parsers.py` — PCF, entity, typelist, product, config, Gosu scanner.
4. `tests/test_discovery.py` — features, evidence, confidence, gaps, holdout.
5. `tests/test_reconstruction.py` — mapping provenance, dispositions, draft, assumptions.
6. `tests/test_review.py` — rule detections, hard negatives, claim strength.
7. `tests/test_compare.py` — five classes, reference target, no false `missing`.
8. `tests/test_evaluate.py` — metrics, denominators, caveats.
9. `tests/test_assistant.py` — grounded answers, refusal, citations.
10. `tests/test_api.py` — routes, JSON contracts, CSRF, source immutability.
11. `tests/test_security.py` — zip-slip, XXE, XSS, path traversal.
12. `tests/test_e2e.py` — Playwright golden path, offline, screenshots.

### 12.2 Acceptance matrix

| ID | Test | Pass condition |
|---|---|---|
| A1 | Manifest completeness | 100% files listed/hashed; 0 source writes |
| A2 | Discovery | main ≥9/12, holdout ≥4/6; every evidence link resolves |
| A3 | Disposition | 100% source properties have explicit disposition; correctness ≥75% |
| A4 | Draft | 100% draft files parse against `preflight-target-v1`; all changes pending |
| A5 | Review | accept/reject/edit persists; audit hash-chain verifies; source unchanged |
| A6 | Findings | 10 rules; precision ≥0.80/recall ≥0.70 on labelled corpus |
| A7 | Comparison | five classes unit-tested; no false `missing` on incomplete target |
| A8 | Evaluation | six metrics with numerator/denominator and caveat |
| A9 | Product | six primary screens; empty/error/partial states; no fake chrome |
| A10 | Live import | zip fixture runs end-to-end in <60s; re-run works |
| A11 | Scale | 5,000-file run completes with reported time/memory |
| A12 | Boundary | no live tenant; no Guidewire assets; disclaimers visible |
| A13 | Offline | after one-time setup, no network requests; Playwright route check |
| A14 | Claims linter | zero prohibited phrases/unverified IDs in UI/rules |

---

## 13. Demo (5 minutes)

| Time | Screen | Action | Message |
|---|---|---|---|
| 0:00 | Feature Spine cold open | Highlight `Motorcycle_Ext` in PCF/entity/product/API/test | “Week 5. The estimate just moved. One typelist value, 11 references, four artefact types, two tests. We find it before kickoff.” |
| 0:25 | Manifest / live import | Import 1,600-file snapshot; run <10s | “Read-only, hashed, offline. 4 unsupported files listed, not hidden.” |
| 1:05 | Features | Open PA-VEH-01; toggle gaps; click node | “PCF → entity → typelist → product → API → test. File, line, snippet. Territory has no source — that is a priced unknown.” |
| 2:05 | Reconstruction | Reject territory; accept year rename; show assumption + dependents | “Twelve dispositions, not a JSON dump. Rejection creates an assumption with owner, impact, and the question to ask. Source untouched.” |
| 3:05 | Findings | Show SQL, secret, hidden package, servlet; a deliberate `Query` negative; “Cloud Assurance: not run” | “Verified ID, verified policy, our heuristic — you can see which is which. We would rather be useful than sound official.” |
| 3:45 | Packet | Export review packet; show assumption register | “The output is a scope you can price, challenge, and sign.” |
| 4:30 | Grounded refusal | Ask “Does this estate use territory rating?” | “Cannot determine — no rating table. These three files would answer it.” |
| 4:50 | Close | Proof slide: holdout, precision/recall, 5k scale | “Every claim has evidence; every unknown has a name; every change waits for a human.” |

No fake 201, no official pass, no auto-pay, no 50 states, no live tenant.

---

## 14. Product content, claims, legal

- Footer + About disclaimer: independent research prototype; not affiliated/endorsed/certified by Guidewire; Guidewire, InsuranceSuite, PolicyCenter, ClaimCenter, BillingCenter, Gosu, APD, Jutro, Integration Gateway, Cloud Assurance, and Developer Assistants are trademarks of Guidewire Software, Inc.; all other trademarks belong to their owners; Source Sans 3 under SIL OFL; synthetic fixture, no customer data or confidential Guidewire information; findings are pattern-based heuristics, not official Cloud Standards checks; not legal/security/compliance advice.
- Claim legend in UI: Designed / Implemented / Measured / Proposed / Gated.
- Prohibited phrases linter: “Guidewire-certified”, “Cloud Assurance pass”, “APD converter”, “production-ready”, “100% detection”, “replaces Cloud Assurance”, “6–8 weeks → 5 minutes”, “first AI migration tool”, unverified IDs.
- AI disclosure: plan and reviews used AI assistance; the product's optional LLM is off by default; no customer code leaves the machine.

---

## 15. Delivery plan (2-person team, 14 days)

| Phase | Days | Output | Gate |
|---|---|---|---|
| P0 Plan re-review | 0.5 | v2 scorecard | All critics ≥8, no major gaps |
| P1 Tests + fixtures | 3 | Test suite, 1,500-file generator, holdout, ground truth | Tests fail for the right reasons |
| P2 Core pipeline | 4 | Intake, parsers, discovery, reconstruction | Unit/integration pass |
| P3 Review/compare/eval/assistant | 2 | Findings, comparison, metrics, grounded Q&A | Acceptance A1–A8 |
| P4 Product UI | 3 | Six screens, shell, states, demo seed | Playwright golden path |
| P5 Hardening + scale | 1 | Security, 5k scale, offline, claims linter | A9–A14 |
| P6 Independent verification | 1 | Critic scores + fixes | All ≥8 |
| P7 Demo package | 0.5 | Screenshots, packet, rehearsal | Demo works offline |

20% buffer included. Cut order: second LOB feature → assistant → SARIF → run comparison → packet PDF. Never cut: evidence, hashes, unsupported reporting, pending approvals, assumptions, denominators, disclaimers.

---

## 16. Deviations from the academic report

| Report | Product v2 | Rationale |
|---|---|---|
| Streamlit suggested | FastAPI + Jinja2 + vanilla JS | Product-grade shell, testable, no React build. |
| Three autonomous agents | Deterministic stages labelled Agent 1A/1B/2/3 | Testability, evidence discipline; “agent” is product language. |
| APD-shaped draft | Cloud API `_ext` extension draft | No public APD schema; documented target files are defensible. |
| “AI-powered” | Evidence-first + optional bounded narration | Demo is deterministic; no unverifiable AI claims. |
| 8 features in report | 12 main + 6 holdout | Evaluation needs a holdout. |
| Reviewer effort metric | Future work | No credible pilot in the build window. |
| Simulated frontend figures | Real screenshots + synthetic fixture labels | Required for integrity. |

---

## 17. Risks

| Risk | Mitigation |
|---|---|
| Fixture realism challenged | Fidelity appendix; public-doc mapping; label inventions; 2 LOBs; scale test. |
| Target format challenged | Documented `_ext` files; `docs/target-format.md`; “local, non-deployable”. |
| Mapping rules challenged | Provenance + reviewer approval; only documented example labelled `guidewire-doc`. |
| Findings seen as Sonar clone | Lead with cross-artefact evidence + assumptions + packet; only 10 checks. |
| Demo failure | Pre-seeded run + live import + backup screenshots; tmux; offline. |
| Overclaim | Claims ledger, claim-strength labels, disclaimers, linter. |
| Scope slip | Six screens; cut list; 20% buffer. |

---

## 18. Re-review protocol

Three independent critics (domain, product/architecture, evaluation/delivery) score v2 1–10 on:

1. Domain accuracy
2. Product/UX and demo
3. Technical feasibility
4. Evaluation rigor
5. Claims/legal/security
6. Delivery realism

**Pass:** every category ≥8, no major gap, at least two “BUILD” verdicts. If not, revise and re-review. Implementation starts only after `plans/04-critic-review-v2.md` records the scorecard.

---

## 19. Final positioning statement

> **PreFlight** is an offline, evidence-first cloud-readiness review product for Guidewire-style legacy estates. It assembles feature candidates across product models, PCF, entities, typelists, Gosu, and Cloud API configuration; links every claim to file/line evidence; surfaces documented blockers and evidence gaps; and produces a reviewable Cloud API extension draft plus a priced assumption register for one feature slice. It does not convert, certify, or deploy. Every claim has evidence; every unknown has a name; every change waits for a human.
