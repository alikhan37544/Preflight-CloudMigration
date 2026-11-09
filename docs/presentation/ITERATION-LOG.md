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

## Loop 1 — Demo package hardening (9 Nov 2026)

**Branch:** `demo/deck`, cut from `feat/deep-review-demo` HEAD `67e54d1` (the app fixes are merged in this HEAD, so assets were recaptured rather than deferred).

### What changed

**Content and claims**
- Slide 16: removed `[name]`, `[email]`, `[github / institution]`; now Saundarya Singh · independent research prototype · `github.com/SaundaryaSingh/Preflight-CloudMigration` · MIT. Added the explicit pilot ask: one authorised estate, two blind SME annotators, hard feedback.
- Slide 11: six headline metrics with M2 restored. M6 is labelled `F1 1.00 (24 TP / 0 FP / 0 FN)`; 24/24 hard negatives are a separate guard count, not a seventh metric.
- Test/freeze/audit counts: 367 tests; 18/18 recorded freeze hashes; seed 9 audit events, 11 after Accept M-01 + Reject M-12; 4 assumptions after the rejection. Updated deck, notes, README, runbook, sources, and `evidence.json`.
- Slide 8: wording is now “Four exact documented examples + one documented 24-char mechanism applied to a synthetic long type.” Added the scope note: Cloud Retrofit without APD App; field-level `nameOverride` applies only on that path; `_ext` is a local JSON contract, not official Guidewire schema/mapping/updater syntax.
- Slide 2: “imports fail late” → “endpoint generation then fails to compile”; SBT is a readiness scope/estimate risk; 24-character limit explicitly applies to type names, with other APD short-name/label limits noted.
- Slide 3: exact positioning sentence (“No public tool we found combines PCF/entity/typelist/template/Gosu evidence into one disposition + assumption packet”); explicit acknowledgment of CUE, Cloud Assurance Services, Lighthouse, SurePath, Developer Assistants, GoQu, CAST/ADDI, Syntra ETL, and SI assessments; “positioning, not an independent product evaluation” footnote.
- Slide 15: removed the unsupported “CUE is free/fast” claim; CUE is an official, formal, high-level assessment. Added Cloud Assurance Services and Lighthouse; clarified “independent” means vendor-independent, not independently validated.
- Slide 9: two standard families are separated (`cloud-standard` vs `gosu-secure-coding`); `IS-TLS-1238`/`IS-TLS-1191` are not presented as the same family as `SEC00-G`/`ERR00-G`.
- Slides 6/7: synthetic-fixture realism disclosure added to visible notes and speaker notes (generated filler; PCF/product model/Gosu are sketches, not production formats; codegen/entity names match the fixture).
- Slide 12: post-decision packet state (11 events / 4 assumptions) with pre-decision state labelled; capture-time hash prefixes explicitly say “read live.”

**Layout and accessibility**
- Added a 10px supporting-text floor and short-projector compaction (`max-height` 840/800/760px) so slides 2, 3, 5, 8, 9, 10, 11, 12, 13, and 14 fit at 1280 × 720 and 1024 × 768. Removed lower-value blocks from dense slides 3, 5, 13, and 14; moved detail to notes.
- Mobile deck scrolls vertically; added `scroll-padding-top` / `scroll-margin-top` so deep links do not hide the heading under the fixed chrome.
- Closed speaker-notes panel is `inert`, `aria-hidden`, and its close button is removed from the tab order.
- Marker positions for slides 6, 9, 12 measured from the captured images; slide 6 marker 4 now points at the 37-vs-24 summary; slide 9 marker 5 points at the precision-guard crop; slide 12 marker 4 points at the cover’s audit-verified line.
- App screenshots are cropped to the relevant region (Workbench/Manifest/Findings/Packet) so text is legible; precision guards and the M-12 row have dedicated legible crops/HTML rows.
- Print CSS no longer inherits mobile width rules; PDF is 16 pages at 1200 × 675 pt with no clipping.

**Assets and validation**
- Recaptured the app set from live `R-DEMO-001`; post-decision set captured on an isolated temporary copy (second loopback Uvicorn), so the live run remains 12 pending / 3 assumptions / 9 events.
- `scripts/capture_demo.py` now supports `--with-decisions`, `--data-source`, and `--deck`, writes `marker-hints.json` and `deck-validation.json`, and regenerates the PDF.
- Validation: 16 slides navigated at 1920×1080, 1440×900, 1280×720, 1024×768, and 390×844; 0 console errors; 0 external requests; 0 desktop clipping/overflow; 0 mobile horizontal overflow; PDF 16 pages.

### Remaining demo risks

1. **No real estate, no human IAA.** The metrics are in-sample synthetic; the reference target is internally authored and AI-assisted. This is disclosed, not solved.
2. **Synthetic realism.** The 300-file fixture contains generated filler and synthetic PCF/product-model/Gosu sketches. It tests evidence discipline, not Guidewire-format fidelity.
3. **Positioning is not an independent product evaluation.** The slide 3 capability map and slide 15 competitor discussion rely on public documentation and search-indexed pages; several vendor pages were rate-limited (429) during the final check.
4. **Packet hashes are capture-time.** Slide 12 shows prefixes and says “read live”; reviewer decisions and packet refresh change the packet hash and audit head.
5. **Post-decision assets are isolated-copy captures.** They are reproducible with the script but are not the live demo run. Do not run `verify-audit` against the bundled static packet.
6. **CUE/Cloud Assurance Services/Lighthouse/SurePath boundaries remain vendor-owned.** PreFlight does not replace them, and the deck now says so explicitly.
7. **PDF/packaging must be regenerated if the app fixes are rebased.** If the app branch changes after this commit, rerun the capture command before presenting.

No score is claimed in this log; the independent reviewer panel decides.
