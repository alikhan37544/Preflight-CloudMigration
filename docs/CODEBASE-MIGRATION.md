# Codebase migration lab

The `/codebase` lab is the code-level migration layer of PreFlight. It extends the
review workstation with a bounded, five-agent cyclic assessment of legacy Gosu, Java
plugins, XML metadata, integration configuration, and GUnit tests.

It answers a different question from feature discovery:

> Given this code, which patterns block a Guidewire Cloud Platform migration, what
> is the smallest reviewable refactor, and what must a human still decide?

The lab is offline and synthetic-fixture based. It does not contact a tenant, deploy
code, edit `_gen` files, or approve its own changes. Official Cloud Assurance was not
run. Findings are advisory structural checks, not an official Cloud Assurance result.

---

## 1. The five-agent cycle

| Agent | Responsibility | Output |
|---|---|---|
| **Scout** | Inventory source files, languages, LOC, hotspots, imports, and custom feature slices | Evidence-linked code inventory |
| **Architect** | Generate target drafts, cloud configuration, unified diffs, and semantic-review notes | `patches`, target bundle, config drafts |
| **Guardian** | Deterministically re-scan the generated target against the rule pack and APD constraints | PASS/FAIL checks and blocking verdict |
| **Critic** | Verify patch coverage, diff application, source immutability, and runtime/architecture risk | Green verdict plus named human gates |
| **Planner** | Compile the executive report, score, SARIF summary, and next actions | `MIGRATION-REPORT.md` and plan |

These are deterministic local stand-ins for the Scout and Architect reasoning roles: the demo
requires no LLM API, and the handoff contract is the same one a model-backed agent would use.
Guardian and Critic remain deterministic gates over the produced artifacts.

### Iteration semantics

```text
Scout ──inventory──▶ Architect ──draft──▶ Guardian
                         ▲                   │
                         │                   ▼
                         └──fix requests── Critic
                                             │
                              both green ────┴──▶ Planner
```

The loop is deliberately cyclic, not a single pipeline:

1. **Scout → Architect.** Scout hands over a grounded inventory. Architect starts
   with **error-severity blockers only** in iteration 1.
2. **Architect → Guardian.** Guardian re-scans the generated target. It blocks while
   any error or warning remains, including warnings that the first pass did not
   attempt.
3. **Guardian → Critic.** Critic independently checks patch coverage, applies every
   displayed unified diff, checks the source hash, and records cross-application risk.
4. **Critic → Architect.** If either gate is red, Critic sends targeted fix requests.
   Architect re-enters the loop. The previous draft is superseded.
5. **Guardian + Critic → Planner.** Only when both gates are green does Planner compile
   the report. The green signal still requires human approval and keeps every residual
   risk as an open gate.

The bounded budget defaults to three iterations. A one-iteration run stops with an
explicit `blocked` state, not a false green.

---

## 2. Code-level blocker taxonomy

The pack is `rules/codebase_rules.yaml`. Every rule declares a category, severity,
claim strength, cloud target, and refactor strategy.

| Rule | Pattern | Claim | Cloud target |
|---|---|---|---|
| `PF-CODE-SQL-001` | Direct JDBC/SQL (`java.sql`, `javax.sql`, `DriverManager`, `executeQuery`) | verified ID `IS-TLS-1238` | Gosu Query / Cloud Data Access for reads; application APIs for writes |
| `PF-CODE-SQL-002` | Dynamic SQL string construction | heuristic | Typed Gosu Query or application API |
| `PF-CODE-SQL-003` | Raw `.sql` script in the extension bundle | heuristic | Cloud Data Access read model or application API |
| `PF-CODE-MSG-001` | Legacy message-transport plugin, JMS/MQ, `MessageTransport` | secondary | App Events webhook or Integration Gateway route |
| `PF-CODE-SRV-001` | Servlet (`javax.servlet`, `HttpServlet`, `@WebServlet`) | verified policy | Cloud API extension endpoint or Gateway route |
| `PF-CODE-API-001` | Removed Java runtime API (EJB, RMI, JNDI, `sun.misc.Unsafe`, old HTTP client) | verified policy | Supported platform API or Gateway |
| `PF-CODE-API-002` | Hidden/internal Guidewire package (`gw.internal`, non-public `com.guidewire`) | verified ID `IS-TLS-1191` | Supported public API |
| `PF-CODE-SEC-001` | Hard-coded credential or token | verified ID `SEC00-G` | Cloud secret manager binding |
| `PF-CODE-SEC-002` | Weak crypto (`MD5`, `SHA-1`, DES, ECB) | heuristic | Platform-approved FIPS primitive |
| `PF-CODE-MT-001` | Static mutable state in a shared runtime | heuristic | Tenant-scoped service state or managed cache |
| `PF-CODE-MT-002` | Local thread/process/system-property/filesystem assumption | heuristic | Platform scheduler, configuration service, or Gateway |
| `PF-CODE-TX-001` | Explicit commit inside `runWithNewBundle` | secondary | Managed bundle transaction |
| `PF-CODE-EXC-001` | Empty catch block | verified ID `ERR00-G` | Explicit failure handling |
| `PF-CODE-APD-001` | APD product-template type name above the import limit | verified document | Codegen `nameOverride` and endpoint regeneration |
| `PF-CODE-GUNIT-001` | Database access in a pure GUnit test | heuristic | Pure GUnit with mocked seams |
| `PF-CODE-LOG-001` | Sensitive field written to output | heuristic | Structured logging with redaction |

