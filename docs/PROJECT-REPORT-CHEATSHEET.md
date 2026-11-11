# PreFlight — One-Page Cheat Sheet

**What it is:** an offline, evidence-first review workstation for a synthetic Guidewire-style P&C insurance estate. It inventories files, groups them into business features, links every claim to file evidence, finds migration blockers, drafts a local target, and names every unknown — but never deploys or self-approves.

---

## Insurance coverage

| Dimension | Coverage |
|---|---|
| Industry | Property & Casualty (P&C) insurance |
| Platform style | Guidewire PolicyCenter-style policy administration |
| Main demo LOB | **Personal Auto** |
| Case-study LOBs | **Personal Auto**, **Homeowners**, **Workers' Compensation** (Harbor P&C) |
| Main demo product | `PersonalAuto`, deep-dive feature `PA-VEH-01` Vehicle Information |
| Case-study products | `CascadeAuto`, `HarborAuto`, `HarborHome`, `HarborWC` |
| Data | 100% synthetic; no tenant, customer data, or credentials |

**Demo features (8, all Personal Auto):** Vehicle Information · Vehicle Rating Factors · Driver Information · Driver Eligibility · Coverage Selection · Coverage Terms · Policy Line and Editions · Policy Questions.

**Cascade Mutual:** monoline Personal Auto (420k policies, TX/OR/WA) with 5 custom features: telematics discount, dealer feed, commission publication, state rating cache, vendor credentials.

**Harbor P&C:** multi-line (2.6M policies, TX/LA/FL/WA) with 6 cross-application features: coastal wind mitigation, claims vendor gateway, vendor MQ publication, billing reconciliation, experience-mod publication, credentials & claim logs.

---

## Frontend sections in one line each

| Section | What it does |
|---|---|
| **Workbench** | One selected feature traced across PCF → entity → typelist → template/Gosu → API draft → tests; click a node for file evidence, gaps, and the grounded assistant |
| **Manifest** | Hashed inventory of all 300 files, including 4 excluded files with reasons and a before/after source-immutability check |
| **Reconstruction** | 12 dispositions, 5 draft files with diffs, 3 assumptions, and a source-vs-target comparison; accept/reject/defer with a required reason |
| **Migrator** | Five-agent pass over a completed review: 5 packages, 5 drafts, 11 open gates, 7/7 verification checks, `completed_with_gates` |
| **Codebase lab** | Five-agent cyclic code refactor over a case estate: findings, unified diffs, Guardian/Critic gates, SARIF, upgrade resilience |
| **Findings** | 24 advisory findings from 8 rules, each with claim strength, plus 24 precision-guard negatives and an SBT readiness flag |
| **Evaluation** | Six metrics (M1–M6), Wilson intervals, baselines, per-rule TP/FP/FN, holdout labelled "not imported", and limitations |
| **Review packet** | Six-section handover artifact with hashes, audit head, owner/status, and HTML download |
| **Case studies** | Cascade (monoline) vs Harbor (multi-line) profiles, features, constraints, and what they prove |
| **Runs** | Run history and new demo run |
| **Settings** | Local configuration, data policy, bundled fixtures |
| **About** | What it is, what it is not, claim legend, claim strength, disclaimer |

---

## Agents in one line each

### Migrator crew (`/migrator`) — deterministic handoffs

| Agent | One-line job | Demo result |
|---|---|---|
| **Scout** | Survey the ground: resolve the feature and confirm enough evidence exists | 300 files → 101 evidence · 31 links on PA-VEH-01 |
| **Architect** | Draw the change: turn each disposition into a target file | 5 packages / 5 draft files |
| **Guardian** | Safety inspector: turn findings and unknowns into blocking gates | 11 gates (6 high), deployment blocked |
| **Critic** | Independent reviewer: try to break the draft | 7/7 checks passed |
| **Scribe** | Document controller: seal plan, report, bundle, and hashes | 8 bundle files, sealed |

### Codebase lab crew (`/codebase`) — cyclic loop

| Agent | One-line job | Output |
|---|---|---|
| **Scout** | Map the codebase: Gosu, Java, XML, config, tests | Evidence-linked inventory |
| **Architect** | Draft the smallest reviewable refactor | Unified diffs + cloud config drafts |
| **Guardian** | Re-scan the target and block on any error/warning | 13 deterministic checks |
| **Critic** | Apply the diffs, verify coverage, record runtime risks | Green verdict + named human gates |
| **Planner** | Compile the executive report after both gates are green | Report, plan, SARIF summary |

**30-second explanation:** *"Scout surveys. Architect drafts. Guardian blocks. Critic tries to break it. Scribe or Planner packages it. None of them can approve or deploy — that is the human's job."*

---

## Headline numbers

| Item | Value |
|---|---|
| Demo fixture | 300 synthetic files |
| Features | 8 (Personal Auto) |
| Evidence records | 101 |
| Dispositions / draft changes | 12 / 5 |
| Findings | 24 from 8 rules |
| Assumptions / gaps | 3 / 3 |
| Migrator | 5 packages · 11 gates · 7/7 checks · `completed_with_gates` |
| Packet | 6 sections |
| Project tests | 460 (450 + 10 Playwright) |
| Cascade / Harbor | 18 / 20 findings · 22 / 21 patches · 10 / 11 gates |

---

## Say this / not that

**Say:**
- "Independent academic research prototype."
- "Synthetic Personal Auto estate; no tenant or customer data."
- "Every claim has file evidence; every unknown has a name."
- "Local, non-deployable drafts; every change is pending human approval."
- "Official Cloud Assurance was not run."

**Don't say:**
- "Guidewire-certified", "official", "Cloud Assurance pass".
- "APD converter", "production-ready", "deployable".
- "100% detection", "zero false positives", "replaces Cloud Assurance".
- Any timeline, price, or savings guarantee.

**Close with:**
> "Every claim has evidence; every unknown has a name; every change waits for a human."
