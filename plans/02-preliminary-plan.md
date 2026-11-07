# PreFlight — Product & Implementation Plan (v1)

**Status:** Draft for independent critic review. Not approved for build until the scorecard in §18 is met.
**Date:** 7 November 2026
**Repo:** `/home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration`
**Working title:** PreFlight — Independent Cloud-Readiness Review for InsuranceSuite-Style Estates.

---

## 1. Executive summary

PreFlight is a **local-first, evidence-first review product** for legacy Guidewire-style insurance estates. It helps a migration team answer four questions before committing to an APD conversion or Cloud Retrofit engagement:

1. **What exists?** A manifest of every artefact, including files the tool cannot read.
2. **What does it implement?** A traceable feature inventory with file/line evidence and confidence labels.
3. **What will block or complicate migration?** Advisory, cited findings tied to public Guidewire guidance and documented failure modes.
4. **What could a target draft look like?** A reviewable, non-deployable draft for one selected feature, with explicit dispositions and assumptions.

The product is **not** an APD converter, Cloud Retrofit replacement, Cloud Assurance scorer, generic Gosu linter, or autonomous migration agent. It is a **read-only pre-conversion review workstation**: every claim links to evidence; every unknown is named; every change waits for a human.

**Core positioning sentence:** *Every mapping has a source; every unknown has a name; every change waits for a human.*

**Product form:** a polished, self-contained web application with a project workspace, run history, review workflow, exportable review packet, audit log, and demo mode. Not a bare API or notebook.

---

## 2. Verified domain facts and corrections

These facts drive scope. Claims marked **VERIFIED** have public primary sources; gated items are labelled.

| # | Fact | Status | Planning consequence |
|---|---|---|---|
| 1 | Guidewire cloud releases: Olos (Dec 2025), Palisades (Apr 2026), Qusar (Aug 2026, current as of Nov 2026); three releases/year; N−2 support. | VERIFIED | Never hard-code one release; pin release context per run. |
| 2 | APD conversion is a services-led Early Access offering, not a public self-service converter. Vendor estimate: 6–8 weeks for a monoline of average complexity, including testing. | VERIFIED as vendor claim | Do not claim to replace it or reproduce its output. |
| 3 | SBT lines could not be converted to APD-managed lines per the Olos release note. | VERIFIED for Olos | Treat SBT detection as a readiness flag, not a conversion attempt. |
| 4 | Cloud Retrofit is not APD conversion. It generates LOB-specific Cloud API endpoints; the APD-assisted path temporarily imports a product and deletes it afterward. | VERIFIED | Keep product-model readiness and API-endpoint readiness separate. |
| 5 | APD type-name limit is **24 characters**, not 30; truncation causes compile errors fixed with a `nameOverride` in codegen config. | VERIFIED | Implement a 24-character type-name warning. Remove the “30-char” claim from all material. |
| 6 | Public Cloud Standards IDs include `IS-TLS-1238` (direct SQL/JDBC), `IS-TLS-1022` (deprecated API usage), `IS-TLS-1191` (hidden package reference), `IS-INT-1335` (Integration Framework / custom servlets), `SEC00-G` (hard-coded secrets). `IS-INT-1268` has no public evidence. | VERIFIED titles/IDs; bodies gated | Use only verified IDs; label bodies gated; never cite `IS-INT-1268`. |
| 7 | `IS-SEC-1289` is the Gosu Secure Coding Standard document, not one rule. | VERIFIED | Do not use it as a single check. |
| 8 | Cloud Assurance is a TeamCity inspection gate using Studio inspections + Cloud Assurance Plugin; it marks PRs `NEEDS WORK` over a threshold; exact threshold and full rule corpus are gated. | VERIFIED process; GATED details | PreFlight findings are advisory only. Show “official Cloud Assurance: not run.” |
| 9 | SonarQube Enterprise already analyses Gosu. Generic Gosu linting is duplicative. | VERIFIED | Do not build a generic security scanner. Only documented, migration-blocking checks. |
| 10 | No public DEVHack 2026 page was found; DEVTrails 2026 is a university event with a gig-insurance theme. | VERIFIED absence; event status uncertain | Position for academic review and a generic product demo; do not claim a 2026 hackathon theme. |
| 11 | APD product/edition files are JSON/XML, not YAML; no public APD JSON schema was found. YAML is used for template/codegen config. | VERIFIED | Treat APD JSON as semi-structured; never claim official schema validation. |
| 12 | PCF is XML with a product-shipped XSD; no public canonical XSD was found. `.eti/.etx`, `.tti/.ttx` are XML metadata. Gosu has public EBNF and partial ANTLR/tree-sitter grammars, but no production-grade public Guidewire parser. | VERIFIED/LIKELY | Parse structures with `lxml`; use a comment/string-aware Gosu scanner, not a full parser. |
| 13 | TrainingApp, GO products, Marketplace content, and full Cloud Standards are proprietary/gated. Public docs are copyrighted; cite, don’t copy. | VERIFIED | Synthetic fixture only; no redistribution of Guidewire content. |
| 14 | Guidewire Developer Assistants for Gosu/Integrations/Jutro are GA in Qusar and use MCP; technical docs are gated. | VERIFIED | Do not plan an integration; position as complementary review evidence. |

