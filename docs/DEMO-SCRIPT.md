# PreFlight — 5-Minute Demo Script

**Run state:** pre-seeded `R-DEMO-001`; live import uses `demo-slice-300`; holdout
`northstar-pc-2026.10` is never imported or tuned.

**Setup**

```bash
make demo
# open http://127.0.0.1:8000/?run=R-DEMO-001
```

Health check: `curl -s http://127.0.0.1:8000/api/health`.

**Backup:** screenshots in `docs/presentation/assets/`; static packet snapshot in
`docs/demo/preflight-review-packet.html`. The packet file is a frozen snapshot from the packaged
build, not a live artifact from the run you just seeded: its audit head and hashes will not match a
fresh `R-DEMO-001`. Do not run `verify-packet` or `verify-audit` against it. If the live server fails,
show it as a static example and say so.

---

## 0:00 — Workbench cold open

Open `/?run=R-DEMO-001&feature=PA-VEH-01`.

Say:

> “This is an offline review of a synthetic Guidewire-style Personal Auto estate. 300 files,
> hashed and read-only. No tenant, no customer data. Official Cloud Assurance was not run.”

Point at the **summary strip**:

> “31 evidence records, 12 distinct files, four artefact types, two tests, and 11 references
> for PA-VEH-01. Separately, a 37-character type is a PA-VEH-02 dependency: it appears in two
> files — the template and the product model — and is not one of those 11 references. Three gaps
> are estate-wide.”

Point at the **Feature spine** (all six columns fit at 1280, including Tests):

> “One feature, traced across PCF, installed entity, typelist, extracted template, Gosu, and tests.
> The long type is 37 characters; APD truncates type names at 24. It is separate from PA-VEH-01’s
> 11 references: the long type appears in two files and is a PA-VEH-02 dependency. The three gaps
> are labelled estate-wide, not claimed as three missing links in this feature. This is the kind
> of cross-feature scope that shows up at week five.”

Click a spine node. A sticky evidence card appears beside the graph with file, line/pointer,
excerpt, method, and hash; the full drawer stays below.

## 0:30 — Manifest / live import

Click **Manifest**. Point at:

- 300 files, hashed.
- Four excluded files listed, not hidden (2 binary, 1 corrupt, 1 unsupported). Tick **Excluded (4)**
  and click **Apply**; the checkbox alone does not refresh the table. The filtered view then shows all
  four with reasons.
- Source hash unchanged before and after analysis.

Optional live import: **Runs → New demo run**, or upload a zip on the empty page. The 300-file zip
import runs in under 10 seconds.

## 1:00 — Feature inventory and gaps

Back to **Workbench**. Point at eight features, each with evidence count and confidence.
Open **PA-VEH-01**; show the open question:

> “Territory has a field but no rating source. That is an impact-rated unknown, not a zero.”

## 1:30 — Reconstruction

Open **Reconstruction**.

- 12 explicit dispositions, all **pending** in a fresh seed. Pending rows are neutral; a row turns
  green only after you click **Accept**.
- Provenance: four exact documented codegen examples, one documented 24-char mechanism applied to a
  synthetic long-type example, six PreFlight API conventions, one typelist convention.
- Click **Accept** on the `PAVehicle → PersonalVehicle` row (`M-01`).
- Click **Reject** on the row with rule `R-TYP-01` (mapping ID `M-12`; the rule ID is not the row ID).
  A new assumption appears with owner, impact range, and the question to ask.
- Open **Draft & diff**. The first diff (`C-01`) auto-opens; `nameOverride` is in the collapsed
  codegen diff, so expand **C-04**. The page header still carries the `_gen` guarantee:
  `_gen` writes: 0.
- Open **Assumptions**; show the 7–9 engineer-day long-type range and “heuristic, not a quote.”
- Open **Comparison**; show preserved/changed/unresolved and reference macro-F1.

Say:

