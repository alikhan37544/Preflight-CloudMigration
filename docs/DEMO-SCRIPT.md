# PreFlight — 5-Minute Demo Script

**Run state:** pre-seeded `R-DEMO-001`; live import uses `demo-slice-300`; holdout
`northstar-pc-2026.10` is never imported or tuned.

**Setup**

```bash
make demo
# open http://127.0.0.1:8000/?run=R-DEMO-001
```

Health check: `curl -s http://127.0.0.1:8000/api/health`.

**Backup:** screenshots in `docs/screenshots/`; packet in
`data/runs/R-DEMO-001/packet.html`. If the server fails, show the packet and screenshots.

---

## 0:00 — Workbench cold open

Open `/?run=R-DEMO-001&feature=PA-VEH-01`.

Say:

> “This is an offline review of a synthetic Guidewire-style Personal Auto estate. 300 files,
> hashed and read-only. No tenant, no customer data. Official Cloud Assurance was not run.”

Point at the **Feature spine**:

> “One feature, traced across PCF, installed entity, typelist, extracted template, Gosu, and tests.
> The long type is 37 characters; APD truncates type names at 24. Eleven references, four artefact
> types, two tests. This is the kind of surprise that shows up at week five.”

Click a spine node. The evidence drawer opens with file, line/pointer, excerpt, method, and hash.

## 0:30 — Manifest / live import

Click **Manifest**. Point at:

- 300 files, hashed.
- Four unsupported/corrupt files listed, not hidden.
- Source hash unchanged before and after analysis.

Optional live import: **Runs → New demo run**, or upload a zip on the empty page. The 300-file zip
import runs in under 10 seconds.

## 1:00 — Feature inventory and gaps

Back to **Workbench**. Point at eight features, each with evidence count and confidence.
Open **PA-VEH-01**; show the open question:

> “Territory has a field but no rating source. That is an impact-rated unknown, not a zero.”

## 1:30 — Reconstruction

Open **Reconstruction**.

- 12 explicit dispositions. Accepted row is green; pending rows are neutral.
- Provenance: five documented codegen overrides, six PreFlight conventions, one typelist convention.
- Click **Accept** on `PAVehicle → PersonalVehicle`.
- Click **Reject** on a mapping (for example `R-TYP-01`). A new assumption appears with owner,
  impact range, and the question to ask.
- Open **Draft & diff**; show `nameOverride` and `_gen` prohibition.
- Open **Assumptions**; show the 7–9 engineer-day long-type range and “heuristic, not a quote.”
- Open **Comparison**; show preserved/changed/unresolved and reference macro-F1.

Say:

> “A decision queue, not a JSON dump. Source untouched; every decision audited.”

## 2:45 — Findings

Open **Findings**.

- 24 advisory findings from 8 rules (3 positives and 3 hard negatives per rule).
- Claim strength per finding: verified ID, verified policy, verified document, secondary, heuristic.
- SQL finding cites `IS-TLS-1238`; secret cites `SEC00-G`; hidden package cites `IS-TLS-1191`;
  swallowed exception cites `ERR00-G`.
- Point at the deliberate `Query.make` hard negative: no SQL finding. The evaluation page shows 3 TP / 0 FP / 0 FN per rule.
- Point at SBT readiness flag, separate from the eight rules.
- Banner: **Official Cloud Assurance: not run.**

Say:

> “Generic linting belongs to SonarQube and Cloud Assurance. We only claim cited,
> migration-specific patterns — and we show when a claim is our own heuristic.”

## 3:30 — Grounded refusal

In the assistant, click **Territory rating?** or ask:

> “Does this estate use territory rating?”

The answer refuses: no rating table; searched scopes; missing evidence listed. Then ask
“Which files reference Motorcycle_Ext?” for a grounded, cited answer.

Say:

> “The assistant is retrieval-only, model off. It would rather refuse than invent a source.”

## 4:00 — Evaluation

Open **Evaluation**.

- Six headline metrics with numerators and denominators.
- Baselines: identity mapper, all-unresolved, PCF+grep, grep-only.
- Per-rule TP/FP/FN.
- Holdout aggregate labelled “not imported.”
- Caveat: one synthetic fixture; not a benchmark; no live tenant.

Say:

> “Raw counts, intervals, baselines, and known limitations. Triage evidence, not a certification.”

## 4:30 — Packet and close

Open **Packet**; download the HTML.

- Six sections; assumption register; audit head; disclaimer.
- Hash-chain verification: `preflight verify-audit R-DEMO-001`.

Close:

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
Five are documented codegen overrides with public quotes. The rest are labelled conventions and
require reviewer approval. Rejections create assumptions.

**“Is the evaluation self-graded?”**
It is measured on a controlled synthetic fixture with a frozen reference target, baselines,
hard negatives, and a naming-shift holdout that is never imported or tuned. It is not a benchmark.

**“What is gated?”**
Cloud Assurance thresholds and full standard bodies; APD conversion; TrainingApp/GO content; a real
tenant. The claims ledger marks each.