---

## 3. Product definition

### 3.1 Personas

| Persona | Need | What PreFlight gives them |
|---|---|---|
| **Migration lead** | Understand scope and risk before an APD/Retrofit engagement | Estate summary, feature coverage, blockers, evidence gaps, exportable readiness brief. |
| **Guidewire developer** | Trace a business feature to PCF/Gosu/entity/product artefacts | Feature detail with file:line evidence, confidence, dependencies, open questions. |
| **Reviewer / architect** | Decide whether a proposed mapping is acceptable | Mapping table, draft diff, assumptions register, accept/reject/edit with audit trail. |
| **Academic evaluator** | Judge rigor and honesty | Claims ledger, fixture provenance, metric denominators, limitations, reproducibility. |

### 3.2 Product principles

1. **Evidence before generation.** Parsers and rules produce facts; the LLM (optional) only explains.
2. **Unknown is a valid output.** Unsupported files, unresolved references, and evidence gaps are visible.
3. **Human approval is structural.** Draft changes start `pending`; no auto-accept; no source writes.
4. **One primary action per view.** Dense, calm, enterprise UI.
5. **No live tenant.** Offline, synthetic, local-only by default.
6. **Claims carry status.** Designed / Implemented / Measured / Proposed / Gated.
7. **Product, not demo script.** Every screen has empty, loading, error, and partial states.

### 3.3 Differentiators

| # | Differentiator | Evidence |
|---|---|---|
| D1 | Offline, pre-engagement readiness pack with no tenant | Local-only architecture; synthetic fixture; read-only manifest. |
| D2 | Cross-artefact feature → evidence graph | PCF + entity + typelist + product model + Gosu + API schema links at file/line. |
| D3 | Assumption register and pending-by-default review | Data model + UI + audit trail. |
| D4 | Documented blocker detection with claim strength | Verified IDs/rules; heuristics clearly labelled. |
| D5 | Reproducible fixture benchmark | Ground truth, metrics, denominators, limitations. |

### 3.4 Non-goals

- APD conversion, Cloud API generation, Cloud Assurance pass/fail.
- Full Gosu parsing, type resolution, transpilation, or code generation.
- PCF→Jutro conversion.
- Live tenant connection, credential storage, third-party calls.
- 50-state product generation, legal advice, claims payment.
- Generic security scanning or “100% detection”.

---

## 4. Scope: the MVP vertical slice

### 4.1 Golden path

1. Open PreFlight → select the bundled synthetic project **Acme Personal Auto** (`acme-pc-2026.10`).
2. Run analysis → manifest lists every file, parser status, hash, and unsupported files.
3. Feature inventory shows **10 features**, each with evidence links and confidence.
4. Select **PA-VEH-01 — Vehicle Information**.
5. Generate a cloud reconstruction draft → mapping table, draft files, patch/diff, assumptions.
6. Review: accept one mapping, reject one ambiguous mapping, see the assumption register update.
7. Review findings: 6 advisory findings with rule IDs, evidence, severity, remediation, and claim strength.
8. Comparison: preserved / changed / missing / added / unresolved for the selected feature.
9. Evaluation: six metrics with denominators and “one synthetic fixture” caveat.
10. Export a review packet (JSON + HTML brief).

### 4.2 Feature slice

**PA-VEH-01 Vehicle Information** — deliberately small but cross-artefact:

| Source artefact | Example element | Target representation |
|---|---|---|
| `product/PersonalAuto.json` | risk object `PAVehicle`, attribute `VehicleType` | APD-shaped product draft |
| `editions/PersonalAuto-BaseEdition.json` | edition binding | edition draft |
| `.../Entity/Vehicle.eti` | `Year`, `Make`, `VIN`, `Usage` | target entity/schema fields |
| `.../extensions/entity/Vehicle.etx` | `GarageLocation_Ext` | `garageLocation` |
| `.../Typelist/VehicleType.tti` + `.ttx` | `Motorcycle_Ext` | target enum value `motorcycle` |
| `.../web/pcf/policy/PAVehicleDV.pcf` | `RangeInput@VehicleType`, `TextInput@Year` | UI/API field mapping |
| `.../gsrc/acme/validation/VehicleValidation.gs` | validation rule | evidence only; no Gosu rewrite |
| `.../integration/.../policyperiod_pa_ext-1.0.schema.json` | `vehicleType`, `garageLocation` | target schema draft |
| `.../codegen/pa_codegen_config_ext-1.0.yaml` | `nameOverride` entries | codegen draft |
| `.../gtest/.../*Test.gs` | pure unit test vs DB-coupled test | test inventory / finding |

