# PreFlight — five-minute live demo runbook

**Run:** `R-DEMO-001` · fixture `demo-slice-300` (300 synthetic files) · feature `PA-VEH-01` Vehicle Information.
**Deck:** `docs/presentation/index.html` (served at `http://127.0.0.1:8090/index.html`).
**Seed state:** 12 pending mappings · 3 assumptions · 9 audit events · 24 advisory findings · 126 evidence items.
**After the two scripted actions:** Accept M-01 + Reject M-12 → 11 audit events · 4 assumptions · A-DEC-04.
**Boundaries to say out loud:** independent research prototype; synthetic estate; not affiliated with Guidewire; official Cloud Assurance was **not** run; the draft targets Cloud Retrofit without APD App and is local and non-deployable.

---

## 0. Setup (do this before the room is seated)

From the repository root:

```bash
make demo
```

This generates fixtures, re-seeds `R-DEMO-001`, and starts Uvicorn inside tmux session `preflight`. Wait for it, then check:

```bash
curl -s http://127.0.0.1:8000/api/health
# {"status":"ok","version":"0.1.0"}

curl -s http://127.0.0.1:8000/api/runs/R-DEMO-001/status
```

Attach to the server only if you need to watch logs:

```bash
tmux attach -t preflight
# detach: Ctrl+b, then d
```

Do **not** press `Ctrl+C` in the tmux pane during the talk; the wrapper restarts after two seconds. To stop deliberately:

```bash
make stop
```

If you need a foreground server instead:

```bash
make demo-fg
```

### Browser setup

- Open `http://127.0.0.1:8000/?run=R-DEMO-001&feature=PA-VEH-01`.
- Use 1440 × 900 or 1280 × 720/900 at 100% zoom. The Findings page is supported at 1280; use 1440 when you want the detail panel and table side by side.
- Reconstruction at 1280 × 720 keeps every column but the mapping table is horizontally scrollable; use 1440 × 900 if you want the decision column and M-12 fully visible without scrolling. M-12 is below the fold even at 1440.
- Hide bookmarks/devtools/notifications. Use full screen.
- Keep the deck open in a second tab: `http://127.0.0.1:8090/index.html`.
- Start with **12 pending mappings, 3 assumptions, and 9 audit events**. `make demo` resets them. Do not accept/reject before the talk unless you are rehearsing on a throwaway copy.

### Backup kit

| Backup | Path / command |
|---|---|
| Application screenshots | `docs/presentation/assets/*.png` |
| Historical packet snapshot | `docs/demo/preflight-review-packet.html` |
| Live packet copy | `cp data/runs/R-DEMO-001/packet.html /tmp/opencode/R-DEMO-001-packet.html` |
| Deck | `docs/presentation/index.html`; serve with `python -m http.server 8090 -d docs/presentation` |
| Freeze verification | `make freeze` (do not run during the talk) |
| Packet verification | `preflight verify-packet R-DEMO-001` or `python -m app.cli verify-packet R-DEMO-001` |
| Audit verification | `preflight verify-audit R-DEMO-001` or `python -m app.cli verify-audit R-DEMO-001` |

**Important:** the bundled `docs/demo/preflight-review-packet.html` is a **historical snapshot**, not the live run. Its packet hash and audit head will not match a freshly seeded run. Do not run `verify-packet` or `verify-audit` against it. If you show it as a fallback, say “this is a historical example from the same build, not today’s run.”

### Exact URLs

| Screen | URL |
|---|---|
| Workbench / PA-VEH-01 | `http://127.0.0.1:8000/?run=R-DEMO-001&feature=PA-VEH-01` |
| Evidence direct link | `http://127.0.0.1:8000/?run=R-DEMO-001&feature=PA-VEH-01&evidence=EV-0001` |
| Manifest excluded filter | `http://127.0.0.1:8000/manifest?run=R-DEMO-001&excluded=1` |
| Reconstruction | `http://127.0.0.1:8000/reconstruction?run=R-DEMO-001` |
| Reconstruction assumptions | `http://127.0.0.1:8000/reconstruction?run=R-DEMO-001&tab=assumptions` |
| Findings | `http://127.0.0.1:8000/findings?run=R-DEMO-001` |
| Evaluation | `http://127.0.0.1:8000/evaluation?run=R-DEMO-001` |
| Review packet | `http://127.0.0.1:8000/packet?run=R-DEMO-001` |
| Packet download | `http://127.0.0.1:8000/packet/export?run=R-DEMO-001` |
| Audit JSON | `http://127.0.0.1:8000/api/runs/R-DEMO-001/audit` |
| Health | `http://127.0.0.1:8000/api/health` |

