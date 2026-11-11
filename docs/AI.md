# AI QCer: what “proper AI” means here

**Decision:** PreFlight uses AI as an **optional, evidence-locked quality-control
reviewer** over a deterministic migration draft. It does not let a model
discover the estate, choose dispositions, create findings, write target paths,
approve changes, or deploy. The default remains model-off and offline.

This document records the critical research behind that decision. It is not a
vendor claim and not a benchmark.

## What “QCer” actually means

**QCer = quality-control reviewer.** It is a role, not a model name. A QCer
independently checks a deliverable against acceptance criteria, records findings,
verifies fixes, and signs off a specific revision. In the A2-ai `ghqc` workflow,
a named collaborator is assigned per file; approval is bound to the exact commit
and hash, and a later change invalidates the approval.
[ghqc.app](https://github.com/A2-ai/ghqc.app)

The CriticGPT paper uses “QCer” differently: a more experienced human reviews a
sample of contractor tasks (median 14%) to audit the preference data. CriticGPT
is the model critic; the QCer is the human meta-reviewer.
[arXiv:2407.00215](https://arxiv.org/abs/2407.00215)

The distinction matters:

| Role | Writes? | Critiques? | Signs off? |
|---|---|---|---|
| Generator | yes | no | no |
| Critic | no | yes | no |
| Judge | no | scores | no |
| QCer | no | audits | yes, named human |

An AI critic must never be called the QCer if it can approve its own generator’s
output. PreFlight uses “AI QCer” as reviewer assistance; the human QCer remains
the sign-off authority.

## What the evidence supports

1. **Critic models help, but are not authorities.** On naturally occurring LLM
   bugs, CriticGPT critiques were preferred over human critiques 63% of the
   time; human+critic teams caught similar bug counts with fewer hallucinations.
   The work focused on localizable bugs; dispersed errors remain hard. Critics
   also hallucinate bugs. [arXiv](https://arxiv.org/abs/2407.00215)
2. **The strongest review products separate deterministic tools from the
   model.** CodeRabbit documents static analyzers/SAST, sandboxed exploration,
   and parallel review/verification agents. Qodo documents AST chunking,
   retrieval, context ranking, and dimension-specific agents. Alibaba's
   open-code-review uses deterministic file/rule/line selection around an LLM
   semantic reviewer and explicitly trades recall for precision.
   [CodeRabbit](https://docs.coderabbit.ai/overview/architecture) ·
   [Qodo](https://docs.qodo.ai/core-concepts/qodo-platform-architecture) ·
   [Alibaba](https://github.com/Alibaba/open-code-review)
3. **Vendor review claims are not comparable without a holdout.** Graphite
   Diamond advertises real-bug review with no manual configuration but publishes
   no method or metrics; a competitor-run benchmark (50 PRs) reports 100%
   precision / 7.6% recall for Graphite and 32.6% / 59.5% for CodeRabbit. The
   benchmark is small and non-neutral. The lesson is not the ranking; it is that
   precision/recall must be measured on your own corpus.
   [Graphite](https://graphite.dev/docs/diamond) ·
   [Martian benchmark](https://codereview.withmartian.com/)
4. **LLM-as-judge is biased.** MT-Bench documents position, verbosity, and
   self-enhancement bias; judges prefer lower-perplexity, familiar text. A single
   model score cannot be the gate. [MT-Bench](https://arxiv.org/abs/2306.05685) ·
   [self-preference](https://arxiv.org/abs/2410.21819)
5. **Grounding is unsolved.** GaRAGe (ACL 2025) reports at most 60%
   relevance-aware factuality, 31% deflection true-positive rate, and 58.9%
   attribution F1; models over-summarize instead of abstaining. A citation is
   not proof of entailment. [GaRAGe](https://arxiv.org/abs/2506.07671)
6. **Prompt injection is an architecture problem.** CaMeL separates trusted
   control flow from untrusted data and uses capabilities; prompt-only filters
   are insufficient. [CaMeL](https://arxiv.org/abs/2503.18813) ·
   [OWASP LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
7. **Guidewire's migration core is deterministic.** Cloud Assurance is a
   TeamCity inspection build; Cloud Retrofit generates endpoints through config
   and codegen with a small amount of manual intervention; APD conversion is
   services-led. Public docs describe no LLM in that path. Guidewire's
   Developer Assistants and Qusar agents are real AI, but the published Gosu
   experiment is 33 tasks and the “>40% faster” claim is an internal benchmark.
   [Cloud Assurance](https://docs.guidewire.com/cloud/gcc-guide/insurer-developer/latest/automated-cloud-assurance/) ·
   [Cloud Retrofit](https://docs.guidewire.com/cloud/pc/202603/cloudapica/cloudAPI/topics/508-LOBEndpoints/01-generating-LOB-endpoints/c_generating_lob_specific_endpoints_for_non_apd_native_products.html) ·
   [Developer Assistants](https://www.guidewire.com/resources/blog/developers/accelerating-p-c-delivery-with-developer-assistants-from-guidewire)
8. **AI migration results are hybrid and self-reported.** IBM's COBOL→Java work
   uses static analysis for structure and an LLM for procedural logic; Google's
   migration experience report uses static targeting, unit tests, and human
   review. Neither supports “autonomous migration” or “zero hallucination.”
   [IBM](https://research.ibm.com/publications/enterprise-scale-cobol-to-java-translation-llms-augmented-with-program-analysis) ·
   [Google](https://arxiv.org/abs/2501.06972)
9. **The counterevidence is real.** METR found experienced developers were 19%
   slower with AI in one study; Veracode found 45% of generated samples failed
   security tests; DORA 2025 estimated negative throughput/stability effects at
   higher adoption. These do not invalidate narrow, verified uses; they rule out
   unqualified productivity claims.
   [METR](https://arxiv.org/abs/2507.09089) ·
   [Veracode](https://www.veracode.com/blog/genai-code-security-report) ·
   [DORA](https://services.google.com/fh/files/misc/dora-impact-of-generative-ai-in-software-development.pdf)

## The PreFlight architecture

```
immutable snapshot
  → deterministic parsers + typed evidence graph
  → versioned rules, dispositions, findings, gates
  → deterministic migration bundle (5 agents)
  → optional AI QCer (read-only, structured JSON)
  → evidence-locked validator (citations, paths, numbers, overclaims)
  → human QCer sign-off
```

The model receives only the sealed plan and the evidence records cited by its
packages. It receives no filesystem tools, no shell, no network tools, no
credentials, and no write path. Its output is rejected wholesale if any claim
cites an unknown evidence ID, mentions an unknown path or unsupported number,
uses an overclaim, or is not valid JSON. Rejected output is recorded, not shown
as advice.

### What the AI is allowed to do

- Summarize the deterministic plan with evidence IDs.
- Identify missing checks and package-specific risks.
- Challenge whether a package is adequately evidenced.
- Propose questions for the human QCer.

### What it is forbidden to do

- Choose a target path or disposition.
- Create or modify a finding, mapping, gate, assumption, or approval.
- Resolve an open assumption or change an impact range.
- Write source, `_gen`, schemas, or deployment artifacts.
- Approve, sign off, or deploy.
- Claim official Cloud Assurance, production readiness, or a guarantee.

## Why not put AI in the five deterministic agents?

Because those agents encode the product's evidence contract. If a model writes
the target path or the evidence link, the deterministic verifier is checking the
model against itself. The useful separation is:

- **Deterministic**: inventory, parsers, hashes, features, dispositions, rules,
  gates, paths, bundle, audit.
- **AI**: critique and explanation over that fixed substrate.
- **Human**: approval of the change.

## Failure modes covered by tests

- Unknown evidence citation → reject.
- Malformed JSON → reject.
- Unknown path → reject.
- Unsupported number → reject.
- “Deploy”, “production-ready”, “official Cloud Assurance”, “guarantee” → reject.
- Model endpoint down → `unavailable`, deterministic bundle unchanged.
- No provider configured → no network, no AI claim.
- Prompt injection in evidence → model has no tools; validator still checks
  every output citation and path.
- Self-approval → impossible: AI review has no approval endpoint.

## How to run it

Offline/deterministic (default):

```bash
make demo
```

Optional local model (Ollama):

```bash
PREFLIGHT_AI_PROVIDER=ollama \
PREFLIGHT_AI_MODEL=qwen2.5:1.5b \
.venv/bin/python -m app.cli ai-review R-DEMO-001
```

Or restart the demo with the same environment so the UI exposes **Run AI QCer**:

```bash
PREFLIGHT_AI_PROVIDER=ollama PREFLIGHT_AI_MODEL=qwen2.5:1.5b make demo
```

The AI-only status is available at `GET /api/ai/status`. The review is written
to `migration/ai-review.json` and is **not** part of the sealed deterministic
bundle; it is advisory and separately downloadable.

## Remaining limitations

- This is a local 1.5B–3B-class model in the demo, not a frontier model. The 3B output is slow on CPU and is shown as advisory only. Its output
  is not a quality benchmark.
- No human inter-annotator study or independent QCer audit has been run.
- Citation validation checks identity/path/number support, not full semantic
  entailment.
- The model can still omit a real risk. The deterministic Critic and the human
  gate remain authoritative.
- The demo sends only redacted evidence excerpts, but an operator enabling a
  remote endpoint is responsible for data-residency review.