### 4.3 Out of scope for the MVP

- Second LOB (keep as optional stretch).
- Real customer/tenant access.
- Agents 2 and 3 as autonomous LLM agents. They are implemented as deterministic review/comparison stages; UI calls them “Review” and “Comparison”.
- LLM narration in the critical path. The LLM adapter is optional and off by default.

---

## 5. User experience

### 5.1 Shell

- **Top bar (56px):** PreFlight mark, product name, snapshot selector, command search, offline badge, help, notification count, avatar.
- **Context bar (40px):** breadcrumb, read-only badge, release context, page actions.
- **Sidebar (240px / 64px collapsed):** Review (Dashboard, Manifest, Features, Reconstruction, Findings, Evaluation), Evidence (Sources, Assumptions, Gaps), Output (Review packet, Audit log), Settings, About.
- **Content canvas:** `#F6F8FA`, max width 1440px, 24–32px padding.
- **Status bar (28px):** snapshot hash, parser/rules version, offline status.

### 5.2 Design tokens (Guidewire-adjacent, original)

| Token | Value | Use |
|---|---|---|
| `--pf-chrome-900` | `#1B2833` | Top bar |
| `--pf-brand-700` | `#0B6B85` | Primary buttons, links |
| `--pf-focus` | `#1EB7DF` | Focus ring, active bar |
| `--pf-page` | `#F6F8FA` | Canvas |
| `--pf-surface` | `#FFFFFF` | Cards, tables |
| `--pf-border` | `#D3DCE4` | 1px borders |
| `--pf-text` | `#1F2D3A` | Primary text |
| `--pf-text-muted` | `#5B6F80` | Meta text |
| `--pf-success` | `#267A45` | Approved |
| `--pf-warning` | `#A05C00` | Gaps/warnings |
| `--pf-danger` | `#B3261E` | Blockers/rejections |
| `--pf-evidence` | `#6B4FA1` | Evidence/assumption accents |
| Radius | `4px` | All containers |
| Table row | `40px` | Data grids |
| Type | Source Sans 3, 14/21 body | Locally bundled; system fallback |

**No** gradients, glassmorphism, giant hero sections, fake gauges, or decorative charts. Border-first cards; shadows only for overlays/drawers.

### 5.3 Screens

| Route | Screen | Primary content | Key interactions |
|---|---|---|---|
| `/` | Dashboard | Readiness KPIs, pipeline stepper, attention list, recent activity | Open run, start review, export brief |
| `/manifest` | Manifest | Snapshot metadata, file table, unsupported files, parser warnings | Filter, inspect file, verify checksum |
| `/features` | Feature Inventory | Feature table with LOB, evidence count, confidence, gaps | Filter, open feature |
| `/features/{id}` | Feature Detail | Summary band, evidence list, dependencies, open questions | Open evidence drawer, request draft |
| `/reconstruction` | Reconstruction | Mapping table, draft files, diff viewer, assumptions | Generate draft, accept/reject mapping, download patch |
| `/findings` | Findings | Advisory findings table, filter by severity/rule | Open finding, view evidence, record decision |
| `/comparison` | Comparison | Classification summary + table; gated if no target | Filter, inspect two-sided evidence |
| `/evaluation` | Evaluation | Six metric cards, metric table, fixture provenance, caveats | Export metrics, view methodology |
| `/runs` | Runs | Run history with status, snapshot, date, operator | Open run, compare runs |
| `/settings` | Settings | Release context, rule pack, parser options, data policy | Save settings (local) |
| `/about` | About / Boundaries | Product statement, disclaimers, claim legend | Read only |

### 5.4 UX states

- **Empty:** no snapshot → “Import a snapshot” + “Open sample project”.
- **Loading:** skeleton rows + “Analysing artefacts…”.
- **Partial:** amber banner “3 files could not be parsed; results exclude them.”
- **Error:** scoped error panel with code, retry, and a link to the run log.
- **Success:** green “Review complete” banner; export action.

### 5.5 Visual evidence

- Every feature/finding row shows an **evidence count** and confidence chip.
- Clicking opens a right-side **evidence drawer** (440px): path, line, XPath/JSON Pointer, snippet, extractor, confidence.
- The drawer never replaces the page; the record stays visible.
- Draft diff uses a two-column unified diff with line numbers and rule badges.
- Assumptions are purple-accented; gaps are amber; blockers are red; approved is green.

---

## 6. Architecture

