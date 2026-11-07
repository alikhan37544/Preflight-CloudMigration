# PreFlight — Build Handoff (post-planning, pre-implementation)

**Date:** 7 November 2026
**Repository:** `/home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration`
**Final plan:** `plans/05-plan-v5.md`
**Canonical claims ledger:** `docs/claims-ledger.json` (Markdown is generated)
**Target format:** `docs/target-format.md`
**Evaluation freeze:** `ground_truth/PRE_REGISTRATION.md`, `ground_truth/FROZEN.json`
**Security contract:** `docs/security.md`
**Feature edge expectations:** `ground_truth/pa_veh_01_edges.json`

---

## 1. What we are building

**PreFlight** — an offline, evidence-first cloud-readiness review **product** for Guidewire-style legacy insurance estates. It is not an APD converter, Cloud Assurance scorer, generic Gosu linter, live-tenant connector, or autonomous migration agent.

**Scenario:** Cloud Retrofit **without APD App** for a non-APD-native Personal Auto product. Source is pre-codegen: legacy product-model XML, extracted APD template XML, PCF, entity/typelist XML, Gosu, GUnit, `template_gen_config.xml`. Target is a **local, non-deployable Cloud API LOB extension draft**: `_ext` schema/mapping/updater, codegen config `pa_codegen_config_ext-1.0.yaml`, product access `pa_ext-1.0.yaml`.

**Headline:** “Find the estimate-moving surprises before kickoff.”
**Tagline:** “Every claim has evidence; every unknown has a name; every change waits for a human.”

---

## 2. Final product scope

### Six primary routes

1. `/` **Workbench** — snapshot header, feature list, SVG feature spine, evidence drawer, Grounded Assistant, gaps.
2. `/reconstruction` — Mappings, Draft & Diff, Assumptions, Comparison.
3. `/findings` — advisory findings + detail.
4. `/evaluation` — six headline metrics + supporting table.
5. `/packet` — six-page review packet + export + audit.
6. `/manifest` — full manifest, pagination, unsupported/corrupt/binary.

Secondary: `/about`, `/settings`, `/runs`.

### Golden path

Select synthetic project → live import `demo-slice-300` → manifest → Workbench feature `PA-VEH-01` → spine/evidence → reconstruction draft → accept/reject mappings → findings → assistant refusal → packet → evaluation.

### Feature slice PA-VEH-01

- Installed entity `PersonalVehicle.eti`: `ModelYear`, `Make`, `VIN`, `Usage`.
- Extension `PersonalVehicle.etx`: `GarageLocation_Ext`.
- Typelist `VehicleType.tti` + `config/extensions/typelist/VehicleType.ttx`: `Motorcycle_Ext`.
- PCF `PAVehicleDV.pcf`: `TypeKeyInput@VehicleType`, `TextInput@ModelYear`, `TextInput@GarageLocation_Ext`.
- Extracted template `product/template/PersonalAutoTemplate.xml`: `PAVehicle`, `Year`.
- Codegen draft `pa_codegen_config_ext-1.0.yaml`: `PAVehicle.nameOverride: PersonalVehicle`, `Year.nameOverride: ModelYear`, `GarageLocation.nameOverride: GarageLocation_Ext`, `PADriver -> VehicleDriver`, `PALine -> PersonalAutoLine`, long type `PersonalAutoRatingFactor -> PersonalAutoRatingFactorConfiguration`.
- Target `_ext` schema/mapping/updater + product access.
- Gosu validation is evidence-only; GUnit clean + DB-coupled test.
- Territory = explicit gap/assumption; rating inputs = unsupported.

### Mapping rules

`R-CG-01..04` (guidewire-doc), `R-GW-24-01` (guidewire-doc), `R-API-01..06` (preflight-convention), `R-TYP-01` (preflight-convention), `R-UNR-01`/`R-UNS-01` (reviewer-decision), `R-TEST-01`/`R-DOC-01` (preflight-convention). Demo set = 12 mappings.