---

## 1. The five-minute click script

The clock is approximate. The demo is deliberately not a feature tour; every click answers one of the four questions: what exists, which feature, what is disposed, what is unknown.

### 0:00 — Workbench cold open (35 s)

**Open:** `http://127.0.0.1:8000/?run=R-DEMO-001&feature=PA-VEH-01`

Say:

> “This is an offline review of a synthetic Guidewire-style Personal Auto estate. 300 files, hashed and read-only. No tenant, no customer data. Official Cloud Assurance was not run.”

Point at the **summary strip**:

> “31 evidence records, 12 distinct files, four artefact types, two tests, and 11 references for PA-VEH-01. Separately, a 37-character type is a PA-VEH-02 dependency: it appears in two files — the template and the product model — and is not one of those 11 references. Three gaps are estate-wide.”

Point at the **feature spine**:

> “One feature traced across PCF, installed entity, typelist, extracted template, Gosu, and tests. The 37 vs 24 signal is separate from PA-VEH-01’s 11 references: the long type is carried by two files and is a PA-VEH-02 dependency.”

**Click a spine node** (for example the leftmost `PAVehicleDV` node). The inline **Selected node evidence** panel appears above the graph; the full evidence drawer is below the fold.

> “EV-0001. PCF path, xpath, line 4, excerpt, method `xml_xpath`, excerpt SHA-256. Every highlighted evidence-bearing node resolves to a file and a locator.”

If the inline panel does not appear, open the direct evidence URL shown above. Do not scroll-hunt on stage.

### 0:35 — Manifest / no silent omission (25 s)

**Open:** `http://127.0.0.1:8000/manifest?run=R-DEMO-001&excluded=1`

Point at the banner and the four rows:

> “Four excluded files, named with reasons: two binary assets, one corrupt PCF, one unsupported CSV. The source snapshot hash is identical before and after. No silent omission.”

If demonstrating the filter manually: **Manifest → tick Excluded (4) → Apply**. The checkbox alone does not refresh the table.

### 1:00 — Reconstruction decision queue (55 s)

**Open:** `http://127.0.0.1:8000/reconstruction?run=R-DEMO-001`

Point at the header:

> “12 explicit dispositions. Five target changes. Every change starts pending. `_gen` writes: zero; the draft is local and non-deployable.”

**Accept M-01** (`PAVehicle → PersonalVehicle`, rule `R-CG-01`, codegen `nameOverride`). The row has an **Accept** button; a decision dialog opens and requires a reason (for example “Reviewed against the documented codegen override.”). Confirm, and the row turns green.

**Scroll to M-12** (`VehicleType.Motorcycle_Ext → schema.vehicleType.motorcycle`, rule `R-TYP-01`) and **Reject** it. The decision dialog/action records a reason; state “rejected in demo: replacement target not agreed.” The banner appears:

> “New assumption A-DEC-04 created from the M-12 rejection. Impact: medium. What target should replace the rejected mapping?”

Say:

> “Reject is not a delete. It creates an owned question. The reviewer is not allowed to leave an unresolved rename implicit.”

Optional: click **View assumption register** or open the assumptions tab. The 3 original assumptions become 4. Do not spend more than a few seconds here.

After both actions the run has **11 audit events** and **4 assumptions**. The packet download and `/packet` page refresh to that state; the seed packet is 9 events / 3 assumptions.

At **1280 × 720**, the mapping table is horizontally scrollable and the decision column may need a small side-scroll; use 1440 × 900 when you want M-01 through M-04 and the decision buttons side by side. M-12 is below the fold at both sizes — scroll to it, then return to the header for the A-DEC-04 notice.

Say the boundary explicitly: “The draft targets Cloud Retrofit **without APD App**, which Guidewire labels not the recommended process; field-level `nameOverride` applies only on that path. The `_ext` draft is a local JSON contract, not official Guidewire schema, mapping, or updater syntax.”