### 6.1 Stack decision

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 | Team skill; ecosystem; stable. |
| Web framework | FastAPI | Small, typed, fast; Jinja2 templates + JSON APIs. |
| Templates | Jinja2 | Server-rendered product shell; no React build. |
| Frontend | Vanilla JS + CSS | Full control, minimal build; product-grade shell. |
| XML | `lxml` | XPath, line numbers, safe parser options. |
| JSON/YAML | stdlib `json`, `PyYAML`/`ruamel` | Contracts, config, rules. |
| Models | Pydantic v2 | Schema validation and JSON contracts. |
| Store | JSON run directories + SQLite index | Reproducible, inspectable, no server DB. |
| Tests | `pytest`, `httpx`, Playwright | Unit, API, E2E. |
| Packaging | `pyproject.toml`, `Makefile`, `preflight` CLI | Product runnable with one command. |

**Rejected:** Streamlit (UI ceiling, hard to mimic enterprise shell), React (build/coordination overhead), ANTLR4 (multi-week trap), graph DB, vector DB, LangGraph, live tenant adapters.

### 6.2 Module layout

```text
preflight/
├── app/
│   ├── main.py                 # FastAPI app factory, routes
│   ├── config.py               # paths, versions, constants
│   ├── models.py               # Pydantic contracts
│   ├── store.py                # run/project storage
│   ├── security.py             # zip safety, path guards
│   ├── services/
│   │   ├── intake.py           # snapshot -> manifest
│   │   ├── parsers/
│   │   │   ├── base.py
│   │   │   ├── pcf.py
│   │   │   ├── entity.py
│   │   │   ├── product.py
│   │   │   ├── config.py
│   │   │   └── gosu.py
│   │   ├── discovery.py        # feature assembly + evidence graph
│   │   ├── reconstruction.py   # mapping rules + draft writer
│   │   ├── review.py           # advisory rule engine
│   │   ├── compare.py          # source vs draft classification
│   │   ├── evaluate.py         # ground-truth metrics
│   │   └── llm.py              # optional NullLLM adapter
│   ├── templates/
│   └── static/
├── rules/
│   ├── feature_rules.yaml
│   ├── mapping_rules.yaml
│   └── review_rules.yaml
├── fixtures/acme-pc-2026.10/   # synthetic Guidewire-style project
├── ground_truth/               # expected features/mappings/findings
├── templates/target/           # target skeleton for draft generation
├── tests/
├── scripts/seed_demo.py
├── pyproject.toml
├── Makefile
└── README.md
```

### 6.3 Pipeline

```text
Snapshot
  → Intake (manifest, hashes, classification, unsupported)
  → Parse (PCF/Entity/Typelist/Product/YAML/Gosu)
  → Discover (feature seeds, evidence links, confidence, gaps)
  → Review (deterministic advisory rules)
  → Reconstruct (selected feature, mapping rules, draft, diff, assumptions)
  → Compare (source properties vs draft properties)
  → Evaluate (ground truth metrics)
  → Review packet (JSON + HTML)
```

Every stage writes a JSON artifact under `data/runs/<run_id>/`. The UI reads artifacts only; it never re-parses source files.

### 6.4 Data model (Pydantic)

| Record | Required fields |
|---|---|
| `Run` | `run_id`, `project_id`, `snapshot_hash`, `created_at`, `status`, `release_context`, `rulepack_version`, `stages` |
| `Artifact` | `path`, `sha256`, `size`, `kind`, `parser`, `status`, `warnings`, `line_count` |
| `Evidence` | `evidence_id`, `path`, `start_line`, `end_line`, `xpath`, `json_pointer`, `yaml_path`, `snippet_sha`, `excerpt`, `method`, `confidence` |
| `Feature` | `feature_id`, `name`, `lob`, `description`, `evidence_ids`, `dependencies`, `confidence`, `open_questions` |
| `Mapping` | `mapping_id`, `source_ref`, `source_name`, `source_type`, `target_path`, `target_name`, `disposition`, `rule_id`, `confidence`, `rationale` |
| `Change` | `change_id`, `target_path`, `diff`, `mapping_id`, `approval_state`, `reviewer`, `reviewed_at` |
| `Assumption` | `assumption_id`, `statement`, `impact`, `status`, `owner`, `related_mapping_id` |
| `Finding` | `finding_id`, `rule_id`, `title`, `severity`, `confidence`, `claim_strength`, `evidence_ids`, `message`, `remediation`, `decision` |
| `Metric` | `metric_id`, `label`, `value`, `numerator`, `denominator`, `unit`, `caveat` |

### 6.5 Persistence

```text
data/
├── projects.json
├── runs/
│   └── R-2026-11-07-001/
│       ├── manifest.json
│       ├── features.json
│       ├── findings.json
│       ├── mapping.json
│       ├── changes.json
│       ├── assumptions.json
│       ├── comparison.json
│       ├── metrics.json
│       ├── decisions.json
│       ├── audit.jsonl
│       ├── draft/
│       └── review_packet.html
└── fixtures/ (copied/read-only)
```

### 6.6 Security

