#!/usr/bin/env python3
"""Capture the PreFlight presentation screenshot set from a running server.

The capture is intentionally read-only against the application: it opens pages,
clicks a spine node, and asks the retrieval-only assistant. It does not upload a
fixture, record a reviewer decision, or restart the server.

Usage:
    python scripts/capture_demo.py
    python scripts/capture_demo.py --base-url http://127.0.0.1:8000 \
        --run-id R-DEMO-001 --out docs/presentation/assets
    python scripts/capture_demo.py --video

The optional video is written next to the screenshots as
``preflight-walkthrough.webm`` and is ignored by git (see assets/.gitignore).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


FOLD = {"width": 1440, "height": 900}
NARROW = {"width": 1280, "height": 900}
MOBILE = {"width": 390, "height": 844}


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
    parser.add_argument("--timeout", type=int, default=30_000,
                        help="Per-action timeout in milliseconds")
    return parser.parse_args()


def slug(path: str) -> str:
    return path.strip("/").replace("/", "-").replace("?", "-") or "root"


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

    def shot(self, name: str, *, full_page: bool = False,
             locator: str | None = None) -> None:
        target = self.out / name
        if locator:
            element = self.page.locator(locator).first
            element.wait_for(state="visible", timeout=self.timeout)
            element.scroll_into_view_if_needed()
            element.screenshot(path=str(target), animations="disabled")
        else:
            self.page.screenshot(path=str(target), full_page=full_page,
                                 animations="disabled")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
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

    def capture_stills(self) -> None:
        print("Workbench")
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-1440x900.png")
        self.shot("workbench-full-1440.png", full_page=True)
        self.page.set_viewport_size(NARROW)
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-1280x900.png")
        self.page.set_viewport_size(FOLD)

        print("Workbench evidence drawer")
        self.open("/?feature=PA-VEH-01&evidence=EV-0001")
        self.shot("workbench-evidence-1440x900.png")
        self.shot("workbench-evidence-panel.png", locator=".evidence-panel")
        self.shot("workbench-evidence-drawer.png", locator=".evidence-drawer")

        print("Manifest excluded filter")
        self.open("/manifest?excluded=1")
        self.shot("manifest-excluded-1440x900.png")
        self.page.set_viewport_size(NARROW)
        self.open("/manifest?excluded=1")
        self.shot("manifest-excluded-1280x900.png")
        self.page.set_viewport_size(FOLD)

        print("Reconstruction")
        self.open("/reconstruction")
        self.shot("reconstruction-1440x900.png")
        self.shot("reconstruction-full-1440.png", full_page=True)

        print("Findings")
        self.open("/findings")
        self.shot("findings-1440x900.png")
        self.shot("findings-full-1440.png", full_page=True)

        print("Assistant citation")
        self.answer("Motorcycle_Ext?", "Motorcycle_Ext appears")
        self.shot("assistant-citation-1440x900.png")
        self.shot("assistant-citation-panel.png", locator=".assistant")

        print("Assistant refusal")
        self.answer("Territory rating?", "Cannot determine")
        self.shot("assistant-refusal-1440x900.png")
        self.shot("assistant-refusal-panel.png", locator=".assistant")

        print("Evaluation")
        self.open("/evaluation")
        self.shot("evaluation-1440x900.png")
        self.shot("evaluation-full-1440.png", full_page=True)
        self.shot("evaluation-intervals.png", locator=".ci-chart")

        print("Review packet")
        self.open("/packet")
        self.shot("packet-1440x900.png")
        self.shot("packet-full-1440.png", full_page=True)

        print("Mobile")
        self.page.set_viewport_size(MOBILE)
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-390x844.png")
        self.shot("workbench-390x844-full.png", full_page=True)

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

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": base,
        "run_id": args.run_id,
        "viewports": {"fold": FOLD, "narrow": NARROW, "mobile": MOBILE},
        "blocked_external_requests": blocked,
        "artifacts": capture.written,
    }
    (out / "capture-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n{len(capture.written)} screenshots -> {out}")
    if blocked:
        print(f"blocked {len(blocked)} external request(s): {blocked}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
