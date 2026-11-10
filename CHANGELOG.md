# Changelog

## Unreleased

- Add `/migrator`: a five-agent autonomous draft generator (Scout, Architect, Guardian, Critic, Scribe) over a completed review run.
- Generate a sealed `migration/` bundle with target files, plan, report, bundle manifest, and a separate hash-chained agent log.
- Add `migrate` and `verify-migration` CLI commands; seed the demo with a completed migrator pass.
- Keep every generated change `pending`; the migrator reports `completed_with_gates` and never deploys or self-approves.

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