- Source snapshot mounted read-only; hash before/after; source writes are a hard failure.
- Zip ingestion: reject absolute paths, `..`, symlinks, NUL, drive letters; size/ratio limits; extract to random temp; no execution.
- XML: `resolve_entities=False`, `no_network=True`, `load_dtd=False`, `huge_tree=False`; parser errors become warnings.
- YAML: `safe_load`.
- No network calls by default; optional LLM adapter off.
- No secrets/PII in logs; redact secret values.
- CSRF not required for local single-user product; document the boundary.
- Path traversal guard on every artifact read.

---

## 7. Discovery design

### 7.1 Parsers

| Parser | Input | Output | MVP? |
|---|---|---|---|
| Inventory | all files | path, hash, size, kind, status | Yes |
| PCF | `.pcf` XML | screens, widgets, IDs, XPath, line | Yes |
| Entity | `.eti/.etx` XML | entities, columns, relationships, extensions | Yes |
| Typelist | `.tti/.ttx` XML | typelist codes/categories | Yes |
| Product | `product/*.json`, `editions/*.json` | recursive product elements, JSON Pointer | Yes |
| Config | `.yaml` | codegen/template keys, TODO markers | Yes |
| Gosu scanner | `.gs/.gsx` | package, imports, declarations, call candidates, strings/comments masked | Yes |
| GUnit | test `.gs` | test class/method, DB-coupling signals | Yes |
| Unsupported | binary/unknown | explicit `unsupported` warning | Yes |
| XSD validation | optional | local only; never claim official | Deferred |

### 7.2 Feature assembly

- Feature rules in `rules/feature_rules.yaml` map a **seed artifact pattern** (e.g., PCF screen `PAVehicleDV`) to a feature name, LOB, and link keys.
- Link keys (`vehicle`, `driver`, `coverage`) match entity names, product elements, typelist names, Gosu symbols, and API schema properties.
- Each link becomes an `Evidence` record with exact path/line/XPath/JSON Pointer.
- Confidence:
  - `parsed` — direct file fact;
  - `linked` — explicit identifier reference;
  - `inferred-review` — naming/co-location only;
  - `unresolved` — evidence gap.
- No feature is emitted without at least one parsed anchor.
- Unsupported files are listed in the manifest, never silently dropped.

### 7.3 Evidence graph

For the MVP, the graph is an adjacency structure persisted in `features.json`:

- nodes: feature, artifact, symbol, config key;
- edges: `contains`, `declares`, `references`, `configures`, `implements`;
- every edge carries `evidence_id`, `confidence`, and `rule_id`.

No graph database; NetworkX optional for analysis only.

---

## 8. Reconstruction design

### 8.1 Mapping rules

`rules/mapping_rules.yaml` entries:

```yaml
- id: R-APD-01
  description: Strip _Ext suffix from custom entity fields
  source: {kind: entity_field, match: ".*_Ext$"}
  target: {path: "entity/{name_without_ext}", transform: camelCase}
  disposition: mapped_transformed
  confidence: high
  citation: "Guidewire custom entity _Ext convention (public glossary)"
```

MVP rules (10):

| Rule | Source | Target / disposition |
|---|---|---|
| R-APD-01 | `GarageLocation_Ext` | `garageLocation` (renamed) |
| R-APD-02 | typelist `Motorcycle_Ext` | `motorcycle` (renamed) |
| R-APD-03 | PCF `RangeInput@VehicleType` | `vehicleType` (mapped) |
| R-APD-04 | product attribute `VehicleType` | `vehicleType` (mapped) |
| R-APD-05 | `Vehicle.year` | `modelYear` (renamed, documented naming) |
| R-APD-06 | codegen `PAVehicle` | `PersonalVehicle` nameOverride |
| R-APD-07 | `Vehicle.territory` | `needs_decision` (unresolved) |
| R-APD-08 | rating inputs | `unsupported` (out of scope) |
| R-CG-01 | template config TODO | `needs_decision` |
| R-API-01 | API schema field | `preserved` |

### 8.2 Draft writer

- Reads a **target skeleton** from `templates/target/` (synthetic, non-deployable).
- Applies mapping rules to the selected feature’s source properties.
- Writes draft files under `data/runs/<id>/draft/` only.
- Produces `mapping.json`, `changes.json`, `assumptions.json`, `patch.diff`.
- Uses Jinja2 for text templates and JSON manipulation for structured files.
- Never overwrites source; every change starts `pending`.

### 8.3 Assumptions

- Any `needs_decision` or `unsupported` disposition creates an assumption.
- Any missing evidence (e.g., territory source, rating table, vendor contract) creates an assumption.
- Assumptions have impact (`high|medium|low`), owner (`unassigned`), status (`open|resolved|rejected`).
- The UI shows the assumptions register beside the draft; unresolved assumptions block “approved as verified”.

---

## 9. Review (Agent 2, deterministic)

### 9.1 Rule catalog (MVP)

