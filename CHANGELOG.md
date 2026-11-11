# Changelog

## Unreleased

- Add `/migrator`: a five-agent autonomous draft generator (Scout, Architect, Guardian, Critic, Scribe) over a completed review run.
- Generate a sealed `migration/` bundle with target files, plan, report, bundle manifest, and a separate hash-chained agent log.
- Add `migrate` and `verify-migration` CLI commands; seed the demo with a completed migrator pass.
- Keep every generated change `pending`; the migrator reports `completed_with_gates` and never deploys or self-approves.
- Add an optional evidence-locked AI QCer over the sealed migrator plan; default-off, advisory, and excluded from the deterministic bundle.
- Add `ai-review` and `ai-status` CLI commands plus an evidence/citation validator that rejects unknown paths, numbers, and overclaims.
- Add `/codebase`: a five-agent cyclic code-migration lab (Scout, Architect, Guardian, Critic, Planner) over Gosu, Java plugins, XML, integration configuration, and GUnit tests.
- Add `rules/codebase_rules.yaml` with 16 cloud-blocker families: direct/dynamic SQL, raw SQL, legacy messaging, servlets, removed runtime APIs, internal packages, secrets, weak crypto, static state, process assumptions, explicit commits, swallowed exceptions, APD naming, GUnit coupling, and sensitive logging.
- Generate Cloud Data Access Gosu adapters, Cloud API/JAX-RS resources, App Events and Gateway descriptors, codegen overrides, secret references, and unified diffs; every patch remains pending.
- Add deterministic Guardian checks for target re-scan, APD limits, path safety, syntax parsing, redacted secret diffs, SARIF validity, and approval state.
- Add hybrid Critic checks for diff application, coverage, source immutability, and named runtime/architecture risk gates.
- Export SARIF 2.1.0 with stable fingerprints, rule help, cloud targets, and no source excerpts or secret values.
- Add upgrade resilience: generation bumps, stale-green invalidation, affected patch lists, revalidate/rollback/defer, and named unexpected-scenario handling.
- Add two synthetic insurer case studies: Cascade Mutual (monoline Personal Auto) and Harbor P&C (Personal Auto, Homeowners, Workers' Comp).
- Update the claims-lint-compatible rulepack hash handling to keep the frozen review snapshot reproducible.
- Test suite grows to 460 collected tests (450 non-browser + 10 Playwright).

## v1.0.0 — 2026-11-08

First public snapshot.

- Offline evidence-first review workstation for Guidewire-style Personal Auto estates.
- Six primary screens: Workbench, Manifest, Reconstruction, Findings, Evaluation, Packet.
- Read-only snapshot intake, hashing, classification, unsupported/corrupt reporting.
- PCF, entity, typelist, product/template XML, YAML, Gosu, and GUnit parsers.
- Cross-artefact feature assembly with evidence links and confidence labels.
- 12 explicit dispositions for `PA-VEH-01`; local `_ext` schema/mapping/updater/codegen draft.
- 8 review rules with claim-strength labels and adversarial false-positive gates.
- Impact-rated assumption register and six-section review packet.
- Frozen evaluation fixtures, gold labels, reference target, and holdout aggregate.
- Hash-chained audit log, CSRF, CSP, host/origin checks, safe archive/XML/YAML handling, secret redaction.
- 421 tests including Playwright golden path.
- Internal QA: core flow, packet, and audit gates pass; independent demo reviewers are scoring the presentation.
