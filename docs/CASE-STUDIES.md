# Insurer case studies

Two synthetic insurer estates exercise different code-migration realities. Both are
invented. They contain no customer data and no confidential Guidewire content.

The profiles live in `app/services/case_studies.py`; their source snapshots live in
`fixtures/case-studies/`.

---

## 1. Cascade Mutual — monoline Personal Auto

**Profile:** a focused Personal Auto mutual with 420,000 policies across TX, OR, and WA.
It runs a pre-cloud Qusar 2026.08 snapshot against a GWCP 2027.04 target.

**Line of business**

| LOB | Product model | Editions |
|---|---|---|
| Personal Auto | `CascadeAuto` (custom, APD-targeted) | TX-Base, OR-Base, WA-Base |

**Custom feature slices**

| Feature | Owner | Code surface | Cloud target |
|---|---|---|---|
| Telematics discount tier | Product & Rating | Gosu + Java rating plugin | Cloud Data Access read model + typed Gosu factor service |
| Dealer vehicle feed | Distribution | Servlet and integration plugin XML | Cloud API extension endpoint or Gateway route |
| Agency commission publication | Finance & Distribution | JMS message-transport plugin | App Events + Integration Gateway |
| State rating cache | Platform Engineering | Static tenant/factor cache | Tenant-scoped service state or managed cache |
| Vendor credential bootstrap | Security | Literal credentials in Gosu | Cloud secret manager with rotation |

**Constraints that shape the design**

- Direct SQL is prohibited; reads move to Cloud Data Access, writes to application APIs.
- The dealer feed has a contractual acknowledgement budget.
- Three states maintain separate mandatory-offer and notice rules.
- The commission system cannot subscribe to App Events directly; it needs a Gateway route.
- A state filing window prevents a long freeze on rating changes.

**What the lab currently finds**

| Dimension | Result |
|---|---|
| Source findings | 18 (10 error, 8 warning) |
| Categories | data access, messaging, servlet, security, multi-tenancy, transactions, APD, testing, logging, API |
| Loop | 2 iterations: first error-first pass is reworked, second full pass is green |
| Refactor patches | 22 drafts, including Cloud API, App Events, secret-reference, codegen, Cloud Data Access, and JAX-RS resource drafts |
| Human gates | 10 open risks |
| Exit | `green_with_human_gates`; no deployment and every patch pending |

**Why it matters**

Cascade is the narrow, high-value case: a small integration surface where direct SQL is
both a cloud blocker and a latency risk. The green signal is only useful after the rating
rewrite, dealer-feed route, and commission publication are reviewed by their owners.

---

## 2. Harbor P&C — multi-line regional carrier

**Profile:** a regional P&C group with 2.6 million policies across Personal Auto,
Homeowners, and Workers' Compensation. Its custom code crosses PolicyCenter,
ClaimCenter, and BillingCenter.

**Lines of business**

| LOB | Product model | Editions | Custom features |
|---|---|---|---|
| Personal Auto | `HarborAuto` | TX, LA, FL | Telematics discount, windshield glass limit |
| Homeowners | `HarborHome` (APD-targeted) | Coastal, Inland | Coastal wind mitigation, roof-age eligibility |
| Workers' Compensation | `HarborWC` | TX, LA | Classification table integration, experience-mod publication |

**Custom feature slices**

| Feature | Owner | Code surface | Cloud target |
|---|---|---|---|
| Coastal wind mitigation | Homeowners Product | Gosu eligibility cache, internal API, long APD type | Public API + tenant-scoped eligibility service + codegen override |
| Claims vendor gateway | Claims Technology | Servlet | Cloud API endpoint or Gateway route |
| Vendor MQ publication | Enterprise Integration | JMS/MQ plugin and XML transport | App Events + Gateway protocol bridge |
| Billing reconciliation batch | Billing Operations | JDBC, local file/thread/process assumptions | Cloud API job + managed scheduler + Cloud Data Access |
| Experience-mod publication | Workers' Comp Actuarial | JDBC + dynamic SQL + messaging | App Events + typed rating lookup |
| Credentials and claim logs | Security & Claims | Literal vendor secrets, PII output, weak crypto | Secret manager + structured redacted logging |

**Constraints that shape the design**

- Three LOBs share one Account but have different edition and eligibility rules.
- Claims and Billing customizations cross application boundaries.
- Coastal underwriting has a filed-model dependency and a state audit trail.
- The vendor MQ estate cannot be retired during the first cloud release.
- Workers' comp classification updates run under a regulatory calendar.
- APD conversion and code migration run in parallel, so type-name changes can invalidate
  endpoint drafts.

**What the lab currently finds**

| Dimension | Result |
|---|---|
| Source findings | 20 (11 error, 9 warning) |
| Categories | data access, messaging, servlet, security, crypto, multi-tenancy, transactions, APD, testing, logging, API |
| Loop | 2 iterations: error-first rework, then full-pass green |
| Refactor patches | 21 drafts across Gosu, Java, XML, YAML, and cloud configuration |
| Human gates | 11 open risks |
| Exit | `green_with_human_gates`; a mid-migration APD or App Events upgrade invalidates it |

**Why it matters**

Harbor is the hard case: a code-level green signal is necessary but not sufficient. The
Critic keeps cross-application risks visible, and the upgrade simulator shows why a
green bundle must be revalidated when the target release changes an APD or App Events
constraint mid-assessment.

---

## 3. What both cases demonstrate

| Claim | Evidence in the lab |
|---|---|
| Blockers are identifiable at line level | Every finding has a path, line, excerpt hash, and stable fingerprint |
| Refactors are reviewable artifacts | Unified diffs, target drafts, cloud config, semantic-review flags, `pending` approval |
| Guardian is deterministic | Re-scan, path safety, APD limit, syntax parse, SARIF structure, approval state |
| Critic is hybrid | Diff application and coverage checks plus named architecture/runtime risks |
| The loop can stop red | A one-iteration run exits `blocked` without a false green |
| Platform upgrades invalidate green | Generation bump, affected patch list, scenario checks, resume options |
| Output reaches pipelines | SARIF 2.1.0 without source excerpts or secret values |
| Human ownership survives autonomy | Every patch remains pending; every residual risk has an owner and action |

## 4. How to inspect the cases

```bash
make demo
```

Open:

- `http://127.0.0.1:8000/case-studies`
- `http://127.0.0.1:8000/codebase?case=cascade-mutual`
- `http://127.0.0.1:8000/codebase?case=harbor-pc`

Download the bundle, SARIF, report, and individual patches from the lab page. The JSON
API exposes the same artifacts.

All data is synthetic. The case studies are illustrative research profiles, not
customer references, and they do not imply Guidewire affiliation or certification.
