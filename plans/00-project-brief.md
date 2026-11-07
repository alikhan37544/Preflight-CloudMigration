# PreFlight — Research Brief for Subagents

## 1. Project identity

**Working title:** PreFlight — AI-Powered Cloud-Readiness Copilot for Guidewire Legacy Estates.

**Context:** An academic project (21CSP302L, SRM Institute of Science and Technology, October 2026) by Saundarya Singh and Rutba Sajad, plus a possible Guidewire DevHack direction. The repository is a blank slate: `/home/arya-stark/Desktop/PROJECTS/Preflight-CloudMigration`.

**One-line goal:** Help a team understand a legacy Guidewire InsuranceSuite estate, trace business features to the technical artefacts that implement them, and produce a reviewable draft of a cloud-oriented target — with evidence for every claim and human approval over every change.

## 2. Source documents — treat as claims, not ground truth

All source documents may contain hallucinations, stale facts, AI-generated assumptions, or unverified numbers. Every research agent must independently verify what it can, and label statements as:

- **VERIFIED** — confirmed by an official/primary source with URL.
- **LIKELY** — supported by credible secondary evidence.
- **UNCERTAIN** — conflicting or incomplete evidence.
- **FALSE / UNSUPPORTED** — contradicted or no evidence found.
- **GATED** — exists but only behind Guidewire login/partner access; cannot be verified publicly.

### Files

- `Docs/Final_Guidewire_Proj_Report.pdf`
  Text extract: `/tmp/opencode/final_report.txt`
  A student design report. Its current architecture is:
  - **Agent 1 — Migration**, split into **Subagent A: Application discovery** and **Subagent B: Cloud reconstruction draft**.
  - **Agent 2 — Review** of violations/optimisation opportunities.
  - **Agent 3 — Comparison** of original vs cloud-oriented artefacts.
  - Agent 1 must be built first; Agents 2 and 3 are gated on available source/target artefacts.
  - Proposed implementation stack in the report: Python, Streamlit, JSON/YAML, standard-library XML/JSON parsing, optional local LLM adapter. (This differs from an earlier README proposal that mentioned FastAPI/Typer/ANTLR4/React — resolve this discrepancy.)
  - Report explicitly says the project is **design/work-plan only**, not implemented.
- `Docs/Top-10-Ideas-FINAL (1).pdf`
  Text extract: `/tmp/opencode/top10.txt`
  An AI-generated hackathon ideation document. It ranks ten Guidewire ideas (APD-Check scorer, SBT gate, LaunchPad Fixer, Clickable Quote, LineageGuard, State Expander, Gosu Cloud-Blockers, GUnit Smell Detector, PCF-Jutro Lookup, Crash-to-Draft) and proposes a combined demo. Treat its metrics, judging claims, and “160 sub-agents” provenance as unverified.
- `/home/arya-stark/Desktop/Saundarya_Master_Migration_README.md`
  Personal context/README. Sections 6.3 and 23.2–23.4 describe PreFlight. It preserves an earlier broad proposal and a narrower five-anti-pattern idea as history; the final report is the most current architecture.

## 3. Core design principles to preserve

- Evidence traceability: every feature, finding, and mapping links to a file/line or explicit source artefact.
- Read-only source: never modify the input snapshot; write proposals to a separate output directory.
- Human review by default: generated changes start as `pending`; reviewer can accept/reject/edit.
- Evidence gaps are reported as gaps, never guessed or fabricated.
- Deterministic parsers/rules where possible; LLMs may explain/summarise but must not invent product behaviour.
- No live insurer tenant, credentials, or third-party calls in the academic prototype.
- Draft artefacts are not deployable until validated in an authorised environment.
- Explicit distinction between “designed”, “implemented”, “measured”, and “proposed”.

## 4. Key research questions for the plan

1. What is actually true about Guidewire's platform, APD, Cloud Retrofit, Cloud APIs, Cloud Assurance, SBT, Integration Gateway, Jutro, Developer Assistants, MCP, and current releases (as of Nov 2026)?
2. Which Guidewire artefacts can a student legally obtain and parse, and what formats/schemas are public?
3. What is a realistic, defensible first feature slice and discovery scope?
4. What architecture is both academically rigorous and demo-able by a small student team?
5. How should the system be evaluated (fixtures, ground truth, metrics, baselines, reviewer effort)?
6. Where is the genuine differentiator versus Guidewire's official tools and existing static-analysis/AI migration tools?
7. What are the legal, security, licensing, and academic-integrity constraints?
8. What delivery plan and cut list make the project succeed within a semester/hackathon timeline?

## 5. Output requirements for every research agent

Return a markdown report with:

1. **Bottom line** — 5–10 bullets that matter for the plan.
2. **Verified findings** — each with source URL and access date; use confidence labels.
3. **Claims checked** — a table of the source-document claims you tested, with verdicts.
4. **Implications for PreFlight** — concrete design/scope decisions, not generic advice.
5. **Risks / unknowns** — what could invalidate the plan.
6. **Sources** — full URLs, with official docs preferred.

Be dense and specific. Prefer tables. Do not write files. Do not repeat the project brief. Flag anything you could not verify. Never invent Guidewire rule IDs, product behaviour, benchmark numbers, or API details.
