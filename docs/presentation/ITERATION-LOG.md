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

## Loop 2 — Hash scope, crops, and marker legibility (9 Nov 2026)

**Branch:** `demo2/deck`, cut from `feat/deep-review-demo` HEAD `b7d0303`. Only `docs/presentation/**` and `scripts/capture_demo.py` were changed. App/content fixes remain owned by the parallel app branch.

### What changed

**Hash consistency and scope**
- Slide 7 now shows `668872420dfb`, the fixture snapshot hash in the live immutability banner; the stale `20b5a25451f3` value is gone. The capture script reads the banner (`title` / short code text) and validates that the visible slide-7 prefix matches the captured manifest hash.
- Slide 12 no longer hard-codes packet/audit values. It shows `packet`, `packet_json`, and `audit head` as **read live**, keeps only the stable snapshot digest, and carries a visible note that reviewer actions and packet refresh change the other values.
- Packet hash scope is corrected on slides 5 and 12 and in the runbook: the main packet hash covers **rendered packet HTML** (hash fields normalized); `packet_json` covers **canonical packet JSON**; content digests bind findings, mappings, and evidence; the audit head covers the event chain. `evidence.json` now carries `packet_hash_scope` and capture-time examples with explicit labels.
- `capture-manifest.json`, `evidence.json`, the runbook, README, and regenerated PDF now agree on the snapshot hash, post-decision counts, and PDF hash/bytes.

**Crops and evidence**
- Focus crops now start at `x=218` (50 px app gutter) and end at section boundaries. Coordinates used by `scripts/capture_demo.py`:
  - Workbench: `x=218 y=270 w=1212 h=630`
  - Manifest: `x=218 y=200 w=1212 h=620` (ends after pagination, before the app footer)
  - Reconstruction: `x=218 y=105 w=1212 h=748` (ends cleanly before M-04; M-12 below the fold is labelled schematic)
  - Findings: `x=218 y=220 w=1212 h=1000` (includes the complete Finding F-002 detail panel)
  - Packet: `x=218 y=95 w=1212 h=772` (page header, six cards, and complete A-01 register row; no mid-row cut)
- The decision toast is waited out before capture; the M-12 panel is visibly labelled “Schematic · M-12 row below the crop.” Slide 12’s caption now says the crop shows the assumption-register summary (A-01) and that the live register has four rows including A-DEC-04.
- `capture_demo.py` now validates each crop against the live DOM: required elements must be wholly inside the crop, partial regions must start inside it, the next section must not be crossed, and the app footer must stay outside. Six checks passed; failures are recorded in `capture-manifest.json` and make the script exit non-zero.

**Markers and layout**
- Overlay markers were removed from slides 6, 8, 9, and 12. Callout numbers are text-only; no bubble obscures the evidence it explains. `marker-hints.json` is retained only as a capture-debug artifact.
- Slide 9 gets a wider evidence column and a short-projector column ratio so the complete detail panel stays visible at 1440 × 900, 1280 × 720, and 1024 × 768.
- Slide 4’s stage-label column switches to `max-content` at ≥1600 px; validated at 1920 × 1080 with no label/text overlap.
- Slide 3 splits **CAST/ADDI** (portfolio and code discovery) from **Syntra ETL** (data migration/extraction), softens “files nobody classified” to “files that were never classified,” and compacts at 720/768 so the extra row does not clip.
- Slide 12’s dark hash-block labels now use `#AFC4CF`; `.title-meta`, `.dot-label`, and `.pipe-num` were darkened through `--muted-2: #52636F`; the `.kicker` is included in the 10 px floor. The 390 capability matrix is a labelled `tabindex="0"` scroll region.

### Validation (current capture)

- Deck: 16/16 slides navigated at **1920×1080, 1440×900, 1280×720, 1024×768, 390×844**; **0 failures**, 0 console errors, 0 external requests; mobile matrix focusable; no 1920 stage-label overlap.
- Crop checks: **0 failures** in `capture-manifest.json` (workbench, manifest, reconstruction pre/post, findings, packet).
- Content check: **ok** — slide-7 snapshot prefix matches the manifest; slide-12 packet/audit values are read-live; scope language present on slides 5 and 12.
- PDF: **16 pages, 1200 × 675.12 pt**; SHA-256 and byte count are recorded in `evidence.json` and `deck-validation.json` after each capture (currently `51cd25f3…`, 912,318 bytes).
- `evidence.json` and `capture-manifest.json` regenerated from the same run.

### Remaining risks / final recapture

1. **App/content merge changes screens.** These captures are from the current live `127.0.0.1:8000` build after Loop 4. If the parallel app/content branch changes any captured screen, rerun:
   ```bash
   /home/understressengineer/programming/Preflight-CloudMigration/.venv/bin/python \
     scripts/capture_demo.py --base-url http://127.0.0.1:8000 \
     --run-id R-DEMO-001 --out docs/presentation/assets \
     --data-source /home/understressengineer/programming/Preflight-CloudMigration/data \
     --with-decisions --deck
   ```
   Then regenerate `evidence.json` PDF/asset hashes from the new PDF; the deck text/CSS should not need changes.
2. **Packet/audit values remain capture-time.** That is deliberate: the deck no longer quotes them. Every isolated capture produced a different packet hash, which is why only the immutable fixture snapshot is visible.
3. **Post-decision assets are isolated-copy captures.** They are reproducible with `--with-decisions`, but are not the live run. Do not verify the bundled static packet against them.
4. **No real estate or human IAA.** The evaluation remains in-sample synthetic; this loop changes presentation evidence, not the underlying evidential limits.
5. **Source IDs.** S-18/S-19 were rechecked against `sources.md`; both currently resolve to the same Guidewire Personal Auto and Sonar rows (no swap). The slide-3 footnote cites S-05–S-07 and S-19–S-24, matching the adjacent-tool rows it describes.

No score is claimed in this log; the independent reviewer panel decides.

## Loop 4 — Independent panel reaches the 8/10 bar (10 Nov 2026)

| Reviewer | Loop 3 | Loop 4 | Basis |
|---|---:|---:|---|
| Judge / demo | 7.0 | **8.0** | Full script works on a copied run; seed intact; no blockers |
| UX / accessibility | 7.5 | **8.2** | 0 axe violations, 1280/390 layouts clean, dialogs and packet export semantics fixed |
| Guidewire domain | 6.0 | **8.5** | ERR00-G, A-03, CUE, APD-conversion scope, GarageLocation_Ext, and verify-packet all corrected |
| Engineering | 7.5 | **8.0** | 418 tests, 92/92 asset hashes, PDF hash, packet tamper/audit checks, seed state |

## Loop 5 — Residual polish (no new review round)

- Removed all overlay callout markers; callouts are text-only and never cover evidence.
- Crop validator now checks every declared full/partial element; capture manifest reports 0 crop failures.
- Deck slide 9 and 12 get short-viewport guards; all five viewports validate with 0 failures.
- Mobile capability matrix scrolls with keyboard/touch without advancing the slide.
- Findings standard IDs are no longer truncated; connector arrows meet contrast.
- `evidence.json` run hashes are synchronized with the capture manifest and live seed packet.
- Final counts: **418 tests**, packet verify OK, audit verify OK, 18/18 freeze hashes, 16-page PDF.