| Rule | Check | Claim strength | Severity | Detection |
|---|---|---|---|---|
| `PF-GW-SQL-001` | Direct JDBC/SQL | Verified ID: `IS-TLS-1238` | error | Masked-source regex for `java.sql`, `DriverManager`, `createStatement`, `prepareStatement`; negative for `gw.api.database.Query`. |
| `PF-GW-SEC-001` | Hard-coded secret | Verified ID: `SEC00-G` / `IS-SEC-1332` | error | Key/value patterns; redact value; placeholders allowlisted. |
| `PF-GW-PKG-001` | Hidden/internal package | Verified ID: `IS-TLS-1191` | error | `gw.internal.*`, `com.guidewire.*`; allow `gw.api.*`, `gw.pl.*`. |
| `PF-GW-SRV-001` | Custom servlet | Verified ID: `IS-INT-1335` | warning | `HttpServlet`, `javax.servlet`, `@WebServlet`, `web.xml` `<servlet>`. |
| `PF-GW-TX-001` | Explicit commit in `runWithNewBundle` | Secondary (Guidewire developer blog) | warning | Brace-matched block containing `.commit()`. |
| `PF-GW-LOG-001` | PII/credential in logs | Verified policy (`IS-SEC-1008` / `IS-IMP-1017`, gated) | warning | Sensitive field names in log calls. |
| `PF-GW-LOG-002` | `print` / `printStackTrace` | Verified policy (hardening) | warning | `print(`, `System.out`, `printStackTrace`. |
| `PF-GW-EXC-001` | Swallowed exception | Verified ID: `ERR00-G` | warning | Empty/comment-only catch block. |
| `PF-GW-GUNIT-001` | DB access in pure unit test | Verified policy (unit-test guidance) | warning | `*UnitTestClassBase` + `Query.make`/`commit`/`loadSampleData`. |
| `PF-GW-NAM-001` | APD type name >24 chars | Verified public doc | warning | Product/entity type names; suggest `nameOverride`. |

### 9.2 Claim-strength discipline

Every finding carries `claim_strength`:

- `verified-id` — exact public Guidewire ID + title; body may be gated.
- `verified-policy` — public Guidewire guidance, no single public ID.
- `secondary` — Guidewire/vendor blog, no public standard.
- `heuristic` — PreFlight invention; must be labelled.

The UI shows the label beside every finding. No finding says “Cloud Assurance violation”.

### 9.3 Output

- Findings persisted in `findings.json`.
- Each finding includes evidence IDs, severity, remediation, rule version, claim strength.
- Reviewer decisions: `open`, `accepted`, `rejected`, `deferred`.
- Optional SARIF 2.1.0 export (deferred if time; not required for MVP).

---

## 10. Comparison (Agent 3, deterministic)

For the selected feature, compare **discovered source properties** to **draft target properties**:

| Class | Definition | Example |
|---|---|---|
| `preserved` | Same semantics, same or equivalent name | `VIN` → `vin` |
| `changed` | Intentional rename/type change with rule + evidence | `year` → `modelYear` |
| `missing` | Source property has no target and no disposition | (should be zero) |
| `added` | Target property has no source counterpart | `auditVersion` |
| `unresolved` | Cannot decide due to missing evidence | `territory` |

Rules:
- `missing` requires a complete target scope; otherwise `unresolved`.
- `preserved` requires positive evidence; name similarity alone is not enough.
- Every comparison row links to source and target evidence.

This is a real implementation, not a gated placeholder. It demonstrates the architecture’s third agent on the one feature slice.

---

## 11. Evaluation

### 11.1 Fixture

`fixtures/acme-pc-2026.10` — synthetic, legally clean, 120–180 files, with:
- 10 labelled features;
- 40+ evidence links;
- 12+ mappings;
- 8+ planted findings;
- 3 deliberate gaps;
- 2 ambiguities;
- 1 unsupported binary file;
- clean negatives for every rule.

Ground truth in `ground_truth/`:
- `features.json`, `evidence.json`, `mappings.json`, `findings.json`, `ambiguities.json`.
- Hash of the fixture and version.

### 11.2 Metrics (six)

| Metric | Definition | Denominator |
|---|---|---|
| Feature discovery coverage | Found gold features / all gold features | 10 |
| Evidence-link accuracy | Reported links that resolve and support the claim / all reported links | reported links |
| Mapping disposition coverage | Source properties with an explicit disposition / all source properties | source properties |
| Silent omission rate | Fields with no disposition / source properties | source properties |
| Draft structural validity | Draft files parse against local schema / draft files | draft files |
| Reviewer effort | Median time to review a fixed task with/without PreFlight | pilot n |

The UI shows numerator/denominator and a caveat: “One synthetic fixture; demonstration, not a benchmark. Agents 2/3 advisory. No live tenant.”

### 11.3 Evaluation run

