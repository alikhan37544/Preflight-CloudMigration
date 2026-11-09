#!/usr/bin/env python3
"""Capture the PreFlight presentation screenshot set and validate the deck.

Read-only against the live demo run: it opens pages, clicks a spine node, and
asks the retrieval-only assistant. It never uploads a fixture, records a
reviewer decision against the live run, or restarts the server.

The optional ``--with-decisions`` mode copies the seeded run into a temporary
data directory, starts a second loopback Uvicorn, records Accept M-01 and
Reject M-12 there, captures the post-decision screens, and deletes the copy.

The optional ``--deck`` mode captures the 16-slide deck at the required
viewports, writes proof screenshots, validates overflow/console/external
requests, and regenerates ``PreFlight-deck.pdf``.

Examples:
    python scripts/capture_demo.py
    python scripts/capture_demo.py --with-decisions --deck
    python scripts/capture_demo.py --base-url http://127.0.0.1:8000 \
        --run-id R-DEMO-001 --out docs/presentation/assets
    python scripts/capture_demo.py --video
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


REPO = Path(__file__).resolve().parents[1]
FOLD = {"width": 1440, "height": 900}
NARROW = {"width": 1280, "height": 900}
COMPACT = {"width": 1280, "height": 720}
MID = {"width": 1024, "height": 768}
MOBILE = {"width": 390, "height": 844}
FULL_HD = {"width": 1920, "height": 1080}
DECK_VIEWPORTS = (
    ("1920x1080", FULL_HD),
    ("1440x900", FOLD),
    ("1280x720", COMPACT),
    ("1024x768", MID),
    ("390x844", MOBILE),
)
# Content crops used by the deck. The app content starts at x=268 on a 1440 px
# viewport, so every crop keeps a 38 px left margin. That margin is also where
# the numbered markers sit: they must not cover the text they explain. Crops
# end at section boundaries (never in the app footer) and stay inside the
# page content width.
FOCUS_CLIPS = {
    # Summary strip, feature list, and the top of the spine.
    "workbench": {"x": 218, "y": 270, "width": 1212, "height": 630},
    # Excluded banner through pagination; the app footer is outside the crop.
    "manifest": {"x": 218, "y": 200, "width": 1212, "height": 620},
    # Page heading, decision notice, tabs, and M-01..M-03 (post-decision).
    "reconstruction": {"x": 218, "y": 105, "width": 1212, "height": 755},
    # Banner, SBT flag, finding table, and the complete detail panel.
    "findings": {"x": 218, "y": 220, "width": 1212, "height": 1016},
    # Page heading, six section cards, and the first assumption row (A-01).
    "packet": {"x": 218, "y": 95, "width": 1212, "height": 752},
}

# Each crop is checked against the live DOM before it is written. ``full``
# elements must be wholly inside the crop; ``partial`` elements must start
# inside it (their content continues below the crop by design). ``text`` keeps
# the proof honest: if a label moves out of the crop, validation fails.
CROP_SPECS = {
    "workbench": {
        "clip": FOCUS_CLIPS["workbench"],
        "full": [".summary-strip"],
        "partial": [".feature-list", ".spine-panel"],
        "text": {".summary-strip": "EVIDENCE RECORDS", ".feature-list": "PA-VEH-01"},
    },
    "manifest": {
        "clip": FOCUS_CLIPS["manifest"],
        "full": [".banner-warning", ".manifest-table", ".pagination"],
        "text": {
            ".banner-warning": "excluded files",
            ".banner-info": "Source unchanged",
            ".manifest-table": "SHA-256",
        },
    },
    "reconstruction": {
        "clip": FOCUS_CLIPS["reconstruction"],
        "full": [
            ".page-head .eyebrow",
            ".page-head h1",
            "[data-gen-writes]",
            ".banner-info",
            ".tabs",
            '[data-mapping-row="M-01"]',
            '[data-mapping-row="M-03"]',
        ],
        "partial": [".mapping-table"],
        "text": {
            ".page-head .eyebrow": "DECISION QUEUE",
            "[data-gen-writes]": "draft is local",
            ".tabs": "Mappings",
        },
    },
    "findings": {
        "clip": FOCUS_CLIPS["findings"],
        "full": [
            ".readiness-panel",
            ".rule-summary-item",
            ".findings-table tr.selected",
            ".detail-panel",
        ],
        "text": {
            ".readiness-panel": "SBT readiness flag",
            ".findings-table tr.selected": "F-002",
            ".detail-panel": "Finding F-002",
        },
    },
    "packet": {
        "clip": FOCUS_CLIPS["packet"],
        "full": [".packet-sections", '.packet-assumptions-table tbody tr:first-child'],
        "bottom_before": '.packet-assumptions-table tbody tr:nth-child(2)',
        "text": {
            ".page-head .eyebrow": "REVIEW ARTIFACT",
            ".page-head .lede": "6-section packet",
            ".packet-assumptions-table": "A-01",
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="Running PreFlight origin (default: http://127.0.0.1:8000)")
    parser.add_argument("--run-id", default="R-DEMO-001",
                        help="Seeded run to capture (default: R-DEMO-001)")
    parser.add_argument("--out", default="docs/presentation/assets",
                        help="Output directory (default: docs/presentation/assets)")
    parser.add_argument("--video", action="store_true",
                        help="Record a short webm walkthrough (not committed by default)")
    parser.add_argument("--with-decisions", action="store_true",
                        help="Capture post-decision screens on an isolated temporary copy")
    parser.add_argument("--data-source", default="",
                        help="Data directory containing runs/ (default: $PREFLIGHT_DATA_DIR or ./data)")
    parser.add_argument("--deck", action="store_true",
                        help="Capture deck proofs, validate viewports, and render the PDF")
    parser.add_argument("--deck-url", default="",
                        help="URL of the deck; the script starts a local static server when empty")
    parser.add_argument("--timeout", type=int, default=30_000,
                        help="Per-action timeout in milliseconds")
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - operational path
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"server did not become healthy at {url}: {last_error}")


def start_isolated_app(run_id: str, data_source: Path) -> tuple[subprocess.Popen, Path, str]:
    port = free_port()
    temp_root = Path(tempfile.mkdtemp(prefix="preflight-demo-", dir="/tmp/opencode"))
    source = data_source / "runs" / run_id
    if not source.is_dir():
        raise RuntimeError(f"seeded run not found: {source}")
    shutil.copytree(source, temp_root / "data" / "runs" / run_id)
    env = os.environ.copy()
    env.update({
        "PREFLIGHT_DATA_DIR": str(temp_root / "data"),
        "PREFLIGHT_PORT": str(port),
        "PREFLIGHT_SECRET_KEY": "capture-demo-isolated",
    })
    log = (temp_root / "uvicorn.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        wait_health(url)
    except Exception:
        proc.terminate()
        raise
    return proc, temp_root, url


def stop_isolated_app(proc: subprocess.Popen, temp_root: Path) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    shutil.rmtree(temp_root, ignore_errors=True)


class Capture:
    def __init__(self, page: Page, base_url: str, run_id: str, out: Path,
                 timeout: int, blocked: list[str]) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.out = out
        self.timeout = timeout
        self.blocked = blocked
        self.written: list[dict] = []
        self.crop_checks: list[dict] = []
        self.crop_failures: list[dict] = []
        self.facts: dict = {}

    def url(self, path: str) -> str:
        joiner = "&" if "?" in path else "?"
        if path.startswith("/"):
            base = f"{self.base_url}{path}"
        else:
            base = f"{self.base_url}/{path}"
        return f"{base}{joiner}run={self.run_id}"

    def open(self, path: str) -> None:
        self.page.goto(self.url(path), wait_until="networkidle", timeout=self.timeout)
        self.page.wait_for_timeout(250)
        self.page.evaluate("window.scrollTo(0, 0)")

    def wait_for_no_toast(self) -> None:
        """Wait out the app's transient decision toast before any screenshot."""
        self.page.wait_for_function(
            """() => {
                const toast = document.querySelector('[data-toast]');
                return !toast || !toast.classList.contains('visible');
            }""",
            timeout=8_000,
        )

    def shot(self, name: str, *, full_page: bool = False,
             locator: str | None = None,
             clip: dict | None = None) -> None:
        target = self.out / name
        self.wait_for_no_toast()
        if locator:
            element = self.page.locator(locator).first
            element.wait_for(state="visible", timeout=self.timeout)
            element.scroll_into_view_if_needed()
            element.screenshot(path=str(target), animations="disabled")
        elif clip:
            # A document-relative clip lets a crop extend below the viewport.
            self.page.screenshot(path=str(target), clip=clip, full_page=True,
                                 animations="disabled")
        else:
            self.page.screenshot(path=str(target), full_page=full_page,
                                 animations="disabled")
        digest = sha256(target)
        self.written.append({
            "file": name,
            "bytes": target.stat().st_size,
            "sha256": digest,
            "path": self.page.url,
        })
        print(f"  captured {name} ({target.stat().st_size:,} bytes)")

    def answer(self, chip_text: str, expected: str) -> None:
        self.open("/?feature=PA-VEH-01")
        self.page.get_by_role("button", name=chip_text, exact=True).click()
        result = self.page.locator("[data-assistant-result] .answer-block").first
        result.wait_for(state="visible", timeout=self.timeout)
        self.page.wait_for_function(
            "(needle) => document.querySelector('[data-assistant-result]')?.innerText.includes(needle)",
            arg=expected,
            timeout=self.timeout,
        )
        self.page.wait_for_timeout(350)
        self.page.locator(".assistant").scroll_into_view_if_needed()
        self.page.wait_for_timeout(200)

    def check_crop(self, name: str, *, full: tuple[str, ...] = (),
                   partial: tuple[str, ...] = (), text: dict[str, str] | None = None,
                   bottom_before: str | None = None) -> None:
        """Validate a hand-picked crop against the live DOM.

        This is deliberately structural rather than OCR: required elements and
        labels must be inside the crop, while ``partial`` elements are allowed
        to continue below it. It catches a moved section, a footer slice, and a
        left edge that starts inside the content column.
        """
        spec = CROP_SPECS[name]
        clip = spec["clip"]
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(50)
        scroll_y = self.page.evaluate("window.scrollY")
        errors: list[str] = []

        def box(selector: str) -> dict | None:
            locator = self.page.locator(selector).first
            if not locator.count():
                return None
            found = locator.bounding_box()
            if not found:
                return None
            return {**found, "y": found["y"] + scroll_y}

        footer = box("footer")
        if footer and clip["y"] + clip["height"] > footer["y"] + 1:
            errors.append(f"crop extends into app footer at y={footer['y']:.0f}")

        for selector in full:
            found = box(selector)
            if not found:
                errors.append(f"missing full element: {selector}")
                continue
            if (found["x"] < clip["x"] - 1
                    or found["y"] < clip["y"] - 1
                    or found["x"] + found["width"] > clip["x"] + clip["width"] + 1
                    or found["y"] + found["height"] > clip["y"] + clip["height"] + 1):
                errors.append(f"element clipped: {selector} {found}")

        for selector in partial:
            found = box(selector)
            if not found:
                errors.append(f"missing partial element: {selector}")
                continue
            if (found["x"] < clip["x"] - 1 or found["y"] < clip["y"] - 1
                    or found["x"] + found["width"] > clip["x"] + clip["width"] + 1):
                errors.append(f"partial element starts outside crop: {selector} {found}")

        for selector, needle in (text or {}).items():
            locator = self.page.locator(selector).first
            if not locator.count() or needle not in locator.inner_text():
                errors.append(f"label {needle!r} missing from {selector}")

        if bottom_before:
            found = box(bottom_before)
            if not found:
                errors.append(f"missing boundary element: {bottom_before}")
            elif clip["y"] + clip["height"] > found["y"] + 2:
                errors.append(
                    f"crop crosses into next section: bottom={clip['y'] + clip['height']:.0f} "
                    f"{bottom_before} top={found['y']:.0f}"
                )

        result = {
            "name": name,
            "clip": clip,
            "full": list(full),
            "partial": list(partial),
            "bottom_before": bottom_before,
            "ok": not errors,
            "errors": errors,
        }
        self.crop_checks.append(result)
        if errors:
            self.crop_failures.append(result)
            print(f"  crop validation failed: {name}: {errors}")

    def hint(self, label: str, selector: str, clip: dict, *,
             left: float | None = None, top: float | None = None) -> None:
        box = self.page.locator(selector).first.bounding_box()
        if not box:
            return
        scroll_y = self.page.evaluate("window.scrollY")
        # Default: a 20 px margin marker centred in the 38 px left gutter.
        margin_center = clip["x"] + 20
        self.hints[label] = {
            "left": round(left if left is not None
                          else (margin_center - clip["x"]) / clip["width"] * 100, 1),
            "top": round(top if top is not None
                         else (box["y"] + scroll_y + box["height"] / 2 - clip["y"])
                         / clip["height"] * 100, 1),
            "selector": selector,
        }

    def capture_stills(self) -> None:
        self.hints: dict[str, dict] = {}

        print("Workbench")
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-1440x900.png")
        self.check_crop("workbench", full=CROP_SPECS["workbench"]["full"],
                        partial=CROP_SPECS["workbench"].get("partial", ()), text=CROP_SPECS["workbench"].get("text", {}))
        self.shot("workbench-focus-1440x900.png", clip=FOCUS_CLIPS["workbench"])
        self.shot("workbench-full-1440.png", full_page=True)
        # Markers 1 and 4 sit in the thin gap above the summary strip; 2 and 3
        # sit in the left gutter at the row they explain.
        self.hint("slide6.marker1", ".summary-stat", FOCUS_CLIPS["workbench"], left=10, top=0.5)
        self.hint("slide6.marker2", ".feature-row.selected .feature-id", FOCUS_CLIPS["workbench"])
        self.hint("slide6.marker3", ".spine-panel h2", FOCUS_CLIPS["workbench"])
        self.hint("slide6.marker4", ".summary-stat.summary-signal", FOCUS_CLIPS["workbench"], left=78, top=0.5)
        self.page.set_viewport_size(NARROW)
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-1280x900.png")
        self.page.set_viewport_size(COMPACT)
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-1280x720.png")
        self.page.set_viewport_size(FOLD)

        print("Workbench evidence drawer")
        self.open("/?feature=PA-VEH-01&evidence=EV-0001")
        self.shot("workbench-evidence-1440x900.png")
        self.shot("workbench-evidence-panel.png", locator=".evidence-panel")
        self.shot("workbench-evidence-drawer.png", locator=".evidence-drawer")

        print("Manifest excluded filter")
        self.open("/manifest?excluded=1")
        self.shot("manifest-excluded-1440x900.png")
        self.check_crop("manifest", full=CROP_SPECS["manifest"]["full"],
                        partial=CROP_SPECS["manifest"].get("partial", ()), text=CROP_SPECS["manifest"].get("text", {}))
        self.shot("manifest-focus-1440x900.png", clip=FOCUS_CLIPS["manifest"])
        hash_code = self.page.locator(".panel .banner-info code.hash").first
        short_hash = hash_code.inner_text().strip()
        self.facts["snapshot_short"] = short_hash
        # The banner only prints the short form; the API holds the full digest.
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/api/runs/{self.run_id}/manifest", timeout=5
            ) as response:
                self.facts["snapshot_hash"] = json.load(response)["snapshot_hash"]
        except Exception:
            self.facts["snapshot_hash"] = short_hash
        self.hint("slide7.marker1", ".banner-warning strong", FOCUS_CLIPS["manifest"])
        self.hint("slide7.marker2", ".manifest-table tbody td:first-child", FOCUS_CLIPS["manifest"])
        self.hint("slide7.marker3", ".panel .banner-info strong", FOCUS_CLIPS["manifest"])
        self.page.set_viewport_size(NARROW)
        self.open("/manifest?excluded=1")
        self.shot("manifest-excluded-1280x900.png")
        self.page.set_viewport_size(FOLD)

        print("Reconstruction (seed, pre-decision)")
        self.open("/reconstruction")
        self.shot("reconstruction-1440x900.png")
        self.check_crop("reconstruction", full=CROP_SPECS["reconstruction"]["full"],
                        partial=CROP_SPECS["reconstruction"].get("partial", ()), text=CROP_SPECS["reconstruction"].get("text", {}),
                        bottom_before='[data-mapping-row="M-06"]')
        self.shot("reconstruction-focus-1440x900.png", clip=FOCUS_CLIPS["reconstruction"])
        self.shot("reconstruction-full-1440.png", full_page=True)

        print("Findings")
        self.open("/findings")
        self.shot("findings-1440x900.png")
        self.check_crop("findings", full=CROP_SPECS["findings"]["full"],
                        partial=CROP_SPECS["findings"].get("partial", ()), text=CROP_SPECS["findings"].get("text", {}))
        self.shot("findings-focus-1440x900.png", clip=FOCUS_CLIPS["findings"])
        self.hint("slide9.marker1", ".rule-summary-item", FOCUS_CLIPS["findings"])
        self.hint("slide9.marker2", ".findings-table tr.selected", FOCUS_CLIPS["findings"])
        # Marker 3 sits in the 33 px gutter between the table and detail panel.
        self.hint("slide9.marker3", ".detail-panel h2", FOCUS_CLIPS["findings"], left=70.2)
        self.hint("slide9.marker4", ".readiness-panel", FOCUS_CLIPS["findings"])
        self.shot("findings-guards-1440.png", locator=".precision-panel")
        self.shot("findings-guard-query-make.png", locator=".precision-panel .guard-card")
        self.shot("findings-full-1440.png", full_page=True)
        self.page.set_viewport_size(COMPACT)
        self.open("/findings")
        self.shot("findings-1280x720.png")
        self.page.set_viewport_size(FOLD)

        print("Assistant citation")
        self.answer("Motorcycle_Ext?", "Motorcycle_Ext appears")
        self.shot("assistant-citation-1440x900.png")
        self.shot("assistant-citation-panel.png", locator="[data-assistant-transcript]")

        print("Assistant refusal")
        self.answer("Territory rating?", "Cannot determine")
        self.shot("assistant-refusal-1440x900.png")
        self.shot("assistant-refusal-panel.png", locator="[data-assistant-transcript]")

        print("Evaluation")
        self.open("/evaluation")
        self.shot("evaluation-1440x900.png")
        self.shot("evaluation-full-1440.png", full_page=True)
        self.shot("evaluation-intervals.png", locator=".ci-chart")

        print("Review packet (seed, pre-decision)")
        self.open("/packet")
        self.shot("packet-predecision-1440x900.png")
        self.shot("packet-predecision-focus-1440x900.png", clip=FOCUS_CLIPS["packet"])
        self.shot("packet-predecision-full-1440.png", full_page=True)

        print("Mobile")
        self.page.set_viewport_size(MOBILE)
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-390x844.png")
        self.shot("workbench-390x844-full.png", full_page=True)

    def capture_after_decisions(self, isolated_url: str) -> dict:
        print("Reconstruction (isolated copy, post-decision)")
        self.base_url = isolated_url
        self.page.set_viewport_size(FOLD)
        self.open("/reconstruction")

        def decide(row_id: str, action: str, reason: str, expected_class: str) -> None:
            self.page.locator(
                f'[data-mapping-row="{row_id}"] [data-decision="{action}"]'
            ).click()
            dialog = self.page.locator("[data-decision-dialog]")
            dialog.wait_for(state="visible", timeout=self.timeout)
            self.page.fill("[data-decision-reason]", reason)
            with self.page.expect_response(
                lambda response: "/api/runs/" in response.url
                and response.request.method == "POST"
                and response.url.endswith("/decisions"),
                timeout=self.timeout,
            ):
                self.page.locator("[data-decision-confirm]").click()
            dialog.wait_for(state="hidden", timeout=self.timeout)
            self.page.wait_for_function(
                f"() => document.querySelector('[data-mapping-row=\"{row_id}\"]')?"
                f".classList.contains('{expected_class}')",
                timeout=self.timeout,
            )

        decide("M-01", "accept", "Reviewed against the documented codegen override.", "row-accepted")
        decide("M-12", "reject", "Typelist convention needs a target-release check.", "row-rejected")
        notice = self.page.locator("[data-assumption-notice]")
        notice.wait_for(state="visible", timeout=self.timeout)
        self.page.wait_for_function(
            "() => document.querySelector('[data-assumption-notice]')?.innerText.includes('A-DEC-04')",
            timeout=self.timeout,
        )
        # The toast lasts 4.2 s; wait it out instead of racing it into the crop.
        self.wait_for_no_toast()
        self.page.wait_for_timeout(250)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.check_crop(
            "reconstruction",
            full=(*CROP_SPECS["reconstruction"]["full"], "[data-assumption-notice]"),
            partial=(".mapping-table",),
            text={**CROP_SPECS["reconstruction"]["text"],
                  "[data-assumption-notice]": "A-DEC-04"},
            bottom_before='[data-mapping-row="M-05"]',
        )
        self.shot("reconstruction-after-decision-1440x900.png")
        self.shot("reconstruction-after-decision-focus-1440x900.png",
                  clip=FOCUS_CLIPS["reconstruction"])
        self.hint("slide8.marker1", "[data-assumption-notice] strong", FOCUS_CLIPS["reconstruction"])
        self.hint("slide8.marker2", '[data-mapping-row="M-01"]', FOCUS_CLIPS["reconstruction"])
        self.hint("slide8.marker3", "[data-gen-writes]", FOCUS_CLIPS["reconstruction"])
        self.shot("reconstruction-m12-row.png", locator='[data-mapping-row="M-12"]')
        self.shot("reconstruction-after-decision-full.png", full_page=True)
        self.open("/reconstruction?tab=assumptions")
        self.shot("reconstruction-assumptions-1440x900.png")

        print("Review packet (isolated copy, post-decision)")
        self.open("/packet")
        self.page.wait_for_timeout(400)
        self.check_crop(
            "packet",
            full=CROP_SPECS["packet"]["full"],
            text=CROP_SPECS["packet"]["text"],
            bottom_before=CROP_SPECS["packet"]["bottom_before"],
        )
        cover_codes = self.page.locator(".packet-card:first-child code")
        if cover_codes.count() >= 2:
            self.facts["packet_cover_snapshot"] = cover_codes.nth(0).inner_text().strip()
            self.facts["packet_cover_packet"] = cover_codes.nth(1).inner_text().strip()
        self.shot("packet-1440x900.png")
        self.shot("packet-focus-1440x900.png", clip=FOCUS_CLIPS["packet"])
        self.hint("slide12.marker1", "a.btn-primary", FOCUS_CLIPS["packet"])
        self.hint("slide12.marker2", ".packet-card:first-child h2", FOCUS_CLIPS["packet"])
        self.hint("slide12.marker3", ".packet-card:nth-child(6) h2", FOCUS_CLIPS["packet"])
        self.hint("slide12.marker4", ".packet-card:first-child p:last-of-type", FOCUS_CLIPS["packet"])
        self.shot("packet-full-1440.png", full_page=True)
        return {}

    def record_video(self) -> None:
        print("Video walkthrough")
        self.page.set_viewport_size(FOLD)
        self.open("/?feature=PA-VEH-01")
        self.page.wait_for_timeout(1_000)
        self.page.locator(".spine-node").first.click()
        self.page.wait_for_timeout(1_200)
        self.page.get_by_role("link", name="Manifest", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.locator('input[name="excluded"]').check()
        self.page.get_by_role("button", name="Apply", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1_500)
        self.page.get_by_role("link", name="Reconstruction", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1_500)
        self.page.get_by_role("link", name="Findings", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1_500)
        self.page.get_by_role("link", name="Workbench", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.locator(".assistant").scroll_into_view_if_needed()
        self.page.get_by_role("button", name="Motorcycle_Ext?", exact=True).click()
        self.page.locator("[data-assistant-result] .answer-block").first.wait_for(
            state="visible", timeout=self.timeout
        )
        self.page.wait_for_timeout(1_800)
        self.page.get_by_role("link", name="Evaluation", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1_500)
        self.page.get_by_role("link", name="Review packet", exact=True).click()
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(2_000)


def after_decision_facts(temp_root: Path, run_id: str) -> dict:
    run = temp_root / "data" / "runs" / run_id
    packet = json.loads((run / "packet.json").read_text(encoding="utf-8"))
    assumptions = json.loads((run / "assumptions.json").read_text(encoding="utf-8"))
    audit_lines = sum(1 for _ in (run / "audit.jsonl").open(encoding="utf-8"))
    return {
        "audit_events": audit_lines,
        "assumptions": len(assumptions.get("assumptions", [])),
        "snapshot_hash": packet.get("hashes", {}).get("snapshot"),
        "audit_head": packet.get("audit_head"),
        "packet_hash": packet.get("packet_sha256"),
        "packet_hash_scope": packet.get("hash_scope"),
        "packet_audit_event_count": packet.get("audit_event_count"),
        "packet_assumptions": packet.get("counts", {}).get("assumptions"),
    }


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass


def start_deck_server(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def deck_validation(page: Page, deck_url: str, out: Path) -> dict:
    results: dict = {"viewports": {}, "console_errors": [], "external_requests": []}
    console_errors: list[str] = []
    external: list[str] = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    page.on("request", lambda req: external.append(req.url)
            if urlparse(req.url).hostname not in {"127.0.0.1", "localhost", "::1", None}
            else None)

    for label, viewport in DECK_VIEWPORTS:
        page.set_viewport_size(viewport)
        failures = []
        for index in range(1, 17):
            page.goto(f"{deck_url}/index.html#slide-{index}", wait_until="networkidle")
            page.wait_for_timeout(80)
            active = page.evaluate(
                """() => {
                    const slide = document.querySelector('.slide.is-active');
                    if (!slide) return null;
                    const body = slide.querySelector('.slide-body');
                    const br = body.getBoundingClientRect();
                    let maxBottom = -Infinity, maxRight = -Infinity;
                    body.querySelectorAll('*').forEach((el) => {
                        const style = getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return;
                        const r = el.getBoundingClientRect();
                        if (!r.width || !r.height) return;
                        maxBottom = Math.max(maxBottom, r.bottom);
                        maxRight = Math.max(maxRight, r.right);
                    });
                    return {
                        id: slide.id,
                        counter: document.getElementById('counter')?.innerText,
                        overflowBottom: Math.round(maxBottom - br.bottom),
                        overflowRight: Math.round(maxRight - br.right),
                        docWidth: document.documentElement.scrollWidth,
                        innerWidth: window.innerWidth,
                        bodyScrollHeight: body.scrollHeight,
                        bodyClientHeight: body.clientHeight,
                        mobile: window.matchMedia('(max-width: 900px)').matches,
                    };
                }"""
            )
            if not active or active["id"] != f"slide-{index}":
                failures.append({"slide": index, "reason": "navigation"})
                continue
            if viewport["width"] > 900:
                if active["overflowBottom"] > 2 or active["overflowRight"] > 2:
                    failures.append({"slide": index, "reason": "clip", **active})
            else:
                if active["docWidth"] > active["innerWidth"] + 1:
                    failures.append({"slide": index, "reason": "horizontal", **active})
        results["viewports"][label] = {"failures": failures, "slides": 16}

        if viewport == FULL_HD:
            # The stage-label column is fixed at 82 px on smaller screens; at
            # 1920 the label floor grows and can collide with the wrapped text.
            page.goto(f"{deck_url}/index.html#slide-4", wait_until="networkidle")
            page.wait_for_timeout(80)
            overlaps = page.evaluate(
                """() => Array.from(document.querySelectorAll('#slide-4 .stage-item')).map((item) => {
                    const label = item.querySelector('b').getBoundingClientRect();
                    const text = item.querySelector('span').getBoundingClientRect();
                    return {label: item.querySelector('b').innerText,
                            overlap: Math.round(label.right - text.left)};
                }).filter((row) => row.overlap > 1)"""
            )
            results.setdefault("layout_checks", {})["stage_labels_1920"] = {
                "overlaps": overlaps,
                "ok": not overlaps,
            }
            if overlaps:
                failures.append({"slide": 4, "reason": "stage-label-overlap", "overlaps": overlaps})

        if viewport == MOBILE:
            page.goto(f"{deck_url}/index.html#slide-3", wait_until="networkidle")
            page.wait_for_timeout(80)
            matrix = page.evaluate(
                """() => {
                    const region = document.querySelector('.matrix-wrap');
                    if (!region) return null;
                    return {
                        tabindex: region.getAttribute('tabindex'),
                        role: region.getAttribute('role'),
                        label: region.getAttribute('aria-label'),
                        scrollWidth: region.scrollWidth,
                        clientWidth: region.clientWidth,
                    };
                }"""
            )
            results.setdefault("accessibility", {})["mobile_matrix"] = matrix
            if (not matrix or matrix.get("tabindex") != "0"
                    or matrix.get("role") != "region"
                    or matrix.get("scrollWidth", 0) <= matrix.get("clientWidth", 0)):
                failures.append({"slide": 3, "reason": "mobile-matrix-not-focusable", "matrix": matrix})

        if viewport in (FOLD, COMPACT):
            for index in range(1, 17):
                page.goto(f"{deck_url}/index.html#slide-{index}", wait_until="networkidle")
                page.wait_for_timeout(80)
                page.screenshot(path=str(out / f"deck-slide-{index:02d}-{label}.png"),
                                animations="disabled")
        elif viewport in (MID, MOBILE):
            for index in (1, 3, 5, 6, 9, 11, 12, 13, 14, 16):
                page.goto(f"{deck_url}/index.html#slide-{index}", wait_until="networkidle")
                page.wait_for_timeout(80)
                page.screenshot(path=str(out / f"deck-slide-{index:02d}-{label}.png"),
                                full_page=viewport is MOBILE, animations="disabled")

    results["console_errors"] = console_errors
    results["external_requests"] = external
    results["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return results


def render_pdf(page: Page, deck_url: str, out: Path) -> dict:
    page.goto(f"{deck_url}/index.html#slide-1", wait_until="networkidle")
    page.emulate_media(media="print")
    pdf_path = out.parent / "PreFlight-deck.pdf"
    page.pdf(path=str(pdf_path), print_background=True, prefer_css_page_size=True,
             margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    page.emulate_media(media="screen")
    info = {"pdf": str(pdf_path), "bytes": pdf_path.stat().st_size,
            "sha256": sha256(pdf_path), "pages": None, "page_size": None}
    try:
        text = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True)
        match = re.search(r"^Pages:\s+(\d+)", text, re.MULTILINE)
        if match:
            info["pages"] = int(match.group(1))
        match = re.search(r"^Page size:\s+(.+)$", text, re.MULTILINE)
        if match:
            info["page_size"] = match.group(1).strip()
    except Exception as exc:  # pragma: no cover - operational path
        info["pdfinfo_error"] = str(exc)
    return info


def validate_deck_content(deck_path: Path, facts: dict) -> dict:
    """Keep visible deck hashes and hash-scope language aligned with the run.

    Slide 7 keeps one visible value: the fixture snapshot hash. It is stable
    across reviewer actions and appears in the immutability banner. Slide 12
    must not quote the packet or audit head, because both change per capture;
    it may show only the snapshot hash and must label the rest "read live".
    """
    html = deck_path.read_text(encoding="utf-8")
    failures: list[str] = []

    def section(number: int) -> str:
        start = html.find(f'id="slide-{number}"')
        end = html.find(f'id="slide-{number + 1}"') if number < 16 else len(html)
        if start < 0 or end < 0:
            failures.append(f"slide-{number}: section not found")
            return ""
        return html[start:end]

    snapshot = str(facts.get("snapshot_hash") or "").strip()
    snapshot_short = str(facts.get("snapshot_short") or snapshot[:12]).strip()
    if len(snapshot) < 12:
        failures.append("snapshot hash was not captured from the manifest")
    slide7 = section(7)
    slide12 = section(12)
    slide5 = section(5)

    if snapshot_short and snapshot_short not in slide7:
        failures.append(
            f"slide-7 snapshot prefix {snapshot_short!r} does not match the captured manifest hash"
        )

    # Slide 7 keeps one immutable snapshot value and must not retain a stale
    # fixture hash from an earlier capture.
    stale_hashes = {"20b5a25451f3"}
    for stale in stale_hashes:
        if stale in slide7:
            failures.append(f"slide-7 retains stale snapshot hash {stale}")

    # Slide 12 may not hard-code packet/audit values. Only the stable snapshot
    # digest is allowed to appear there; all other values are "read live".
    hex_values = set(re.findall(r"\b[0-9a-f]{12,64}\b", slide12))
    allowed = {snapshot_short, snapshot}
    unexpected = sorted(value for value in hex_values if value not in allowed)
    if unexpected:
        failures.append(f"slide-12 hard-codes capture-time hash value(s): {unexpected}")
    if slide12.count("read live") < 2:
        failures.append("slide-12 does not label packet/audit values as read live")
    if "rendered packet HTML" not in slide12:
        failures.append("slide-12 does not state that the packet hash covers rendered HTML")
    if "packet_json" not in slide12:
        failures.append("slide-12 does not distinguish the packet_json digest")
    if "content digests" not in slide12.lower():
        failures.append("slide-12 does not mention content digests")
    if "audit head" not in slide12.lower():
        failures.append("slide-12 does not mention the audit head")
    if "reviewer actions" not in slide12.lower():
        failures.append("slide-12 does not warn that hashes change with reviewer actions")
    if "rendered packet HTML" not in slide5:
        failures.append("slide-5 does not state that the packet hash covers rendered HTML")
    if "packet_json" not in slide5:
        failures.append("slide-5 does not distinguish the packet_json digest")
    if "content digests" not in slide5.lower():
        failures.append("slide-5 does not mention content digests")

    try:
        source = str(deck_path.relative_to(REPO))
    except ValueError:
        source = str(deck_path)
    return {
        "ok": not failures,
        "failures": failures,
        "snapshot_short": snapshot_short,
        "source": source,
    }


def main() -> int:
    args = parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    host = urlparse(base).hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"refusing non-loopback base URL: {base}", file=sys.stderr)
        return 2

    blocked: list[str] = []
    video_dir = out / "_video"
    isolated: tuple[subprocess.Popen, Path, str] | None = None
    deck_server = None
    deck_url = args.deck_url.rstrip("/")
    summary: dict = {}
    data_source = Path(args.data_source) if args.data_source else Path(
        os.environ.get("PREFLIGHT_DATA_DIR", str(REPO / "data"))
    )
    try:
        if args.with_decisions:
            isolated = start_isolated_app(args.run_id, data_source)
        if args.deck and not deck_url:
            deck_server, deck_url = start_deck_server(REPO / "docs" / "presentation")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context_args: dict = {
                "viewport": FOLD,
                "device_scale_factor": 1,
                "reduced_motion": "reduce",
                "color_scheme": "light",
            }
            if args.video:
                video_dir.mkdir(parents=True, exist_ok=True)
                context_args["record_video_dir"] = str(video_dir)
                context_args["record_video_size"] = {"width": 1280, "height": 720}
            context = browser.new_context(**context_args)
            page = context.new_page()
            page.set_default_timeout(args.timeout)

            def guard(route):
                parsed = urlparse(route.request.url)
                if parsed.scheme in {"http", "https"} and parsed.hostname not in {
                    "127.0.0.1", "localhost", "::1"
                }:
                    blocked.append(route.request.url)
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", guard)
            capture = Capture(page, base, args.run_id, out, args.timeout, blocked)
            capture.capture_stills()
            after_facts = {}
            if args.with_decisions and isolated:
                capture.capture_after_decisions(isolated[2])
                after_facts = after_decision_facts(isolated[1], args.run_id)
            if args.deck:
                validation = deck_validation(page, deck_url, out)
                summary["deck_validation"] = validation
                summary["pdf"] = render_pdf(page, deck_url, out)
                summary["content_validation"] = validate_deck_content(
                    REPO / "docs" / "presentation" / "index.html", capture.facts
                )
            if args.video:
                capture.record_video()
                video = page.video
                context.close()
                if video:
                    source = Path(video.path())
                    target = out / "preflight-walkthrough.webm"
                    shutil.move(str(source), str(target))
                    print(f"  recorded preflight-walkthrough.webm ({target.stat().st_size:,} bytes)")
            else:
                context.close()
            browser.close()

        (out / "marker-hints.json").write_text(
            json.dumps(capture.hints, indent=2) + "\n", encoding="utf-8"
        )
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base_url": base,
            "run_id": args.run_id,
            "viewports": {"fold": FOLD, "narrow": NARROW, "compact": COMPACT,
                          "mid": MID, "mobile": MOBILE},
            "blocked_external_requests": blocked,
            "after_decision": after_facts,
            "content_facts": capture.facts,
            "crop_checks": capture.crop_checks,
            "crop_failures": capture.crop_failures,
            "artifacts": capture.written,
        }
        (out / "capture-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if args.deck:
            (out / "deck-validation.json").write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
        print(f"\n{len(capture.written)} screenshots -> {out}")
        if args.deck:
            print(f"deck validation -> {out / 'deck-validation.json'}")
            print(f"pdf -> {summary.get('pdf')}")
        failures: list[str] = []
        if capture.crop_failures:
            failures.append(f"{len(capture.crop_failures)} crop validation failure(s)")
        if args.deck:
            viewport_failures = {
                label: len(result["failures"])
                for label, result in summary["deck_validation"]["viewports"].items()
                if result["failures"]
            }
            if viewport_failures:
                failures.append(f"deck viewport failures: {viewport_failures}")
            if summary["deck_validation"]["console_errors"]:
                failures.append("deck console errors")
            if summary["deck_validation"]["external_requests"]:
                failures.append("deck external requests")
            content = summary.get("content_validation", {})
            if content.get("failures"):
                failures.append(f"deck content validation: {content['failures']}")
            pdf = summary.get("pdf", {})
            if pdf.get("pages") != 16:
                failures.append(f"PDF page count is {pdf.get('pages')}, expected 16")
            if pdf.get("page_size") and not pdf["page_size"].startswith("1200 x 675"):
                failures.append(f"PDF page size is {pdf['page_size']}, expected 1200 x 675")
        if blocked:
            failures.append(f"blocked {len(blocked)} external request(s): {blocked}")
        if failures:
            for failure in failures:
                print(f"validation failure: {failure}", file=sys.stderr)
            return 1
        return 0
    finally:
        if isolated:
            stop_isolated_app(isolated[0], isolated[1])
        if deck_server:
            deck_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