**Exact IDs in this queue**

| Object | IDs |
|---|---|
| Mappings | `M-01` … `M-12` (`M-01` PAVehicle, `M-02` PAVehicle.Year, `M-03` PADriver, `M-04` PALine, `M-05` PersonalAutoRatingFactorConfiguration, `M-06` … `M-11` installed-entity API fields, `M-12` VehicleType.Motorcycle_Ext) |
| Target changes | `C-01` schema, `C-02` mapping, `C-03` updater, `C-04` codegen config, `C-05` installed-LOB config — all pending |
| Findings | `F-001` SBT readiness flag; `F-002` … `F-025` advisory findings (24 rows, 8 rules) |
| Gaps | `G-01` territory, `G-02` rating inputs, `G-03` duplicate PAVehicleDV screen |

### 1:55 — Findings with restraint (45 s)

**Open:** `http://127.0.0.1:8000/findings?run=R-DEMO-001`

Point at the top:

> “24 advisory findings from 8 rules. The SBT readiness flag is separate; it is not one of the 24.”

Click the first `PF-GW-EXC-001` row (finding `F-002`). Point at the detail panel:

> “Claim strength: verified ID. Gosu Secure Coding: ERR00-G, Do Not Suppress Exceptions. Source line, excerpt, remediation. The SQL finding cites Cloud Standard IS-TLS-1238; the secret cites Gosu Secure Coding SEC00-G; the hidden package cites Cloud Standard IS-TLS-1191. Those are two standard families, not one: `standard_family=cloud-standard` versus `gosu-secure-coding`.”

Scroll to **Precision guards**:

> “These are deliberate near-misses. `Query.make` is the supported data-access API, not direct SQL. Comments and strings are masked. The 24 hard negatives must stay silent.”

Say:

> “Generic Gosu linting belongs to SonarQube and Cloud Assurance. These are cited, migration-specific patterns — and every claim is labelled with its strength.”

The page now renders at **1280 × 720** without horizontal overflow; 1440 × 900 is still the better stage view because the detail panel stays beside the table.

### 2:40 — Grounded assistant (35 s)

**Back to Workbench** (`Ctrl+L`, paste the Workbench URL, or click Workbench). Scroll to **Grounded assistant**.

Click **Territory rating?**:

> “Cannot determine. No rating table or territory source artefact exists. It names the searched scopes and the missing evidence. That is A-01 in the packet.”

Click **Motorcycle_Ext?**:

> “One evidence record: EV-0023, `config/extensions/typelist/VehicleType.ttx`, xpath, line 3. A citation card, not a generated answer. The assistant is retrieval-only; model off. It does not decide the mapping.”

### 3:15 — Evaluation honesty (45 s)

**Open:** `http://127.0.0.1:8000/evaluation?run=R-DEMO-001`

Point at the **summary strip labels** first — left to right they read **6/6 estimate-moving issues**, **24 findings / micro-F1 1.00**, **4/4 holdout recall (not imported)**, **6/8 top-8 allowance**, and **24/24 hard negatives silent**:

> “Those five labels are the denominator check. The six metric cards below repeat the same evidence as M1–M6: M1 and M2 8/8, M3 101/101 all links plus a 30/30 sample, M4 12/12, M5 6/6 with the 6/8 top-8 allowance, M6 F1 1.00 — 24 TP / 0 FP / 0 FN. The 24/24 hard negatives are a separate guard count, not a seventh metric.”

Then scroll to the interval chart and say immediately:

> “These are in-sample synthetic measurements. The lower bounds are 61–96%. No human IAA. The reference target is internally authored and AI-assisted. The four-feature holdout is naming-shift only and is not imported. This is not a benchmark.”

Do not let the 100% numbers sit without the caveat.

### 4:00 — Packet and audit (40 s)

**Open:** `http://127.0.0.1:8000/packet?run=R-DEMO-001`

Point at the six section cards:

> “Six sections: cover, executive summary, coverage and confidence, assumption register, findings, evidence and audit appendix. 126 evidence items, not a sample. The four excluded files are in the packet.”

Point at the audit line:

> “Audit chain verified: yes, eleven events in this post-decision view. The seed state is nine events; Accept M-01 + Reject M-12 add one each. The assumption register now has four rows. The main packet hash covers the rendered packet HTML; `packet_json` separately covers canonical packet JSON; the findings, mappings, and evidence digests bind those payloads; the audit head covers the event chain. This is local and tamper-evident, not non-repudiation.”