`scripts/evaluate.py` loads ground truth, runs the pipeline on the fixture, computes metrics, writes `metrics.json`. Tests assert:
- feature coverage ≥ 0.8;
- evidence links resolve 100%;
- disposition coverage = 100%;
- silent omissions = 0;
- structural validity = 100%.

---

## 12. Test-first plan

### 12.1 Order

1. `tests/test_models.py` — contracts, validation, serialization.
2. `tests/test_intake.py` — hashing, classification, unsupported files, zip safety.
3. `tests/test_parsers.py` — PCF, entity, typelist, product, config, Gosu scanner.
4. `tests/test_discovery.py` — features, evidence, confidence, gaps.
5. `tests/test_reconstruction.py` — mapping rules, dispositions, draft, assumptions.
6. `tests/test_review.py` — rule detections, false positives, claim strength.
7. `tests/test_compare.py` — preserved/changed/missing/added/unresolved.
8. `tests/test_evaluate.py` — metrics and denominators.
9. `tests/test_api.py` — FastAPI routes, JSON contracts, source immutability.
10. `tests/test_e2e.py` — Playwright golden path, offline, screenshots.

### 12.2 Acceptance tests (MVP)

| ID | Test | Pass condition |
|---|---|---|
| A1 | Manifest completeness | 100% files listed and hashed; 0 source writes |
| A2 | Discovery | ≥8/10 features; every evidence link resolves to file + line |
| A3 | Mapping | 100% source properties have a disposition; 0 silent omissions |
| A4 | Draft | 100% draft files parse against local schema; diff exists; all changes pending |
| A5 | Review | Accept/reject persists; source hash unchanged; audit log appended |
| A6 | Findings | Each finding has rule ID, claim strength, evidence, remediation |
| A7 | Comparison | All five classes present; no `missing` without complete target scope |
| A8 | Evaluation | Six metrics with numerator/denominator; caveat visible |
| A9 | Product | All routes render; empty/error/partial states present; no dead links |
| A10 | Reproducibility | `make demo` from fresh clone offline in <5 minutes |
| A11 | Boundary | No live tenant, no Guidewire assets, disclaimers visible |

### 12.3 E2E Playwright checks

- Open dashboard → KPI cards visible.
- Navigate to manifest → unsupported file visible.
- Open feature inventory → 10 features; open PA-VEH-01.
- Generate draft → mapping table + diff.
- Accept one mapping, reject one → status persists.
- Open findings → 6+ rows; claim-strength label visible.
- Open evaluation → six metrics and caveat.
- Screenshot each screen at 1440×900 and 1280×800.
- Confirm no external network requests (route interception) and no console errors.

---

## 13. Demo

### 13.1 5-minute judge demo

| Time | Screen | Action | Message |
|---|---|---|---|
| 0:00 | Dashboard | Show snapshot hash, offline badge | “This is an offline review of a synthetic Guidewire-style policy administration estate. No tenant, no customer data.” |
| 0:20 | Manifest | Filter unsupported | “128 files hashed; 4 unsupported and visible — not silently skipped.” |
| 0:50 | Features | Open PA-VEH-01 | “10 features; every one traces to file and line. Parsed, linked, and inferred are different.” |
| 1:30 | Feature detail | Open evidence drawer | “This field is in PCF, entity, product model, typelist, and API schema. One click shows the source.” |
| 2:10 | Reconstruction | Generate draft | “Ten mapping rules; every source property gets an explicit disposition. Unknowns become assumptions.” |
| 3:00 | Review | Reject territory mapping, accept year rename | “Pending by default. Rejection creates a visible assumption; approval is audited; source is unchanged.” |
| 3:40 | Findings | Show SQL, secret, hidden package, servlet | “These are advisory, with verified public standard IDs where they exist — never an official Cloud Assurance result.” |
| 4:20 | Evaluation | Show six metrics | “Six metrics with denominators on one synthetic fixture. Not a benchmark; the method is the contribution.” |
| 4:40 | Close | Review packet | “Every mapping has a source; every unknown has a name; every change waits for a human.” |

### 13.2 Demo safeguards

- Pre-seeded run `R-DEMO-001`; no live parsing during the demo unless it takes <5s.
- Offline; no CDN; no external fonts; no telemetry.
- Backup video/screenshots.
- Two browsers; server in tmux; health check.
- One live action: accept/reject a mapping.
- No fake “201 Created”, “CAA passed”, or “APD converted”.

---

## 14. Product content and claims

### 14.1 Required disclaimers

Visible in the footer and About page:

> PreFlight is an independent academic research prototype. It is not affiliated with, endorsed by, sponsored by, or certified by Guidewire Software, Inc. Guidewire, InsuranceSuite, PolicyCenter, ClaimCenter, BillingCenter, Gosu, Advanced Product Designer (APD), and Cloud Assurance are trademarks or registered trademarks of Guidewire Software, Inc. PreFlight does not perform Guidewire Cloud Assurance, does not replace Guidewire tools or services, and does not generate deployable Guidewire Cloud artefacts. All outputs are draft suggestions requiring human review and validation in an authorised environment.

