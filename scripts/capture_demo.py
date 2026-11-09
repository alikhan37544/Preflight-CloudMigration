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
# Content crops used by the deck. Keeping the app chrome out of the crop makes
# the text legible on a projector and keeps annotation coordinates stable.
FOCUS_CLIPS = {
    "workbench": {"x": 272, "y": 285, "width": 1144, "height": 615},
    "manifest": {"x": 272, "y": 220, "width": 1144, "height": 680},
    "reconstruction": {"x": 272, "y": 110, "width": 1144, "height": 790},
    "findings": {"x": 272, "y": 230, "width": 1144, "height": 670},
    "packet": {"x": 272, "y": 110, "width": 1144, "height": 700},
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
             locator: str | None = None,
             clip: dict | None = None) -> None:
        target = self.out / name
        if locator:
            element = self.page.locator(locator).first
            element.wait_for(state="visible", timeout=self.timeout)
            element.scroll_into_view_if_needed()
            element.screenshot(path=str(target), animations="disabled")
        elif clip:
            self.page.screenshot(path=str(target), clip=clip, animations="disabled")
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

    def hint(self, label: str, selector: str, clip: dict) -> None:
        box = self.page.locator(selector).first.bounding_box()
        if not box:
            return
        scroll_y = self.page.evaluate("window.scrollY")
        self.hints[label] = {
            "left": round((box["x"] + box["width"] / 2 - clip["x"]) / clip["width"] * 100, 1),
            "top": round((box["y"] + scroll_y + box["height"] / 2 - clip["y"]) / clip["height"] * 100, 1),
            "selector": selector,
        }

    def capture_stills(self) -> None:
        self.hints: dict[str, dict] = {}

        print("Workbench")
        self.open("/?feature=PA-VEH-01")
        self.shot("workbench-1440x900.png")
        self.shot("workbench-focus-1440x900.png", clip=FOCUS_CLIPS["workbench"])
        self.shot("workbench-full-1440.png", full_page=True)
        self.hint("slide6.marker1", ".summary-stat", FOCUS_CLIPS["workbench"])
        self.hint("slide6.marker2", ".feature-row.selected .feature-id", FOCUS_CLIPS["workbench"])
        self.hint("slide6.marker3", ".spine-panel h2", FOCUS_CLIPS["workbench"])
        self.hint("slide6.marker4", ".summary-stat.summary-signal", FOCUS_CLIPS["workbench"])
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
        self.shot("manifest-focus-1440x900.png", clip=FOCUS_CLIPS["manifest"])
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
        self.shot("reconstruction-focus-1440x900.png", clip=FOCUS_CLIPS["reconstruction"])
        self.shot("reconstruction-full-1440.png", full_page=True)

        print("Findings")
        self.open("/findings")
        self.shot("findings-1440x900.png")
        self.shot("findings-focus-1440x900.png", clip=FOCUS_CLIPS["findings"])
        self.hint("slide9.marker1", ".rule-summary-item", FOCUS_CLIPS["findings"])
        self.hint("slide9.marker2", ".findings-table tr.selected", FOCUS_CLIPS["findings"])
        self.hint("slide9.marker3", ".detail-panel h2", FOCUS_CLIPS["findings"])
        self.hint("slide9.marker4", ".readiness-row strong", FOCUS_CLIPS["findings"])
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
        with self.page.expect_response(
            lambda response: "/api/runs/" in response.url
            and response.request.method == "POST"
            and response.url.endswith("/decisions")
        ):
            self.page.locator('[data-mapping-row="M-01"] [data-decision="accept"]').click()
        self.page.wait_for_function(
            "() => document.querySelector('[data-mapping-row=\"M-01\"]')?.classList.contains('row-accepted')",
            timeout=self.timeout,
        )
        with self.page.expect_response(
            lambda response: "/api/runs/" in response.url
            and response.request.method == "POST"
            and response.url.endswith("/decisions")
        ):
            self.page.locator('[data-mapping-row="M-12"] [data-decision="reject"]').click()
        self.page.wait_for_function(
            "() => document.querySelector('[data-mapping-row=\"M-12\"]')?.classList.contains('row-rejected')",
            timeout=self.timeout,
        )
        notice = self.page.locator("[data-assumption-notice]")
        notice.wait_for(state="visible", timeout=self.timeout)
        self.page.wait_for_function(
            "() => document.querySelector('[data-assumption-notice]')?.innerText.includes('A-DEC-04')",
            timeout=self.timeout,
        )
        self.page.wait_for_timeout(2500)
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
        if blocked:
            print(f"blocked {len(blocked)} external request(s): {blocked}", file=sys.stderr)
            return 1
        return 0
    finally:
        if isolated:
            stop_isolated_app(isolated[0], isolated[1])
        if deck_server:
            deck_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