Click **Download packet HTML** only if the browser download folder is predictable. Otherwise use the URL:

```text
http://127.0.0.1:8000/packet/export?run=R-DEMO-001
```

The export refreshes the packet first, so it includes the two decisions. If you show the pre-decision packet instead, label it: “This is 9 events / 3 assumptions; the live run is now 11 / 4.”

Say:

> “The hash changes when a reviewer decision is recorded. Read it from the live screen; don’t quote the deck. The bundled packet is a historical snapshot.”

If the download fails after the actions, open the live `/packet` page and use its post-decision hash block; do not fall back to the bundled static packet as if it were current.

### 4:40 — Close (20 s)

> “Every claim has evidence; every unknown has a name; every change waits for a human. The ask is one pilot estate, two blind SME annotators, and hard feedback.”

If time is short, skip the optional packet download and end on the audit line.

---

## 2. Fallbacks if something breaks

### The live server is unavailable

1. Check `curl -s http://127.0.0.1:8000/api/health`.
2. If it fails, run `make demo` (this re-seeds and resets decisions; say so if you have already demoed accepts).
3. If port 8000 is occupied, run `make stop`, then `make demo`.
4. If the tmux session is gone, `make demo` recreates it.
5. If Uvicorn died mid-talk, do **not** keep clicking; switch to the deck’s demo slides 6–12 and the captures in `docs/presentation/assets/`. Say: “These are captures from the same build and run; the live server is unavailable.”
6. If the wrapper auto-restarts Uvicorn, the run and its reviewer decisions are **not** reseeded: they persist on disk, and the stable demo secret keeps the reviewer session/CSRF continuity. `make demo` is the command that reseeds to 12 pending / 3 assumptions / 9 audit events. If you deliberately run `make demo`, say so.

### The packet download fails

- Open the live `/packet` page first; it refreshes on view and carries the post-decision 11 events / 4 assumptions.
- If the live packet is unavailable, open the historical snapshot: `docs/demo/preflight-review-packet.html`.
- Say: “This is a historical snapshot from the packaged build, not the live run. Its packet hash and audit head will not verify against a fresh seed, and it predates today’s reviewer actions.”
- Do not run `verify-packet` or `verify-audit` against the static snapshot. The live run is the only hash-verifiable artifact.

### The browser or projector fails

- Use another browser (Chromium/Chrome preferred).
- If the projector is 1280 × 720, use the 1280 × 900 Workbench capture or set browser zoom to 90%.
- If the app is unusable, present the deck; it is fully offline and includes the same evidence.

### You accidentally accept/reject the wrong row

- The decision is audited; it is not a silent edit. For a rehearsal, re-seed with `make demo`.
- During the talk, do not try to “undo” by accepting the opposite; explain that the decision queue is auditable and move on. The demo is about the control, not perfection.

### The assistant is slow or refuses unexpectedly

- It is a local retrieval call; wait a beat. If it fails, use the captured assistant crops on slide 10.
- The territory refusal is the expected behavior. Do not “retry until it answers.”

---

## 3. Twelve likely questions — honest answers

**1. Is this just a linter?**
No. The product output is a cross-artefact feature inventory, a disposition ledger, an assumption register, and a review packet. The eight review rules are supporting evidence, not the product. Generic Gosu linting belongs to SonarQube/Cloud Assurance.

**2. Does it replace CUE, Cloud Assurance, APD conversion, or Cloud Retrofit?**
No. It stops before generation and deployment. The local `_ext` draft is non-deployable and targets Cloud Retrofit **without APD App**, which Guidewire labels not the recommended process. CUE is the official Cloud Upgrade Estimate; Cloud Assurance Services owns the official standards gate; Lighthouse is the migration lab. PreFlight is a pre-estimate evidence pack.

**3. Is the evaluation self-graded?**
It is measured on a controlled synthetic fixture with a frozen reference target, baselines, hard negatives, and a naming-shift holdout. It is **not** a benchmark. The reference target is internally authored and AI-assisted, not blind. There is no human IAA.