### Review rules

`PF-GW-SQL-001` (IS-TLS-1238), `PF-GW-SEC-001` (SEC00-G), `PF-GW-PKG-001` (IS-TLS-1191), `PF-GW-EXC-001` (ERR00-G), `PF-GW-TX-001` (secondary blog), `PF-GW-SRV-001` (verified policy), `PF-GW-NAM-001` (verified doc, error), `PF-GW-GUNIT-001` (heuristic), `PF-GW-LOG-001/002` (heuristic thesis), `PF-GW-SBT-001` (readiness flag). Never invent `IS-*` IDs. Always show “Official Cloud Assurance: not run.”

---

## 3. Stack and architecture

- Python 3.12, FastAPI, Jinja2, vanilla JS/CSS.
- `lxml` for XML/PCF, `ruamel.yaml` for YAML line marks, stdlib `json` + JSON Pointer.
- Pydantic v2 models; JSON run store + SQLite index.
- pytest, httpx, Playwright.
- No React, Streamlit, ANTLR4, graph DB, vector DB, live tenant.
- Background job thread with state machine: `queued → running(stage) → succeeded|failed|cancelled`; progress weights; cancel; atomic writes; single worker.
- Source read-only; hash before/after; drafts under `data/runs/<run_id>/draft/`; all changes pending.
- Security: 127.0.0.1, Host/Origin allowlist, CSRF token, SameSite=Strict, Jinja autoescape, CSP, zip-slip/bomb protections, safe XML/YAML, secret redaction at capture, hash-chained audit, POST-only mutations.

### Planned module layout

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
      assistant.py
      llm.py
    templates/
    static/
  rules/{feature_rules,mapping_rules,review_rules}.yaml
  fixtures/acme-pc-2026.10/        # 1,500+ thesis / 600–800 demo
  fixtures/demo-slice-300/
  fixtures/northstar-pc-2026.10/   # holdout
  ground_truth/                     # features, edges, mappings, findings, reference target
  templates/target/
  tests/
  scripts/{generate_fixture.py,seed_demo.py,evaluate.py,claims_lint.py,verify_audit.py}
  docs/
```

---

## 4. Test-first build order

1. `tests/test_models.py` — Pydantic contracts, enums, schema versions.
2. `tests/test_intake.py` — hashing, classification, unsupported, zip safety.
3. `tests/test_parsers.py` — PCF/entity/typelist/product/config/Gosu.
4. `tests/test_discovery.py` — 8 features, evidence, confidence, gaps, holdout.
5. `tests/test_reconstruction.py` — 12 mappings, dispositions, draft, assumptions.
6. `tests/test_review.py` — 8 demo rules, hard negatives, claim strength.
7. `tests/test_compare.py` — five classes, reference target, no false missing.
8. `tests/test_evaluate.py` — M1–M6, baselines, denominators, caveats.
9. `tests/test_assistant.py` — 10 questions, citations, refusal.
10. `tests/test_api.py` — routes, CSRF, source immutability.
11. `tests/test_security.py` — zip/XXE/YAML/XSS/CSRF/audit/secrets.
12. `tests/test_e2e.py` — Playwright golden path, offline, screenshots.
13. `tests/test_claims_ledger.py` + `scripts/claims_lint.py` — JSON ledger, rule coverage.

Acceptance suite A1–A23 in `plans/05-plan-v5.md` §21. Tier: demo-critical first (600–800 files, 8 features, 8 rules, 12 mappings, M1–M6, 10-question assistant, 10 calendar days / 20 person-days).

---

## 5. UI direction

Guidewire-adjacent enterprise review workstation, original assets only:

- Top bar 56px `#1B2833`; context bar 40px; sidebar 240px/64px; status bar 28px.
- Canvas `#F6F8FA`; surface `#FFFFFF`; border `#D3DCE4`; text `#1F2D3A`; brand `#0B6B85`; focus `#1EB7DF`; evidence `#6B4FA1`.
- Source Sans 3 locally bundled (SIL OFL), fallback system; body 14/21; table 13/20; rows 40px; radius 4px.
- No gradients, glassmorphism, fake gauges, notification bell, avatar, or command palette.
- Feature spine: left-to-right columns PCF → entity → typelist → template/product → API draft → tests; deterministic layered SVG; click node → evidence drawer; table fallback.
- Every page: empty/loading/partial/error/success states; keyboard/focus; contrast; reduced motion.
- Packet: cover, executive summary, coverage/confidence, assumption register, findings, evidence/audit appendix. Print CSS. “Synthetic demo estate” and “not a quote” labels.