> “A decision queue, not a JSON dump. Source untouched; every decision audited.”

## 2:45 — Findings

Open **Findings**.

- 24 advisory findings from 8 rules in this seeded run. The corpus-level
  “three positives and three hard negatives per rule” belongs to the precision-guard panel
  (24 guard cases), not the 24-row findings table.
- Claim strength per finding: verified ID, verified policy, verified document, secondary, heuristic.
- SQL finding cites `IS-TLS-1238`; secret cites `SEC00-G`; hidden package cites `IS-TLS-1191`;
  swallowed exception cites `ERR00-G`.
- Point at the deliberate `Query.make` hard negative: no SQL finding. The evaluation page shows 3 TP / 0 FP / 0 FN per rule.
- Point at SBT readiness flag, separate from the eight scored rule-pack findings.
- Banner: **Official Cloud Assurance: not run.**

Say:

> “Generic linting belongs to SonarQube and Cloud Assurance. We only claim cited,
> migration-specific patterns — and we show when a claim is our own heuristic.”

## 3:30 — Grounded refusal

Go back to **Workbench**. In the assistant, click **Territory rating?** or ask:

> “Does this estate use territory rating?”

The answer refuses: no rating table; searched scopes; missing evidence listed. Then ask
“Which files reference Motorcycle_Ext?” for a grounded, cited answer.

Say:

> “The assistant is retrieval-only, model off. It would rather refuse than invent a source.”

## 4:00 — Evaluation

Open **Evaluation**.

- Six headline metrics in this seeded demo run, with numerators and denominators. The intro reads
  from the actual metric count; an empty/uploaded run shows an empty state instead.
- Baselines: identity mapper, all-unresolved, PCF+grep, grep-only.
- Per-rule TP/FP/FN.
- Holdout aggregate labelled “not imported.”
- Caveat: one synthetic fixture; not a benchmark; no live tenant.

Say:

> “Raw counts, intervals, baselines, and known limitations. Triage evidence, not a certification.”

## 4:30 — Packet

Open **Packet**; download the HTML.

- The live packet's section count comes from its packet JSON (six in this seed); assumption register;
  current audit head; disclaimer.
- Two-step verification against the live run: `preflight verify-packet R-DEMO-001` checks the
  packet and content digests; `preflight verify-audit R-DEMO-001` checks the audit chain only.
  The bundled `docs/demo/preflight-review-packet.html` is a static snapshot, so its hashes will
  not match a freshly seeded run.

## 4:50 — Close

> “Every claim has evidence; every unknown has a name; every change waits for a human.”

---

## Do not say

- “Guidewire-certified”, “official”, “Cloud Assurance pass”, “APD converter”.
- “Production-ready”, “deployable”, “migration-ready”.
- “100% detection”, “zero false positives”, “replaces Cloud Assurance”.
- “Six-figure”, “priced”, “6–8 weeks in five minutes”.
- Any `IS-*` ID not in `docs/claims-ledger.json`.

## Likely Q&A

**“Is this just a linter?”**
No: the output is a cross-artefact feature inventory, explicit dispositions, assumptions, and a
review packet. The eight review rules are supporting evidence, not the product.

**“Does it replace APD conversion or Cloud Retrofit?”**
No. It stops before generation and deployment. The draft is local and non-deployable.

**“Why should we trust the mappings?”**
Four are exact documented codegen examples with public quotes, plus one documented 24-char mechanism
applied to a synthetic long-type example. The rest are labelled conventions and require reviewer
approval. Rejections create assumptions.

**“Is the evaluation self-graded?”**
It is measured on a controlled synthetic fixture with a frozen reference target, baselines,
hard negatives, and a naming-shift holdout that is never imported or tuned. It is not a benchmark.

**“What is gated?”**
Cloud Assurance thresholds and full standard bodies; APD conversion; TrainingApp/GO content; a real
tenant. The claims ledger marks each.