**4. Why should I trust the mappings?**
Four are exact documented codegen examples; one is a documented 24-character mechanism applied to a synthetic long type; six are PreFlight API conventions; one is a typelist convention. Every row shows provenance and reviewer state. Rejecting a row creates an assumption. The draft is not compiled or tenant-validated, and the field-level `nameOverride` path applies only to Cloud Retrofit without APD App.

**5. What is gated?**
The Cloud Assurance threshold and full Cloud Standards corpus; APD Conversion (EA); TrainingApp/GO products; Marketplace content; a real tenant. Public IDs and titles are cited; gated bodies are never invented.

**6. How does it scale?**
The demo is 300 files; there is a 5,000-file throughput test, but that is a throughput test, not a generalisation or estate-complexity claim. A performance envelope on a real estate is roadmap work.

**7. Has it been run on a real insurer estate?**
No. All fixtures are synthetic. A real anonymised estate, a second LOB, and blind SME annotation are the next experiments. Until then, no real-estate claim.

**8. Is the assistant an LLM?**
No. It is deterministic retrieval over the run’s evidence; model off; no external calls. It cites evidence IDs or refuses and names missing sources. It does not decide mappings.

**9. What about false positives?**
The rule pack has 24 deliberate hard negatives, including `Query.make`, comments/strings, placeholders, and a 24-character boundary case. Findings are advisory and pattern-based; there is no “zero false positives” claim.

**10. What is actually novel?**
Not the algorithms. Feature location, traceability recovery, reflexion models, and GSN are established. Reversa (2026) is the closest single work. PreFlight’s contribution is domain-specific integration: Guidewire artefact families, a disposition ledger with provenance, an impact-rated assumption register, and a self-verifying packet, offline, before CUE.

**11. What would prove you wrong?**
A real estate where supported parsers miss a large share of files; blind human annotators disagreeing with the links; line-level evaluation collapsing the finding scores; or a reviewer preferring a spreadsheet to the packet. Those are the experiments that matter.

**12. What do you want from us?**
One authorised, anonymised pilot estate for one LOB; two blind SME annotators; and hard feedback on the claims, packet, and disposition model. Contact: Saundarya Singh, independent research prototype; repository `github.com/SaundaryaSingh/Preflight-CloudMigration`; MIT.

---

## 4. Claims to avoid

| Do not say | Say instead |
|---|---|
| “Guidewire-certified”, “official”, “Cloud Assurance pass” | “Independent prototype; official Cloud Assurance was not run.” |
| “APD converter”, “replaces Cloud Retrofit” | “Stops before generation; local non-deployable `_ext` draft on Cloud Retrofit without APD App.” |
| “CUE is free/fast and already in the account” | “CUE is the official Cloud Upgrade Estimate; PreFlight prepares file-level evidence before it.” |
| “Nobody hands you the review packet” | “No public tool we found combines PCF/entity/typelist/template/Gosu evidence into one disposition + assumption packet.” |
| “Imports fail late” | “Endpoint generation then fails to compile.” |
| “SBT is not an estimate line item” | “SBT is a readiness scope/estimate risk that must be priced or explicitly excluded.” |
| “All four are verified IDs in one family” | “Two families: Cloud Standards `IS-TLS-1238`/`IS-TLS-1191`; Gosu Secure Coding `SEC00-G`/`ERR00-G`.” |
| “100% detection”, “zero false positives” | “24/24 hard negatives silent on this fixture; advisory findings.” |
| “6–8 weeks in five minutes” | “A pre-estimate evidence pack; no measured productivity claim.” |
| “Production-ready”, “deployable”, “migration-ready” | “Research prototype; synthetic fixture; draft is non-deployable.” |
| “First / only offline pre-check” | “Public docs do not describe this exact offline pre-bid evidence pack.” |
| “Human IAA” when the comparison is AI-AI | “AI-assisted concordance; no human IAA.” |
| “M3 proves semantic entailment” | “M3 audits excerpt support at the source, not entailment.” |
| “M5 is a learned ranking” | “Fixed two-decoy top-8 allowance; 6/8 slots.” |
| “M6 is just 48/48” | “M6 F1 1.00 = 24 TP / 0 FP / 0 FN.” |
| Any `IS-*` ID not in `docs/claims-ledger.json` | Use only verified IDs/titles, or label `verified-policy` / `heuristic`. |
| “The packet verifies against the bundled snapshot” | “The bundled packet is historical; verify only the live run.” |
| “The packet hash covers canonical JSON” | “The packet hash covers rendered packet HTML; `packet_json` covers canonical JSON; content digests bind findings/mappings/evidence.” |
| “The packet hash is the audit head” | “The audit head is the chain head; it is a separate value from the packet hash.” |