### 14.2 Claim legend

| Status | Meaning | Allowed wording |
|---|---|---|
| Designed | Architecture exists | “We designed…” |
| Implemented | Code runs on the fixture | “The prototype executes…” |
| Measured | Metrics on controlled fixtures | “Measured on one synthetic fixture…” |
| Proposed | Future work | “Planned…” |
| Gated | Requires external access | “Gated on…” |

### 14.3 Prohibited claims

- “Guidewire-certified/approved/official.”
- “Cloud Assurance pass/score.”
- “APD converter / Cloud Retrofit replacement.”
- “Production-ready / deployable / migration-ready.”
- “100% detection / zero false positives.”
- “6–8 weeks → 5 minutes.”
- Invented `IS-xxx` IDs or rule text.
- “First AI migration tool.”

---

## 15. Delivery plan

| Phase | Days | Output | Gate |
|---|---|---|---|
| P0 Plan vetting | 1 | This plan + critic scorecard | All critics ≥8/10; no major gaps |
| P1 Test contracts | 1 | Test suite skeleton + fixtures + ground truth | Tests fail for the right reasons |
| P2 Core pipeline | 3 | Intake, parsers, discovery, reconstruction | Unit/integration tests pass |
| P3 Review/compare/eval | 2 | Findings, comparison, metrics | Acceptance tests pass |
| P4 Product UI | 3 | All routes, shell, states, demo seed | Playwright golden path passes |
| P5 Hardening | 1 | Security, empty/error states, fresh-clone test | `make demo` offline <5 min |
| P6 Independent verification | 1 | Critic/verifier scorecards + fixes | All ≥8/10 |
| P7 Demo package | 1 | Screenshots, video script, review packet | Final demo rehearsal |

### 15.1 Definition of done

- Fresh clone → `make demo` → server starts in tmux → golden path works offline.
- `pytest` passes with ≥90% core coverage.
- Playwright E2E passes at 1440×900 and 1280×800.
- Every screen has empty/error/partial state.
- No source writes; hash verification passes.
- Claims ledger and disclaimers updated.
- Independent critics score ≥8/10 on domain, product, rigor, and delivery.

---

## 16. Risks and cut list

| Risk | Impact | Mitigation |
|---|---|---|
| Fixture too synthetic | Reviewers question realism | Base on public docs; label assumptions; include messy files and gaps. |
| Parser complexity | Slips schedule | Limit to 6 formats; lxml + scanner; no full AST. |
| UI polish consumes time | Core not finished | Build shell early; reuse components; cut animations, not evidence. |
| Reviewer sees “yet another linter” | Low score | Lead with evidence graph, dispositions, assumptions, review workflow. |
| Claims overreach | Legal/academic risk | Claim legend, disclaimers, verified IDs only, no official status. |
| Demo failure | Bad judge experience | Pre-seeded run, offline, backup screenshots/video, tmux health check. |
| Too many screens | Incomplete states | Seven core routes; no extra tabs. |

**Cut order:** second LOB → SARIF export → LLM narration → command palette → run comparison → optional animations. **Never cut:** evidence links, hashes, unsupported reporting, pending approvals, assumptions, evaluation denominators, disclaimers.

---

## 17. Independent critic review protocol

Before implementation, three independent critics review this plan and score it 1–10 on:

1. **Domain accuracy** — Guidewire facts, scope, claims.
2. **Product/UX quality** — product form, workflow, demo.
3. **Technical feasibility** — stack, parsers, data model, tests.
4. **Evaluation rigor** — metrics, ground truth, limitations.
5. **Risk/legal/claims** — disclaimers, data, academic integrity.
6. **Delivery realism** — milestones, cut list, definition of done.

**Pass condition:** every category ≥8/10, no “major gap”, and at least two critics say “build”. If any category <8 or a major gap is found, revise the plan and re-review.

**Implementation may start only after the scorecard is recorded in `plans/03-critic-review.md` and the final plan is updated.**

---

## 18. Critic scorecard template

| Critic | Domain | Product | Feasibility | Evaluation | Risk | Delivery | Verdict | Major gaps |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Critic A — Guidewire domain | | | | | | | | |
| Critic B — Product/architecture | | | | | | | | |
| Critic C — Evaluation/delivery | | | | | | | | |

---

## 19. Final positioning statement

> **PreFlight** is an offline, evidence-first cloud-readiness review product for Guidewire-style legacy estates. It discovers business features across product models, PCF, entities, typelists, Gosu, and API configuration; links every claim to a source artefact; surfaces documented blockers and evidence gaps; and produces a reviewable draft for one feature slice. It does not convert, certify, or deploy. Every mapping has a source; every unknown has a name; every change waits for a human.
