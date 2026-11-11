# PreFlight PR3 — evidence-locked AI QCer

**Branch:** `feat/ai-qcer` (stacked on `feat/autonomous-migrator` / PR #2)
**Goal:** replace the ambiguous “AI” story with a real, optional, critically
constrained model review. No fake inference; no model in the deterministic path.

## What changed

- Added `app/services/ai.py`: Ollama / OpenAI-compatible transport, default
  `none`, status endpoint, structured prompt, evidence-locked validator.
- Added optional **AI QCer** to `/migrator`: a sixth reviewer that critiques the
  sealed five-agent bundle. It cannot write source, choose paths, approve,
  deploy, or alter the deterministic bundle.
- Added `POST /api/runs/{id}/migration/ai-review`, `GET /api/ai/status`, CLI
  `ai-review`, and `ai-status`.
- AI output is accepted only if every claim cites a known evidence ID, mentions
  only known paths/numbers, avoids overclaims, and is valid JSON. Any failure
  rejects the whole response and records the errors.
- Added `docs/AI.md`: critical research on QCer/CriticGPT, CodeRabbit, Qodo,
  Alibaba open-code-review, Guidewire's deterministic migration path, LLM-judge
  bias, grounding, prompt injection, and the counterevidence.
- Settings page shows whether AI is off or configured; no hardcoded “model off”
  claim on the AI surface.

## Honest AI status

No model is bundled in the repository. Default is:

```json
{"configured": false, "provider": "none", "reason": "AI is opt-in. ..."}
```

Local demo with Ollama:

```bash
PREFLIGHT_AI_PROVIDER=ollama PREFLIGHT_AI_MODEL=qwen2.5:1.5b \
  .venv/bin/python -m app.cli ai-review R-DEMO-001
```

The model receives only the deterministic plan and cited evidence excerpts. It
gets no filesystem, shell, tenant, approval, or deployment tools.

## Verification

```text
pytest -q                                  429 passed
claims_lint.py                            claims-lint: OK
ai-status                                 configured=false by default
ai-review (stub, valid)                   accepted
ai-review (unknown citation/path/number)  rejected
ai-review (malformed JSON)                rejected
```

The AI review is `migration/ai-review.json`, separately downloadable and
**excluded from the sealed deterministic bundle** because it is advisory, not a
deterministic artifact. The review-run packet and 12-event migrator audit remain
unchanged.

## Why this is not “AI migration”

The deterministic agents own inventory, parsing, evidence, dispositions, paths,
gates, bundle hashes, and audit. The AI only critiques that substrate. A human
QCer still signs off. This is the separation the research supports; calling the
model an autonomous migrator would be a false claim.
