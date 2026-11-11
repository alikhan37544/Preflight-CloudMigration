# PreFlight — Simple Project Report

**Independent cloud-readiness review for Guidewire-style insurance estates**

> Every claim has evidence; every unknown has a name; every change waits for a human.

---

## Contents

1. [What this project is](#1-what-this-project-is-in-one-paragraph)
2. [Which insurance, which LOB, which features](#2-which-insurance-which-line-of-business-which-features)
3. [What is being done end-to-end](#3-what-is-being-done-end-to-end)
4. [The frontend, section by section](#4-the-frontend-section-by-section)
5. [The agents, explained simply](#5-the-agents-explained-simply)
6. [What gets detected](#6-what-gets-detected)
7. [Demo numbers at a glance](#7-demo-numbers-at-a-glance)
8. [Boundaries: what to say and avoid](#8-boundaries-what-to-say-and-what-to-avoid)
9. [Five-minute explanation flow](#9-a-simple-five-minute-explanation-flow)
10. [Glossary](#10-glossary)
11. [Bottom line](#11-bottom-line)

---

## 1. What this project is, in one paragraph

PreFlight is an **offline review workstation** for a legacy insurance policy-administration codebase. You give it a read-only snapshot of a Guidewire-style estate (PCF screens, entity files, typelists, templates, Gosu code, tests, and integration config). It inventories every file, groups the files into **business features**, links every statement back to a file and line, checks migration-specific risk patterns, and produces a reviewable **migration draft + assumption register + review packet**.

In simple terms:

| Question a migration team asks | What PreFlight gives back |
|---|---|
| What customisation actually exists? | A hashed file inventory and eight business feature slices |
| Which files belong to which feature? | A feature spine: PCF → entity → typelist → template/Gosu → API draft → tests |
| Can I trust this claim? | File path, line/pointer, excerpt, method, confidence, and excerpt hash |
| What is missing or unknown? | A named gap and an impact-rated assumption with an owner question |
| What would the target change look like? | A local, non-deployable `_ext` target draft and a diff |
| What must a human decide? | Explicit accept / reject / defer decisions and open gates |

**It is not** a converter, a deployment tool, an official Cloud Assurance check, or a live tenant connector. It stops before APD conversion, deployment, and tenant contact.

---

## 2. Which insurance, which line of business, which features

### 2.1 The important distinction

PreFlight does not "insure" anything and it is not an insurance company. It is a **software review tool for a Property & Casualty (P&C) insurer's policy-administration estate**. All estates are synthetic; there is no customer data, no real tenant, and no confidential Guidewire content.

The insurance domain is **Guidewire PolicyCenter-style personal and commercial P&C**, with code surfaces that touch PolicyCenter, ClaimCenter, and BillingCenter in the case studies.

### 2.2 The main demo estate: Personal Auto

The shipped demo (`demo-slice-300`, 300 files) is a **Personal Auto** estate. The review slice is product `PersonalAuto`, feature `PA-VEH-01` (Vehicle Information).

| Feature ID | Business feature | LOB | Evidence records |
|---|---|---|---:|
| PA-VEH-01 | Vehicle Information | Personal Auto | 31 |
| PA-VEH-02 | Vehicle Rating Factors | Personal Auto | 16 |
| PA-DRV-01 | Driver Information | Personal Auto | 17 |
| PA-DRV-02 | Driver Eligibility | Personal Auto | 9 |
| PA-COV-01 | Coverage Selection | Personal Auto | 14 |
| PA-COV-02 | Coverage Terms | Personal Auto | 7 |
| PA-POL-01 | Policy Line and Editions | Personal Auto | 5 |
| PA-POL-02 | Policy Questions | Personal Auto | 2 |

**What each feature contains (plain language):**

- **Vehicle Information** — vehicle identity, model year, usage, type, and garage location.
- **Vehicle Rating Factors** — rating inputs attached to a vehicle.
- **Driver Information** — driver identity, licence, and violation data.
- **Driver Eligibility** — eligibility decision and reason for a driver.
- **Coverage Selection** — liability, collision, and comprehensive coverage choices.
- **Coverage Terms** — coverage term type and value.
- **Policy Line and Editions** — product line identity and edition binding.
- **Policy Questions** — underwriting and garage-keeping questions.

The **deep-dive reconstruction slice** is `PA-VEH-01`. It traces 12 explicit dispositions and produces five target files.

### 2.3 The two case-study estates (code-level lab)

These are separate synthetic insurer profiles used by the `/codebase` lab. They are designed to show two migration realities.

#### Cascade Mutual — monoline Personal Auto

| Item | Detail |
|---|---|
| Segment | Monoline Personal Auto mutual |
| Policies | 420,000 |
| States | TX, OR, WA |
| Source → target | Qusar 2026.08 → GWCP 2027.04 |
| Program | Cloud Retrofit without APD App · single LOB |
| LOB | **Personal Auto** |
| Product model | `CascadeAuto` (custom, APD-targeted) |
| Editions | TX-Base, OR-Base, WA-Base |

**Custom features:** telematics discount tier, dealer vehicle feed, agency commission publication, state rating cache, vendor credential bootstrap.

#### Harbor P&C — multi-line regional carrier

| Item | Detail |
|---|---|
| Segment | Multi-line regional P&C group |
| Policies | 2.6 million |
| States | TX, LA, FL, WA |
| Source → target | Qusar 2026.08 → GWCP 2027.04 |
| Program | Cloud Retrofit with APD conversion · multi-LOB |

| LOB | Product model | Editions | LOB-level features |
|---|---|---|---|
| **Personal Auto** | `HarborAuto` | TX, LA, FL | Telematics discount, windshield glass limit |
| **Homeowners** | `HarborHome` (APD-targeted) | Coastal, Inland | Coastal wind mitigation, roof-age eligibility |
| **Workers' Compensation** | `HarborWC` | TX, LA | Classification table integration, experience-mod publication |

**Cross-application custom features:** coastal wind mitigation, claims vendor gateway, vendor MQ publication, billing reconciliation batch, experience-mod publication, credentials and claim logs.

### 2.4 What is *not* covered

- No real insurer, real policy, real claim, or live tenant.
- No full ClaimCenter or BillingCenter product conversion; those appear only as code/integration surfaces.
- No commercial lines beyond the Harbor Workers' Comp slice.
- No actual policy issuance, rating engine, or deployment.
- No official Cloud Assurance certification.

---

## 3. What is being done end-to-end

### 3.1 The review pipeline (the core product)

```text
Snapshot
  → Intake       hash, classify, list excluded files
  → Parse        PCF, entity, typelist, template, Gosu, YAML
  → Discover     features, evidence graph, confidence, gaps
  → Review       8 migration-specific rules with claim strength
  → Reconstruct  12 dispositions, _ext draft, diff, assumptions
  → Compare      preserved / changed / missing / added / unresolved
  → Evaluate     M1–M6, baselines, intervals, per-rule counts
  → Packet       6-section review artifact with hashes + audit head
```

| Stage | What it does | Main output |
|---|---|---|
| **Intake** | Opens the snapshot read-only, hashes every file, classifies it, and lists binary/corrupt/unsupported files instead of dropping them | `manifest.json`, immutability check |
| **Parse** | Reads each supported file format into a common evidence model | Evidence records |
| **Discover** | Uses seeded rules to group artefacts into business features and builds a feature spine | `features.json`, `spine.json`, `gaps.json` |
| **Review** | Runs eight migration-specific pattern checks with comment/string masking and hard negatives | `findings.json`, `review_evidence.json` |
| **Reconstruct** | Applies 12 mapping rules to `PA-VEH-01` and writes local `_ext` drafts | `mappings.json`, `changes.json`, `assumptions.json` |
| **Compare** | Compares source inventory with the reference target | `comparison.json` |
| **Evaluate** | Computes six headline metrics, baselines, and per-rule results | `metrics.json` |
| **Packet** | Packages the review into a six-section artifact with hashes and an audit head | `packet.json`, `packet.html` |

### 3.2 The two migration layers on top

| Layer | Page | What it does | Scope |
|---|---|---|---|
| **Autonomous migrator** | `/migrator` | Five agents turn the completed review into a local target bundle and gate register | One feature slice: `PA-VEH-01` |
| **Codebase migration lab** | `/codebase` | Five agents scan code, generate refactors, re-scan, verify, and report | Gosu, Java, XML, config, tests across a case estate |

Both layers are **bounded autonomy**: they generate drafts, not deployments. Every change stays `pending` human approval.

### 3.3 The one-sentence flow

> Inventory the estate → group it into business features → attach evidence to every claim → find migration blockers → draft the target → name every unknown → ask a human to decide.

---

## 4. The frontend, section by section

### 4.1 The shared shell (present on every page)

| Element | What it shows | Why it matters |
|---|---|---|
| **Top bar** | `PreFlight`, `Synthetic estate`, `Offline`, `Official Cloud Assurance: not run` | Sets the boundary before any number is read |
| **Context bar** | Run ID, snapshot SHA-256, file count, run status, release context, audit link, "Copy snapshot hash" | Proves which exact snapshot the page is describing |
| **Sidebar** | Review: Workbench, Manifest, Reconstruction, Migrator, Codebase lab, Findings. Evidence: Evaluation, Review packet. Workspace: Case studies, Runs, Settings, About | The whole app is navigable in three groups |
| **Footer** | Full disclaimer | Keeps the legal/claim boundary visible |
| **Decision dialog** | Accept / Reject / Defer / Edit, with a required reason | A decision is an audited event, not a silent click |
| **Toast** | Short success/error feedback | Confirms an action without a page reload |

Accessibility is built in: skip link, keyboard-selectable feature-spine nodes, ARIA labels, visible focus, and scrollable table regions.

---

### 4.2 Workbench (`/`)

**The question it answers:** *What is this feature made of, and can I see the evidence?*

**What you see:**

1. **Summary strip** — evidence records, distinct files, artefact types, tests, references, long-type-vs-APD-limit signal, and gap count.
2. **Features panel** — all eight features with evidence count and confidence; a filter box; the selected feature's description and open questions.
3. **Feature spine** — a six-column graph: **PCF → Entity → Typelist → Template / Gosu → API draft → Tests**. Edges show how artefacts relate; evidence-bearing nodes are clickable; structural API-draft nodes are dashed because they have no evidence record.
4. **Evidence drawer** — file path, line/pointer, excerpt, method, confidence, and excerpt hash for the selected node.
5. **Grounded assistant** — retrieval-only, model off. It answers only from the snapshot and **refuses** when the evidence is missing (for example, territory rating).
6. **Long-type signal** — the 37-character `PersonalAutoRatingFactorConfiguration` versus APD's 24-character import limit, labelled as a synthetic example.
7. **Unknowns and gaps** — each gap with subject, evidence sought, impact, and owner.

**What you can do:** switch features, filter the list, click nodes, inspect evidence, ask the assistant, and record decisions where offered.

**How to explain it:** *"This is the evidence graph. One feature, traced across six artefact types. If a claim has no node, it has no evidence."*

---

### 4.3 Manifest (`/manifest`)

**The question it answers:** *Did we really see every file, and was the source touched?*

**What you see:**

- 300 files, each with kind, parser, status, exclude reason, line count, size, and SHA-256.
- Four excluded files listed explicitly: **2 binary, 1 corrupt, 1 unsupported**.
- A **source unchanged** banner: hash before = hash after.
- Filters by path, status, and "Excluded"; pagination.

**Why it matters:** the credibility of every downstream claim depends on knowing what was parsed and what was not. Nothing is silently dropped.

**How to explain it:** *"This is the chain of custody. Four files could not be parsed, and they are shown with reasons rather than hidden."*

---

### 4.4 Reconstruction (`/reconstruction`)

**The question it answers:** *What is the target disposition for each source item, and what is still unknown?*

Four tabs:

| Tab | Contents | Actions |
|---|---|---|
| **Mapping table** | 12 explicit dispositions (`mapped_exact` / `mapped_transformed`), provenance, rule, rationale, quote/source link | Accept, Reject, Defer, Edit |
| **Draft files** | 5 target files: `_ext` schema, mapping, updater, codegen config, product access YAML, each with a unified diff | Accept / Reject / Defer each change |
| **Assumption register** | Unresolved items with impact, impact range (engineer-days), owner, and the exact question to ask | Review and assign |
| **Comparison** | Preserved / changed / missing / added / unresolved versus the reference target, plus macro-F1 | Inspect gaps |

**Key behaviours:**

- A rejection creates a **new assumption** inline, with an owner, impact range, and question.
- Every decision requires a reason and is written to the hash-chained audit trail.
- The page states **`_gen` writes: 0**. Only `_ext`, codegen, and product-access drafts are proposed.

**How to explain it:** *"This is a decision queue, not a JSON dump. The machine proposes; the reviewer disposes."*

---

### 4.5 Migrator (`/migrator`)

**The question it answers:** *What would a migration crew actually change, and what must a human decide before it ships?*

**What you see:**

1. **Feature selector + Run again** — launches the five-agent pass over a completed review run.
2. **Summary strip** — work packages, draft targets generated, open gates, high-impact gates, bundle files.
3. **Agent crew** — five cards with status and a one-line result.
4. **Generated packages** — one row per target file, with disposition, status, evidence IDs, gate IDs, and approval state.
5. **Open gates** — each with severity, kind, question, owner, and source.
6. **Verification and bundle** — 7/7 checks, plan hash, report hash, bundle hash, agent-log head and verification pill.
7. **Live polling** while a run is in progress.

**Current demo result:** `completed_with_gates` — 5 work packages, 5 draft files, 11 open gates (6 high), 7/7 verification checks passed, 8 bundle files. Nothing is approved.

**How to explain it:** *"The crew does the repetitive reconstruction and verification. The page's headline is still 'human decisions required'."*

---

### 4.6 Codebase lab (`/codebase?case=...`)

**The question it answers:** *Given this code, which patterns block a cloud migration, what is the smallest reviewable refactor, and what must a human still decide?*

**What you see:**

1. **Case switcher** — Cascade Mutual or Harbor P&C.
2. **Green-signal banner** — says whether the signal is unified and that it is bounded, not deployment approval.
3. **The cyclic crew map** — Scout → Architect → Guardian/Critic → Planner, drawn as a loop.
4. **Iterative patching** — each iteration shows Architect, Guardian verdict, and Critic verdict.
5. **Guardian deterministic gate** — 13 checks, pass/fail.
6. **Critic hybrid review** — patch application, coverage, source immutability, and named runtime/architecture risks.
7. **Source findings** — line-level blockers by rule, severity, category, and evidence.
8. **Architect patch bundle** — unified diffs with target path, risk, approval `pending`.
9. **Human review gates** — open by design.
10. **Planner report** — executive report link and summary.
11. **Mid-migration upgrade resilience** — five release-change scenarios, generation bump, invalidated green signal, affected patches, and **revalidate / rollback / defer** choices.
12. **Unexpected scenario playbook** — source changed, corrupt file, duplicate target, analyzer crash, empty snapshot.
13. **Downloads** — SARIF 2.1.0, report, patch bundle ZIP.

**How to explain it:** *"This is the code-level loop. Architect drafts, Guardian blocks, Critic verifies, and if anything is red the Architect goes again. Green still means 'ready for human review', not 'deployed'."*

---

### 4.7 Findings (`/findings`)

**The question it answers:** *What migration-specific patterns were found, how strong is each claim, and what did we deliberately not flag?*

**What you see:**

- **SBT readiness flag** — a separate Standards Based Template signal, not one of the eight scored rules.
- **Rule summary strip** — 24 findings grouped across 8 rules.
- **Findings table** — rule, title, source path, severity, claim strength, standard ID, and inspect action.
- **Detail pane** — full message, evidence, and Accept / Reject / Defer.
- **Precision guards** — 3 deliberate hard negatives per rule (24 cases), showing what the scanner must *not* flag.
- Banner: **Official Cloud Assurance: not run.**

**How to explain it:** *"Generic linting belongs to SonarQube and Cloud Assurance. We only claim cited, migration-specific patterns — and we label our own heuristics as heuristics."*

---

### 4.8 Evaluation (`/evaluation`)

**The question it answers:** *How well does the method perform, and what does that not prove?*

**What you see:**

- Six headline metrics **M1–M6**, each with numerator/denominator and a 95% Wilson interval where available.
- Baselines and deltas: identity mapper, normalized-name mapper, PCF filename baseline, grep-only findings/F1, all-unresolved.
- Per-rule TP / FP / FN table.
- Supporting metrics.
- A holdout aggregate labelled **"not imported"** and never used for tuning.
- A **"What this does not prove"** panel.

**Demo snapshot:**

| Metric | Result |
|---|---|
| M1 Feature recall | 8 / 8 |
| M2 Feature precision | 8 / 8 |
| M3 Evidence-link support precision | 101 / 101 |
| M4 Disposition correctness | 12 / 12 |
| M5 Estimate-moving issue recall | 6 / 6 |
| M6 Finding micro-F1 | 1.00 (3 TP / 0 FP / 0 FN per rule) |

These are **in-sample results on one controlled synthetic fixture**, not a benchmark or a generalisation claim.

**How to explain it:** *"Raw counts, intervals, baselines, and known limitations. This is triage evidence, not a certification."*

---

### 4.9 Review packet (`/packet`)

**The question it answers:** *Can I hand this to a reviewer as a sealed artifact?*

**What you see** — six sections:

1. Cover
2. Executive summary
3. Coverage and confidence
4. Assumption register
5. Findings
6. Evidence and audit appendix

Plus hashes (snapshot, rule pack, reference target, ground truth, features, findings, mappings, changes, assumptions), the audit head, owner/status, and a downloadable HTML packet.

**How to explain it:** *"This is the handover artifact. It carries its own hashes and audit head, so a reviewer can verify what they are reading."*

---

### 4.10 Case studies (`/case-studies`)

**The question it answers:** *What does the method look like on two different insurer shapes?*

Two profile cards — **Cascade Mutual** (narrow, single-LOB, high-value rating path) and **Harbor P&C** (multi-LOB, cross-application, APD + code migration in parallel) — each showing footprint, LOBs, custom features, constraints, and a "why it matters" thesis. The page closes with four claims the cases support.

**How to explain it:** *"One monoline carrier and one multi-line group. The method is the same; the risk mix is different."*

---

### 4.11 Runs (`/runs`)

Run history: run ID, project, fixture, status, created time, open/delete actions, and a "New demo run" path. This is where you start a fresh analysis or revisit an old one.

### 4.12 Settings (`/settings`)

Local configuration and data policy: review context, retention, local-only handling, and the bundled synthetic fixtures. No credentials or tenant settings.

### 4.13 About (`/about`)

The boundary page: what the product is, what it is not, the claim legend, claim-strength definitions, and the full disclaimer.

### 4.14 Empty / loading / error pages

- **Empty** — import a demo slice or upload a ZIP.
- **Loading** — live progress by stage and percentage.
- **Error** — failure reason, retry, and run-history link.

These matter because a review tool must fail visibly, not silently.

---

## 5. The agents, explained simply

### 5.1 First, avoid one common confusion

The **review pipeline** (Intake → Parse → Discover → Review → Reconstruct → Compare → Evaluate → Packet) is a sequence of deterministic stages. Those stages are **not** called agents.

There are **two separate five-agent crews**:

| Crew | Page | Works on | Output |
|---|---|---|---|
| **Migrator crew** | `/migrator` | A completed review run | Local `_ext` target bundle + gate register |
| **Codebase lab crew** | `/codebase` | Source code | Refactor patches + SARIF + executive report |

They share four names — Scout, Architect, Guardian, Critic — but the last agent differs: **Scribe** seals the migrator bundle; **Planner** compiles the codebase report.

---

### 5.2 Migrator crew (five agents, deterministic handoffs)

#### 1. Scout — *"What are we working on, and is there enough evidence to start?"*

| | |
|---|---|
| **Job** | Resolve the feature, count evidence, and refuse an ungrounded slice |
| **Input** | Completed review artifacts: features, evidence, findings, dispositions |
| **Output** | An evidence-linked inventory summary |
| **Demo result** | 300 files → 101 evidence records · 24 findings · 12 dispositions · 31 evidence links on `PA-VEH-01` |
| **Human decision** | None directly; a thin slice stops the run |
| **One-line explanation** | *"Scout is the surveyor: it checks that the ground is solid before anyone drafts."* |

#### 2. Architect — *"Turn every explicit disposition into a target file."*

| | |
|---|---|
| **Job** | Convert every explicit disposition into a target file in the migration bundle |
| **Input** | Scout's grounded inventory + the 12 dispositions |
| **Output** | 5 work packages / 5 files: `_ext` schema, mapping, updater, codegen config, product access YAML |
| **Demo result** | 5 draft targets under `migration/target/` |
| **Human decision** | Every package remains `pending` |
| **One-line explanation** | *"Architect is the draftsperson: it draws the target, it does not sign it off."* |

#### 3. Guardian — *"What can block this change?"*

| | |
|---|---|
| **Job** | Convert findings and open assumptions into blocking review gates |
| **Input** | Review findings + assumption register + target draft |
| **Output** | Gate register, each with severity, owner, question, and source |
| **Demo result** | 11 open gates · 6 high impact · deployment remains blocked |
| **Human decision** | Gate owners must answer or accept the risk |
| **One-line explanation** | *"Guardian is the safety inspector: it can stop the line, and it does."* |

#### 4. Critic — *"Try to break the draft before a human trusts it."*

| | |
|---|---|
| **Job** | Adversarially verify paths, targets, evidence links, parseability, and approval state |
| **Input** | Architect's bundle + Guardian's gates |
| **Output** | PASS/FAIL checks and a verdict |
| **Demo result** | **7/7 checks passed · PASS** |
| **Checks** | packages exist · all files generated · no `_gen` targets · no duplicate targets · generated JSON/YAML parses · every package evidence-linked · human approval retained |
| **Human decision** | None auto-approved |
| **One-line explanation** | *"Critic is the independent reviewer: it assumes the draft is wrong until it proves otherwise."* |

#### 5. Scribe — *"Seal the plan, the report, and the bundle."*

| | |
|---|---|
| **Job** | Write the plan, the review report, and the sealed bundle manifest |
| **Input** | All prior agent outputs |
| **Output** | `migration-plan.json`, `MIGRATION-REPORT.md`, `bundle-manifest.json`, hash-chained agent log |
| **Demo result** | Bundle sealed: 8 files · plan hash `12c2d3d23446…` · report hash `ef9bf37eabcd…` |
| **Human decision** | Human approval still required |
| **One-line explanation** | *"Scribe is the document controller: it packages and stamps the work, it does not approve it."* |

**Migrator run status:** `completed_with_gates` — work completed, gates still open.

---

### 5.3 Codebase lab crew (five agents, cyclic loop)

```text
Scout ──inventory──▶ Architect ──draft──▶ Guardian
                        ▲                   │
                        │                   ▼
                        └──fix requests── Critic
                                            │
                             both green ────┴──▶ Planner
```

#### 1. Scout — *"What code is here, and what does it touch?"*

- Scans Gosu, Java plugins, XML metadata, integration configuration, and GUnit tests.
- Produces an evidence-linked inventory: files, languages, LOC, hotspots, imports, and custom feature slices.
- Skips generated, hidden, binary, and oversized files explicitly.

**One-line:** *"Scout maps the codebase before anyone changes a line."*

#### 2. Architect — *"What is the smallest reviewable refactor?"*

- Iteration 1 handles **error-severity blockers only**; later iterations handle warnings.
- Generates target drafts and unified diffs:
  - Cloud Data Access Gosu service for direct SQL
  - Cloud API YAML + JAX-RS resource for servlets
  - App Events + Integration Gateway descriptors for legacy messaging
  - Secret-reference descriptors for hard-coded credentials
  - Codegen `nameOverride` for long APD type names
  - Removal of static state, local process assumptions, explicit commits, empty catches
- Every patch is `pending`, with source/target SHA-256 and a semantic-review flag.

**One-line:** *"Architect turns each blocker family into a reviewable diff."*

#### 3. Guardian — *"Does the generated target still contain blockers?"*

Deterministic re-scan of the target. It blocks while any error or warning remains. Thirteen checks include:

1. Source snapshot hash unchanged.
2. Every source finding has a patch.
3. No error-severity blockers in the target.
4. No residual warnings.
5. APD type names fit the limit or have an override.
6. No `_gen` targets.
7. Paths are relative, unique, and safe.
8. Generated XML/JSON/YAML parses.
9. Secret diffs are redacted.
10. Every patch is still pending.
11. SARIF is structurally valid 2.1.0.
12. SARIF covers every source finding.
13. Target drafts exist.

**One-line:** *"Guardian is the deterministic gate: no 'warn and continue' path."*

#### 4. Critic — *"Does the diff actually reproduce the target, and what risk remains?"*

- Checks Guardian is green, coverage is complete, and every displayed diff applies cleanly.
- Confirms source immutability.
- Re-scans the target for zero blockers.
- Records architecture and runtime risks as **named human gates** (rating equivalence, event contracts, API auth, secret rotation, tenant isolation, APD regeneration, transaction/failure paths).
- If red, sends targeted fix requests back to Architect; the previous draft is superseded.

**One-line:** *"Critic applies the patches and keeps the risks visible instead of hiding behind a green badge."*

#### 5. Planner — *"Compile the executive report — but only after both gates are green."*

- Produces `MIGRATION-REPORT.md`, the plan, the score, the SARIF summary, and next actions.
- Exits `green_with_human_gates`; every residual risk is still an open gate.
- Does not approve or deploy.

**One-line:** *"Planner writes the report after the gates agree; it does not overrule them."*

**Loop budget:** default three iterations. A one-iteration run stops `blocked` rather than reporting a false green.

---

### 5.4 Migrator vs. codebase lab — how to keep them apart

| Dimension | Migrator | Codebase lab |
|---|---|---|
| Starting point | Completed review run | Raw source snapshot |
| Unit of work | One feature slice (`PA-VEH-01`) | Whole case estate (Gosu/Java/XML/tests) |
| Agent 5 | **Scribe** (seal bundle) | **Planner** (executive report) |
| Loop | Single deterministic handoff chain | Cyclic Architect ↔ Guardian/Critic loop |
| Output | `_ext` schema/mapping/updater/codegen/product-access drafts | Refactor patches, Cloud API/App Events/config drafts, SARIF |
| Risk model | Assumptions + review findings → gates | Patch checks + cross-application runtime risks → gates |
| Upgrade handling | Not the focus | Five release-change scenarios + revalidate/rollback/defer |
| Common rule | Every change `pending`, no deployment | Every patch `pending`, no deployment |

### 5.5 How to explain the whole crew in 30 seconds

> "Scout surveys the ground. Architect draws the change. Guardian checks whether it is safe. Critic tries to break it. Scribe or Planner packages the result. None of them can approve or deploy; that is the human's job."

### 5.6 What the agents never do

- Deploy or contact a tenant.
- Edit `_gen` files.
- Approve their own changes.
- Resolve an assumption.
- Claim an official Cloud Assurance result.
- Hide a failed gate behind a green summary.

---

## 6. What gets detected

### 6.1 Review rules (8 scored rules)

| Rule | Pattern | Claim strength | Standard reference |
|---|---|---|---|
| `PF-GW-SQL-001` | Direct JDBC/SQL access | Verified ID | `IS-TLS-1238` |
| `PF-GW-SEC-001` | Hard-coded secret | Verified ID | `SEC00-G` |
| `PF-GW-PKG-001` | Hidden/internal Guidewire package | Verified ID | `IS-TLS-1191` |
| `PF-GW-EXC-001` | Swallowed exception | Verified ID | `ERR00-G` |
| `PF-GW-TX-001` | Explicit commit inside `runWithNewBundle` | Secondary | — |
| `PF-GW-SRV-001` | Custom servlet | Verified policy | — |
| `PF-GW-NAM-001` | APD type name over 24 characters | Verified document | — |
| `PF-GW-GUNIT-001` | Database access in a pure unit test | Heuristic | — |

`PF-GW-SBT-001` is a **separate readiness flag** for Standards Based Template estates, not a scored finding.

### 6.2 Codebase rule families (16)

| Family | Examples |
|---|---|
| Direct / dynamic / raw SQL | JDBC, `DriverManager`, `executeQuery`, concatenated SQL, `.sql` scripts |
| Legacy messaging | JMS/MQ, `MessageTransport` |
| Servlets | `javax.servlet`, `HttpServlet`, `@WebServlet` |
| Removed runtime APIs | EJB, RMI, JNDI, `sun.misc.Unsafe`, old HTTP clients |
| Internal packages | `gw.internal`, non-public `com.guidewire` |
| Secrets | Hard-coded credentials and tokens |
| Weak crypto | MD5, SHA-1, DES, ECB |
| Static mutable state | Shared caches and tenant markers |
| Local runtime assumptions | Threads, process exit, system properties, filesystem paths |
| Explicit commits | Commit inside a managed bundle block |
| Swallowed exceptions | Empty catch blocks |
| APD naming | Type names above the import limit |
| GUnit coupling | Database access in a pure test |
| Sensitive logging | PII or secrets written to output |

### 6.3 Claim strength

Every finding carries one of: **verified ID**, **verified policy**, **verified document**, **secondary**, or **heuristic**. No finding is presented as a Cloud Assurance violation.

---

## 7. Demo numbers at a glance

| Item | Value |
|---|---|
| Demo fixture | `demo-slice-300` (300 synthetic files) |
| Snapshot | Read-only, SHA-256 hashed before and after |
| Excluded files | 4 (2 binary, 1 corrupt, 1 unsupported) |
| Business features | 8, all Personal Auto |
| Evidence records | 101 |
| Deep-dive slice | `PA-VEH-01` Vehicle Information |
| Dispositions | 12 |
| Draft changes | 5 |
| Findings | 24 from 8 rules |
| Assumptions / gaps | 3 / 3 |
| Migrator output | 5 work packages, 5 draft files, 11 gates (6 high), 7/7 checks, `completed_with_gates` |
| Review packet | 6 sections |
| Tests in the project | 460 (450 non-browser + 10 Playwright) |
| Cascade case | 18 findings, 22 patches, 10 human gates, 2 iterations |
| Harbor case | 20 findings, 21 patches, 11 human gates, 2 iterations |

---

## 8. Boundaries: what to say and what to avoid

### Safe, accurate sentences

- "This is an independent academic research prototype."
- "It reviews a synthetic Guidewire-style estate."
- "It produces local, non-deployable drafts."
- "Findings are pattern-based heuristics with claim-strength labels."
- "Official Cloud Assurance was not run."
- "A green signal means the agents' bounded checks passed; human approval is still required."
- "The source snapshot is read-only and hash-verified."

### Avoid saying

- "Guidewire-certified", "official", "Cloud Assurance pass".
- "APD converter", "production-ready", "deployable", "migration-ready".
- "100% detection", "zero false positives", "replaces Cloud Assurance".
- "Six-figure savings", fixed delivery timelines, or any guarantee.
- Any `IS-*` identifier not present in `docs/claims-ledger.json`.

---

## 9. A simple five-minute explanation flow

| Time | Screen | What to say |
|---|---|---|
| 0:00 | Workbench | "Offline review of a synthetic 300-file Personal Auto estate, hashed and read-only. Official Cloud Assurance was not run." |
| 0:30 | Manifest | "Every file is classified. Four could not be parsed and are listed with reasons. The source hash did not change." |
| 1:00 | Workbench | "Eight business features. PA-VEH-01 is vehicle information. The spine traces it from PCF to tests; click a node for file evidence." |
| 1:30 | Reconstruction | "Twelve dispositions, five draft files. Accept one, reject one, and a new assumption appears inline with an owner and question." |
| 2:45 | Findings | "Twenty-four findings from eight rules, each with a claim strength. Precision guards show what we deliberately did not flag." |
| 3:30 | Workbench assistant | "The assistant refuses the territory rating question because the snapshot has no rating table. It prefers a refusal to an invention." |
| 4:00 | Evaluation | "Six metrics with denominators, intervals, baselines, and limitations. In-sample on one synthetic fixture." |
| 4:30 | Packet | "A six-section packet with hashes and an audit head. This is the handover artifact." |
| 5:00 | Migrator / Codebase | "Five agents draft and verify. Every change is still pending. The machine did the repetition; the human owns the decision." |

---

## 10. Glossary

| Term | Simple meaning |
|---|---|
| **LOB** | Line of business — the insurance product category, e.g. Personal Auto, Homeowners, Workers' Comp |
| **P&C** | Property & Casualty insurance |
| **PCF** | Guidewire PolicyCenter screen definition file |
| **Entity (.eti / .etx)** | Installed and extended data model files |
| **Typelist (.tti / .ttx)** | Installed and extended dropdown/type definitions |
| **Gosu** | Guidewire's JVM-based programming language |
| **GUnit** | Guidewire's unit-test framework |
| **APD** | Advanced Product Designer — Guidewire's product-definition tool; type names over 24 characters are a known import constraint |
| **GWCP** | Guidewire Cloud Platform |
| **Cloud API / `_ext`** | The cloud extension surface: schema, mapping, updater, codegen, and product-access configuration |
| **`_gen`** | Generated files that must never be edited by hand |
| **Disposition** | An explicit decision about what happens to a source item in the target (`mapped_exact`, `mapped_transformed`, unresolved, etc.) |
| **Assumption** | A named unknown with impact, range, owner, and a question to ask |
| **Gate** | A blocking human decision |
| **SARIF** | A standard JSON format for static-analysis results, consumable by GitHub code scanning |
| **Claim strength** | How strongly a finding is backed: verified ID, policy, document, secondary, or heuristic |
| **Wilson interval** | A statistical confidence interval for a proportion |
| **Bounded autonomy** | The agents can draft, verify, and package, but cannot approve or deploy |

---

## 11. Bottom line

PreFlight answers one question well:

> **"What does this insurance estate actually contain, what will block its move to cloud, and what must a human decide before anything changes?"**

It covers a **synthetic Personal Auto** policy-administration estate in the main demo, and **Personal Auto, Homeowners, and Workers' Comp** across its two code-level case studies. It produces evidence, dispositions, assumptions, findings, a draft target, a gate register, and a sealed review packet — but it never deploys, never self-approves, and never claims to be an official Cloud Assurance result.
