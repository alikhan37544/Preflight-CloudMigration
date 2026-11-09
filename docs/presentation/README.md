# PreFlight presentation package

A self-contained, offline 16-slide deck for judges, academics, and technical reviewers. It explains the migration problem, the evidence model, the live demo, the evaluation, the engineering hardening, the prior art, and the honest viability case.

**Open:** <http://127.0.0.1:8090/index.html> after starting the local server below.

The deck has no external fonts, scripts, styles, CDNs, analytics, or network calls. It loads only local files from this directory. The application screenshots are in `assets/`.

---

## Run it

From the repository root:

```bash
python -m http.server 8090 -d docs/presentation
```

Then open:

```text
http://127.0.0.1:8090/index.html
```

The deck also works by opening `docs/presentation/index.html` directly in a modern browser, but a local HTTP server is recommended so deep links and asset paths behave consistently.

`python` must be Python 3 on the machine; the repository’s shared venv also works:

```bash
/home/understressengineer/programming/Preflight-CloudMigration/.venv/bin/python \
  -m http.server 8090 -d docs/presentation
```

Stop the server with `Ctrl+C`.

## Controls

| Input | Action |
|---|---|
| `→` `↓` `Space` `PageDown` | Next slide |
| `←` `↑` `PageUp` | Previous slide |
| `Home` / `End` | First / last slide |
| `n` | Toggle substantive speaker notes |
| `?` | Open / close the keyboard help dialog |
| `Esc` | Close help or notes |
| `p` (or the **PDF** button) | Print / save as PDF |
| Swipe left / right | Next / previous on touch screens |

Deep links use `#slide-1` … `#slide-16`, for example:

```text
http://127.0.0.1:8090/index.html#slide-11
```

The current slide is reflected in the address bar; pasting the URL opens that slide.

## Print or save as PDF

The print stylesheet is designed for one 16:9 slide per page.

1. Open the deck.
2. Press `p` or click **PDF**.
3. Choose **Landscape**, **Background graphics: on**, **Margins: none**.
4. Save as PDF.

The stylesheet sets `@page { size: 1600px 900px; margin: 0; }` and prints every slide on its own page. A headless check produced **16 pages at 1200 × 675 pt** (16:9) with all screenshots and charts present. A pre-rendered copy is included as `PreFlight-deck.pdf`.

## File map

| Path | Purpose |
|---|---|
| `index.html` | The complete deck: inline custom CSS, inline JS, 16 slides, speaker notes, help, print CSS. No external dependencies. |
| `PreFlight-deck.pdf` | Rendered 16-page, 16:9 PDF of the current deck (1200 × 675 pt per page). |
| `README.md` | This file. |
| `DEMO-RUNBOOK.md` | Exact five-minute live demo script, setup, fallbacks, Q&A, claims to avoid, URLs. |
| `sources.md` | Verified public sources, access dates, gated items, prior-art citations. |
| `evidence.json` | Machine-readable slide data, run counts, metrics, hashes, and source list. |
| `assets/workbench-1440x900.png` | Workbench fold at 1440 × 900. |
| `assets/workbench-1280x900.png` | Workbench fold at 1280 × 900. |
| `assets/workbench-full-1440.png` | Full-page Workbench for annotation/reference. |
| `assets/workbench-390x844.png` | Mobile Workbench viewport at 390 × 844. |
| `assets/workbench-390x844-full.png` | Full-page mobile Workbench. |
| `assets/workbench-evidence-1440x900.png` | Workbench scrolled to the evidence drawer. |
| `assets/workbench-evidence-panel.png` | Evidence + assistant panel crop. |
| `assets/workbench-evidence-drawer.png` | EV-0001 evidence card crop. |
| `assets/manifest-excluded-1440x900.png` | Manifest filtered to the four excluded files. |
| `assets/manifest-excluded-1280x900.png` | Same filter at 1280 × 900. |
| `assets/reconstruction-1440x900.png` | Reconstruction in the read-only demo state. |
| `assets/reconstruction-after-decision-1440x900.png` | Reconstruction after M-01 accept + M-12 reject, showing A-DEC-04. Captured on an isolated copy of the run. |
| `assets/reconstruction-assumptions-1440x900.png` | Assumption register after the reject. |
| `assets/findings-1440x900.png` | Findings with the selected ERR00-G row and SBT flag. |
| `assets/assistant-citation-1440x900.png` | Assistant with the Motorcycle_Ext cited answer. |
| `assets/assistant-citation-panel.png` | Citation card crop used on slide 10. |
| `assets/assistant-refusal-1440x900.png` | Assistant with the territory refusal. |
| `assets/assistant-refusal-panel.png` | Refusal crop used on slide 10. |
| `assets/evaluation-1440x900.png` | Evaluation summary and metric cards. |
| `assets/evaluation-intervals.png` | The application’s interval chart crop. |
| `assets/packet-1440x900.png` | Review packet. |
| `assets/deck-slide-01-1440x900.png` | Validation proof: deck slide 1 rendered at 1440 × 900. |
| `assets/deck-slide-11-1440x900.png` | Validation proof: deck slide 11 rendered at 1440 × 900. |
| `assets/capture-manifest.json` | Capture timestamp, URLs, sizes, and SHA-256 for each application screenshot. |
| `assets/.gitignore` | Keeps generated `.webm` walkthroughs local. |