---

## 6. Demo

5-minute narrative in `plans/05-plan-v5.md` §10. Cold open on a 37-char Personal Auto type (`PersonalAutoRatingFactorConfiguration`) and `Motorcycle_Ext`; live 300-file import; spine; reconstruction; findings; grounded refusal (“no rating artefacts”); packet; measured demo-tier metrics; close on tagline. No fake 201, official pass, auto-pay, 50 states, live tenant.

---

## 7. Claims and legal guardrails

- Independent research prototype; not affiliated/endorsed/certified by Guidewire.
- Guidewire, InsuranceSuite, PolicyCenter, ClaimCenter, BillingCenter, Gosu, APD, Jutro, Integration Gateway, Cloud Assurance, Developer Assistants, Guidewire Cloud Platform, InsuranceNow are trademarks/registered trademarks of Guidewire Software, Inc.
- Synthetic fixture only; no customer data or confidential Guidewire information.
- Findings are pattern-based heuristics, not official Cloud Standards checks.
- No “Cloud Assurance pass/score,” “APD converter,” “production-ready,” “100% detection,” “six-figure,” “priced assumption register,” or invented `IS-*` IDs.
- Impact range is a heuristic planning range, not a quote.
- AI narration off by default; no customer code leaves the machine.

---

## 8. Current repository state

- Git repo initialized; no commits yet.
- Planning/research artifacts exist: `plans/`, `docs/`, `ground_truth/`.
- No application code, tests, fixtures, or UI yet.
- Python 3.12 venv at `.venv` with FastAPI, Uvicorn, Jinja2, Pydantic, lxml, PyYAML, pytest, httpx, python-multipart, Playwright.
- Playwright Chromium installed.
- `tmux` installed.
- The plan passed one independent domain BUILD; final contract consistency fixes were applied. Remaining work is implementation, not more planning.

---

## 9. Immediate next steps

1. Commit the planning baseline (`plans/`, `docs/`, `ground_truth/`) to Git.
2. Write `tests/test_models.py` and `tests/test_intake.py` first; run them and show failures.
3. Build `app/models.py`, `app/store.py`, `app/services/intake.py`; make those tests pass.
4. Build the fixture generator and `demo-slice-300`; generate `acme-pc-2026.10`, `northstar-pc-2026.10`, and `ground_truth` files.
5. Build parsers + discovery; make `test_parsers.py` and `test_discovery.py` pass.
6. Build reconstruction, review, compare, evaluate, assistant; make their tests pass.
7. Build FastAPI routes + Jinja2 shell + static assets; run `uvicorn` in tmux.
8. Seed demo run; run Playwright golden path; capture screenshots at 1440×900 and 1280×800.
9. Run `make demo` offline; run `scripts/claims_lint.py`, `pytest`, and `preflight verify-audit`.
10. Independent verifier agents review the running product; fix blockers; record scores.

---

## 10. Commands

```bash
cd /home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration
source .venv/bin/activate
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8000
tmux new -s preflight 'source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000'
python scripts/seed_demo.py
python scripts/evaluate.py
python scripts/claims_lint.py
.venv/bin/playwright test
```

**Definition of done:** fresh clone → `make demo` → server starts → golden path works offline; `pytest` passes; Playwright E2E passes; every screen has states; no source writes; evidence/assumption/audit/packet visible; demo impresses without overclaiming.
