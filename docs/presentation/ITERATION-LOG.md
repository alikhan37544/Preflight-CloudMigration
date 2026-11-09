# PreFlight Demo — Iteration Log

**Mode:** Demo/presentation hardening only. Broader evaluation/method work is paused.
**Target:** Independent demo reviewers ≥ 8/10, then commit/push, then resume the rest.
**Review budget:** 5 loops maximum.

## Loop 0 — Baseline independent review (9 Nov 2026)

| Reviewer | Score | Main demo blockers |
|---|---:|---|
| Judge / demo | 7/10 | Slide 16 contact placeholders; packet says “5 approvals”; post-decision packet state inconsistent with deck/runbook; Findings detail below fold at 1280; deck omits M2 and has stale test count |
| Engineering | 6/10 | Packet content hash does not cover findings/HTML; cached export can serve tampered HTML; decision reason/XML secrets unredacted; delete resurrection; corrupt zip 500; static reconstruction; compare ignores target |
| Evaluation | 3/10 | Gold/rule-pack circularity; M5 not a ranking; M6 extra-rule loophole; M3 changed post-freeze; stale docs/test counts. **Deferred to post-demo work.** |
| UX / accessibility | 6.5/10 | Findings detail hidden at 1280; 1024 page overflow; decision IDs/state/reasons missing; packet page/export clipping and print; deck 720p clipping; feature filter broken; tab semantics; assistant history absent; grammar/empty-state issues |
| Domain | 6/10 | `PADriver → VehicleDriver` vs `PersonalVehicleDriver`; `GarageLocation` vs `GarageLocation_Ext`; SBT marker claimed verified; “SBT not an estimate line item”; “imports fail late”; CUE “free/fast”; “nobody hands you the packet”; SEC00-G/ERR00-G conflated with Cloud Standards; non-recommended Cloud Retrofit path not disclosed |

**Current state at loop 0:** `feat/deep-review-demo` HEAD `67e54d1`; 367 tests passing; live demo `R-DEMO-001` healthy; presentation package committed with 16-slide deck and PDF.

### Loop 1 plan

1. Fix all judge/UX demo blockers: 1280 Findings, 1024 overflow, decision IDs/state/reason/terminal actions, feature filter, tabs, assistant history, empty/error copy, packet page grammar/approval wording.
2. Fix all domain-visible contradictions: codegen/entity names, GarageLocation extension, SBT claim strength, deck/runbook claim wording, non-recommended path disclosure, SEC/Gosu family distinction.
3. Make packet integrity real (content hash covers rendered HTML/findings; verify on export), redact decision inputs/XML/JSON, fix corrupt-zip handling.
4. Presentation: placeholders, slide 11 M2/metric labels, stale counts, 720p height guard, mobile deck scroll, annotation markers, runbook post-decision counts; recapture assets; regenerate PDF.
5. Re-run independent demo panel (judge, UX, domain, engineering). Iterate if any reviewer < 8.

## Loop 1 — [in progress]