---

## 5. Honest caveats to keep visible

- In-sample, one synthetic 300-file fixture; not a benchmark.
- The 300 files include generated filler; PCF/product model/Gosu are synthetic sketches, not production Guidewire formats. Codegen/entity names match the fixture.
- Reference target internally authored and AI-assisted; not blind, not independent.
- No human inter-annotator agreement; AI-AI concordance is not human IAA.
- Four-feature naming-shift holdout; pre-computed, never imported or tuned.
- M3 checks excerpt support, not semantic entailment.
- M5 uses a fixed 6/8 top-8 allowance, not a learned ranking.
- M6 uses path-level matching; line-level matching is deferred.
- Findings use two standard families: Cloud Standards (`IS-*`) and Gosu Secure Coding (`*-G`); they are not interchangeable.
- Draft is local and non-deployable; not compiled or tenant-validated. It targets Cloud Retrofit without APD App.
- No real estate, customer code, live tenant, deployment, or official Cloud Assurance run.
- Packet (`packet`/`packet_json`), content digests, and audit head change with reviewer decisions and packet refreshes; read the live screen. The snapshot hash is the stable fixture hash. The seed is 9 events / 3 assumptions; the runbook actions make 11 / 4.
- The audit chain is local and tamper-evident, not non-repudiation.
- Tests: 418 passing; freeze manifest: 18/18 recorded hashes; these are build facts, not domain-validation evidence.

---

## 6. One-screen cheat sheet

```text
WORKBENCH     ?run=R-DEMO-001&feature=PA-VEH-01
              31 evidence · 12 files · 4 types · 2 tests · 11 PA-VEH-01 refs · 3 gaps
              long type 37 vs 24: 2 files, PA-VEH-02 dependency, not in the 11 refs
              click a spine node → EV-0001

MANIFEST      /manifest?run=R-DEMO-001&excluded=1
              4 excluded: 2 binary · 1 corrupt · 1 unsupported
              before = after bd4a8a4b338a (immutable fixture snapshot)

RECON         /reconstruction?run=R-DEMO-001
              seed: 12 pending · 3 assumptions · 9 audit events
              accept M-01; reject M-12 (R-TYP-01) → A-DEC-04
              after: 11 audit events · 4 assumptions · 5 changes pending

FINDINGS      /findings?run=R-DEMO-001
              24 findings / 8 rules · SBT readiness F-001 separate
              Cloud Standards IS-TLS-1238 · IS-TLS-1191
              Gosu Secure Coding SEC00-G · ERR00-G
              24 hard negatives silent; Query.make supported
              note: page renders at 1280; 1440 is the better stage view

ASSISTANT     Workbench → Grounded assistant
              Territory → refusal, missing sources
              Motorcycle_Ext → EV-0023 at VehicleType.ttx:3

EVALUATION    /evaluation?run=R-DEMO-001
              six headline metrics: M1 8/8 · M2 8/8 · M3 101/101 + 30/30
              M4 12/12 · M5 6/6 (6/8 allowance) · M6 F1 1.00 (24 TP / 0 FP / 0 FN)
              24/24 hard negatives = guard count, not a seventh metric
              holdout 4/4 not imported · no human IAA

PACKET        /packet?run=R-DEMO-001
              6 sections · 126 evidence · post-decision 11 events / 4 assumptions
              seed packet: 9 events / 3 assumptions; label it if shown
              download: /packet/export?run=R-DEMO-001
              verify: preflight verify-packet R-DEMO-001
                      preflight verify-audit R-DEMO-001 (audit chain only)
              packet hash = rendered HTML; packet_json = canonical JSON
              content digests bind findings/mappings/evidence; audit head = chain
              static docs/demo packet = historical, not hash-verifiable

BUILD         418 tests · 18/18 freeze hashes · 9 seed audit events

CLOSE         “Every claim has evidence; every unknown has a name;
               every change waits for a human.”
```