All application screenshots are from run `R-DEMO-001` (`demo-slice-300`) on 2026-11-09. The main set is live from `http://127.0.0.1:8000`; the reconstruction after-action shot uses an isolated copy so the demo run stays read-only. The packet/audit hashes shown on slide 12 are from the capture; re-read them from the live screen before quoting, because reviewer decisions — and the packet refresh itself — change them.

## Refresh the screenshots

Start the application server first (see `docs/DEMO-SCRIPT.md` or `Makefile`):

```bash
make demo
curl -s http://127.0.0.1:8000/api/health
```

From the repository root, with the shared venv:

```bash
/home/understressengineer/programming/Preflight-CloudMigration/.venv/bin/python \
  scripts/capture_demo.py \
  --base-url http://127.0.0.1:8000 \
  --run-id R-DEMO-001 \
  --out docs/presentation/assets
```

The script captures the 1440 × 900 set, the 1280 × 900 Workbench/Manifest set, the full-page Workbench, the mobile viewport, the assistant crops, and the evaluation chart. It blocks non-loopback requests and writes `capture-manifest.json`. It is read-only against the application: it does not upload, accept/reject, or restart anything.

Optional short walkthrough:

```bash
/home/understressengineer/programming/Preflight-CloudMigration/.venv/bin/python \
  scripts/capture_demo.py --video
```

This writes `docs/presentation/assets/preflight-walkthrough.webm`; it is git-ignored and should not be committed by default.

The after-decision reconstruction shot is deliberately **not** produced by the default capture script. To reproduce it without touching the demo run, copy a seeded run directory to a temporary `PREFLIGHT_DATA_DIR`, start a second Uvicorn on another loopback port, accept `M-01`, reject `M-12`, and capture the banner. The live run should remain at 12 pending dispositions.

## Slide map

| # | Slide | Purpose |
|---:|---|---|
| 1 | Title | Evidence before the estimate; boundaries and packet preview. |
| 2 | The problem | Estimate vs inventory, four questions, four sourced pain points. |
| 3 | Why tools leave a gap | Capability map across Cloud Assurance, CUE, SonarQube/GoQu, CAST/ADDI/AWS, SIs. |
| 4 | Solution | Nine-stage pipeline, invariants, run facts, artifact writes. |
| 5 | Evidence model | Claim anatomy, claim-strength ladder, assumption register, hash chain. |
| 6 | Demo: Workbench | 31/12/4/2/11, 37 vs 24, 3 estate gaps, click node → evidence. |
| 7 | Demo: Manifest | 4 excluded files named with reasons; source hash unchanged. |
| 8 | Demo: Reconstruction | 12 dispositions; M-01 accept; M-12 reject → A-DEC-04; `_gen` writes 0. |
| 9 | Demo: Findings | 24 findings / 8 rules; claim strength; verified IDs; 24 hard negatives silent. |
| 10 | Demo: Assistant | Territory refusal; Motorcycle_Ext citation; retrieval-only, model off. |
| 11 | Demo: Evaluation | M1–M6, intervals, baselines, holdout, limitations. |
| 12 | Demo: Packet | 126 evidence, 9 audit events, packet/audit hashes, verify command. |
| 13 | Engineering rigor | 330 tests, Playwright, frozen hashes, security, flaws found and fixed. |
| 14 | Novelty & prior art | Feature location, traceability, Reversa, GSN, honest scorecard. |
| 15 | Viability | Kill risks, defensible wedge, proposed acceptance tests, roadmap. |
| 16 | Close | The three-line standard and the ask. |

## Accessibility and quality notes

- Semantic `h1`/`h2` headings, labelled slide regions, skip link, visible focus rings, `aria-live` slide announcements, and reduced-motion support.
- Keyboard navigation works without a mouse; the help dialog traps focus while open and returns focus on close.
- Screenshots have descriptive `alt` text; numbered callouts are supplemented by a text legend, not colour alone.
- Charts are inline SVG with a text caption and equivalent numbers in the surrounding slide.
- Validation was run with Playwright at 1920 × 1080, 1440 × 900, and 390 × 844: 16 slides navigated, zero console errors, zero external requests, zero horizontal overflow. Print produced 16 pages. See `evidence.json` for the recorded validation summary.
- Repository checks on 2026-11-09: `pytest -q` — **330 passed**; `scripts/claims_lint.py` — **OK**; `preflight verify-audit R-DEMO-001` — **OK (9 events)**.

## Boundaries

This is an independent academic research prototype. It is not affiliated with, endorsed by, sponsored by, or certified by Guidewire Software, Inc. Fixtures are synthetic. Official Cloud Assurance was not run. Findings are pattern-based heuristics, not official Cloud Standards checks, and are not legal, security, or compliance advice. The Cloud API extension draft is local and non-deployable; it is not compiled or tenant-validated. Impact ranges are heuristic planning ranges, not quotes.