The direct-SQL and hidden-package rules reuse the documented identifiers already used
by the review layer. Rules that cannot claim a documented identifier are labelled
`heuristic` and carry no standard ID.

---

## 3. Static analysis design

The scanner is intentionally conservative:

- **Comment/string-aware masking.** Gosu and Java comments and string literals are
  replaced with spaces before structural matching, preserving line and column offsets.
  Prose such as `// DriverManager.getConnection` cannot fire a finding.
- **Separate value inspection.** Weak-crypto and secret rules use a comment-masked view
  that preserves string literals where the value matters.
- **Secret redaction at capture.** Secret excerpts are replaced with
  `[REDACTED:<fingerprint>]` before they enter a finding, SARIF file, report, or API
  response. The raw value is not persisted.
- **Evidence-bound findings.** Every finding has a path, line, excerpt hash, and stable
  fingerprint derived from rule, path, line, and excerpt. The SARIF exporter carries
  the fingerprint as `partialFingerprints.primaryLocationLineHash`.
- **Explicit exclusions.** Generated paths, `_gen`, hidden directories, symlinks, binary
  files, and oversized files are listed as skipped rather than silently dropped.
- **No source writes.** The scanner opens source files read-only. The Architect works
  in a temporary target tree; tests assert the source tree hash is unchanged.

### What it is not

This is not a Gosu compiler, AST, or a replacement for SonarQube, Cloud Assurance, or
the official Cloud Standards checks. It is a structural pre-check designed to surface
code-level migration work early with evidence a developer can inspect.

---

## 4. Architect refactor strategies

| Finding family | Draft strategy |
|---|---|
| Direct SQL | Remove JDBC imports/calls, add a `Query` import, and generate a candidate `<Class>CloudDataAccess.gs` service using `Query.make(...).select()` |
| Dynamic SQL | Quarantine the concatenated statement and route the method through the same typed data-access draft |
| Legacy messaging | Remove the transport plugin and generate an App Events publication descriptor plus Integration Gateway delivery route |
| Servlet | Remove servlet imports/surface, generate a Cloud API extension YAML and a JAX-RS resource draft |
| Removed runtime API | Comment out the unsupported call and record the replacement family in the patch strategy |
| Internal package | Remove the import/usage and record the public-API replacement requirement |
| Hard-coded secret | Replace the literal with an environment or secret binding and generate a secret-reference descriptor; the displayed diff is redacted |
| Weak crypto | Replace MD5/SHA-1/DES/ECB with SHA-256/AES/GCM in the draft |
| Static mutable state | Remove `static` from the declaration and add a tenant-isolation review note |
| Process/thread/filesystem | Remove the local-runtime assumption and route to a platform service |
| Explicit commit | Remove the commit from the managed bundle block |
| Empty catch | Insert a contextual rethrow |
| APD long type | Generate a codegen `nameOverride` mapping the truncated visualized name to the installed name |
| GUnit DB coupling | Remove database calls from the pure test and add an integration-test follow-up |
| Sensitive logging | Remove the sensitive value from output |

Each patch includes:

- `patch_id`, source/target path, rule ids, finding ids
- a unified diff (`a/...` → `b/...`)
- source and target SHA-256
- risk level, semantic-review flag, approval state `pending`
- secret-redacted diff flag where applicable

The Critic applies every non-redacted diff to the original and compares it with the
target draft. A patch that does not reproduce its target fails the gate.

---

## 5. Guardian deterministic gate

Guardian re-scans the generated target bundle and checks:

1. Source snapshot hash unchanged.
2. Every source finding has a patch.
3. Target has no error-severity blockers.
4. Target has no residual warnings.
5. APD type names fit the effective import limit (or have an override).
6. No `_gen` targets.
7. Target paths are unique, relative, and safe.
8. Generated XML/JSON/YAML drafts parse.
9. Secret patches redact their displayed diffs.
10. Every patch remains pending human approval.
11. SARIF is structurally valid 2.1.0.
12. SARIF results cover every source finding.
13. Target drafts exist.

A failing check blocks the green signal. There is no “warn and continue” path for an
error or warning blocker.

---

## 6. Critic hybrid review

Deterministic checks:

- Guardian is green.
- Patch coverage is complete.
- Displayed diffs reproduce target drafts.
- Target paths are unique.
- Source is unchanged.
- Target re-scan has zero blockers.
- No automatic approval.

Then Critic records architecture and runtime risk as named human gates. Examples:

- semantic equivalence of a rating/data-access rewrite;
- App Events contract, ordering, and consumer acknowledgement;
- Cloud API route authentication and consumer cut-over;
- credential rotation and secret binding;
- tenant-isolation/concurrency testing after removing static state;
- APD endpoint regeneration and compilation;
- transaction, failure-path, and test-coverage verification.

These gates do not hide behind the green signal. They remain visible in the API, page,
report, and bundle manifest.

---

## 7. SARIF 2.1.0

`GET /api/codebase/cases/<case>/sarif` returns a SARIF 2.1.0 document with:

- tool driver `PreFlight CodeGuard`
- one rule entry per rule id, with help, help URI, category, claim strength, and cloud target
- results with rule index, level, message, artifact URI, start line/column
- `partialFingerprints.primaryLocationLineHash`
- properties: finding id, evidence hash, standard id, remediation, redacted flag
- run properties: `official_cloud_assurance: false`, synthetic flag, counts

Example GitHub Actions step:

```yaml
- name: PreFlight codebase review
  run: |
    curl -sS "http://127.0.0.1:8000/api/codebase/cases/cascade-mutual/sarif" \
      -o preflight-code.sarif

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: preflight-code.sarif
```

The SARIF file does not embed secret values or source excerpts. It carries locations
and evidence fingerprints instead.

---

## 8. Mid-migration upgrade resilience

A migration assessment can outlive the target release it was written against. The
resilience module models five release events:

| Scenario | Effect |
|---|---|
| `GWCP-APD-NAMING-2027.04` | APD type-name limit tightens from 24 to 20; APD patches and codegen overrides are affected |
| `GWCP-APP-EVENTS-V2-2027.04` | App Events envelope moves to schema v2; publication drafts are affected |
| `GWCP-GATEWAY-MTLS-2027.04` | Gateway routes require mTLS and a scoped service identity |
| `GWCP-GOSU-API-REMOVAL-2027.04` | A deprecated runtime API is removed; API replacement drafts are affected |
| `GWCP-CLOUD-API-VERSION-2027.04` | Cloud API extension routes move to a new version prefix |

On a detected upgrade:

1. The active assessment generation increments.
2. The previous green signal is invalidated, never silently reused.
3. Affected patches and rule ids are identified.
4. Scenario-specific checks run against the existing bundle.
5. Resume options are recorded: **revalidate**, **rollback**, or **defer**.
6. Re-running the Architect with the upgrade scenario uses the new effective values. For the
   APD naming scenario, the codegen override is regenerated at 20 characters; the same
   scenario against the earlier 24-character bundle reports `revalidation_required`.
7. A human still approves every patch.

Unexpected scenarios also have named handling: source changed mid-scan, corrupt file,
duplicate target, analyzer crash, and empty snapshot. See the page’s playbook or
`resilience_drills()`.

---

## 9. Run it

```bash
make demo
# http://127.0.0.1:8000/codebase?case=cascade-mutual
# http://127.0.0.1:8000/codebase?case=harbor-pc
# http://127.0.0.1:8000/case-studies
```

API:

```text
GET  /api/codebase/cases
GET  /api/codebase/cases/{case_id}
POST /api/codebase/cases/{case_id}/run
POST /api/codebase/cases/{case_id}/upgrade
POST /api/codebase/cases/{case_id}/resume
GET  /api/codebase/cases/{case_id}/sarif
GET  /api/codebase/cases/{case_id}/report
GET  /api/codebase/cases/{case_id}/patches/{patch_id}
GET  /api/codebase/cases/{case_id}/bundle.zip
GET  /api/codebase/cases/{case_id}/audit
```

CLI:

```bash
.venv/bin/python -m app.cli codebase cascade-mutual --out ./codebase/cascade
.venv/bin/python -m app.cli codebase harbor-pc --iterations 2 --upgrade GWCP-APD-NAMING-2027.04
```

The CLI writes `target/`, `patches/`, `results.sarif`, `MIGRATION-REPORT.md`, and
`bundle-manifest.json`. It exits non-zero when the green signal is not unified.

All POST routes require the local CSRF token. No tenant, credentials, telemetry, or
external network call is used.

---

## 10. Boundaries and limitations

- The lab is a structural scanner, not a compiler or full data-flow engine.
- Candidate entities in generated Gosu drafts require domain confirmation.
- Refactors are drafts; they are not compiled against a Guidewire runtime.
- The green signal is a bounded agent verdict, not an official Cloud Assurance result.
- Case studies and fixtures are synthetic. They are not customer data.
- APD rules are based on documented behavior and must be re-checked against the target
  release; the upgrade simulator exists for exactly that reason.
- Every patch remains pending human approval. Nothing is deployed.
