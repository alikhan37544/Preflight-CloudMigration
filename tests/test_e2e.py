"""Playwright golden path against a real local server.

The server is started as a subprocess with a temporary run store. The test
also captures screenshots used by the demo package and checks for external
network requests and console errors.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.services.pipeline import execute_run
from app.store import RunStore

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
REFERENCE = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"
RUN_ID = "R-E2E"


def _free_port() -> int:
    """Ask the OS for an unused loopback port instead of hard-coding 8765."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_seeded_run(base: str, proc: subprocess.Popen, timeout: float = 45.0) -> None:
    """Wait for health *and* a succeeded run with a clear timeout error."""
    deadline = time.time() + timeout
    last_error = "no response yet"
    while time.time() < deadline:
        if proc.poll() is not None:
            output = ""
            if proc.stdout:
                output = proc.stdout.read().decode(errors="replace")
            raise RuntimeError(f"server exited before the seeded run was ready:\n{output}")
        try:
            health = httpx.get(f"{base}/api/health", timeout=1.0)
            if health.status_code != 200:
                last_error = f"health returned {health.status_code}"
            else:
                status = httpx.get(f"{base}/api/runs/{RUN_ID}/status", timeout=1.0)
                if status.status_code == 200:
                    payload = status.json()
                    if payload.get("status") == "succeeded":
                        return
                    last_error = f"run status was {payload.get('status')!r}"
                else:
                    last_error = f"run status returned {status.status_code}"
        except Exception as exc:  # noqa: BLE001 - retry until the deadline
            last_error = repr(exc)
        time.sleep(0.25)
    raise RuntimeError(
        f"seeded run {RUN_ID} did not reach 'succeeded' within {timeout:.0f}s "
        f"at {base}: {last_error}"
    )


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("e2e-data")
    store = RunStore(data)
    store.create_run(RUN_ID, project_id="demo", snapshot_id="S-E2E",
                     fixture_id="demo-slice-300")
    execute_run(
        DEMO, store, RUN_ID, project_id="demo", fixture_id="demo-slice-300",
        tier="demo", reference_path=REFERENCE,
    )
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["PREFLIGHT_DATA_DIR"] = str(data)
    env["PREFLIGHT_FIXTURES_DIR"] = str(REPO / "fixtures")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_seeded_run(base, proc)
    except Exception:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise
    yield {"data": data, "base": base}
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.e2e
def test_golden_path(server) -> None:
    base = server["base"]
    shots = Path(server["data"]) / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    requests: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))

        # Workbench
        page.goto(f"{base}/?run=R-E2E", wait_until="networkidle")
        expect(page.locator("h1")).to_contain_text("Feature workbench")
        expect(page.locator(".feature-row")).to_have_count(8)
        expect(page.locator(".spine-node")).not_to_have_count(0)
        page.locator(".spine-node[data-evidence-id]:not([data-evidence-id=''])").first.click()
        expect(page.locator("[data-evidence-drawer]")).to_contain_text("config/")
        expect(page.locator("[data-evidence-drawer]")).to_be_visible()
        page.screenshot(path=str(shots / "workbench-1440.png"), full_page=True)

        # Grounded refusal
        page.fill("#assistant-question", "Does this estate use territory rating?")
        page.click("[data-assistant-form] button[type=submit]")
        expect(page.locator("[data-assistant-result]")).to_contain_text("Cannot determine", timeout=8000)

        # Manifest
        page.goto(f"{base}/manifest?run=R-E2E", wait_until="networkidle")
        expect(page.locator("h1")).to_have_text("Manifest")
        expect(page.locator(".manifest-table tbody tr")).not_to_have_count(0)
        expect(page.locator("body")).to_contain_text("excluded files")
        page.screenshot(path=str(shots / "manifest-1440.png"), full_page=True)

        # Reconstruction: accept the first mapping
        page.goto(f"{base}/reconstruction?run=R-E2E", wait_until="networkidle")
        expect(page.locator("h1")).to_have_text("Reconstruction")
        first_accept = page.locator('[data-decision="accept"][data-object-type="mapping"]').first
        first_accept.click()
        expect(page.locator("[data-toast]")).to_contain_text("Recorded accept", timeout=8000)
        expect(page.locator("[data-mapping-row]").first.locator("[data-state]")).to_have_text("accepted")
        page.screenshot(path=str(shots / "reconstruction-1440.png"), full_page=True)
        page.locator('[data-decision="reject"][data-object-type="mapping"]').last.click()
        expect(page.locator("[data-assumption-notice]")).to_contain_text("A-DEC-", timeout=8000)
        expect(page.locator("[data-assumption-notice]")).to_be_visible()
        expect(page.locator("[data-mapping-row]").last.locator("[data-state]")).to_have_text("rejected")
        page.locator('.tab[data-tab="assumptions"]').click()
        expect(page.locator("[data-tab-panel='assumptions']")).to_contain_text("A-DEC-")

        # Findings
        page.goto(f"{base}/findings?run=R-E2E", wait_until="networkidle")
        expect(page.locator("body")).to_contain_text("Official Cloud Assurance: not run")
        page.locator('a:has-text("Inspect")').first.click()
        expect(page.locator(".detail-panel")).to_contain_text("Remediation")
        expect(page.locator(".pill-claim")).not_to_have_count(0)
        page.screenshot(path=str(shots / "findings-1440.png"), full_page=True)

        # Evaluation
        page.goto(f"{base}/evaluation?run=R-E2E", wait_until="networkidle")
        expect(page.locator(".metric-card")).to_have_count(6)
        expect(page.locator("body")).to_contain_text("not a benchmark")
        page.screenshot(path=str(shots / "evaluation-1440.png"), full_page=True)

        # Packet
        page.goto(f"{base}/packet?run=R-E2E", wait_until="networkidle")
        expect(page.locator("body")).to_contain_text("Download packet HTML")
        expect(page.locator("body")).to_contain_text("tamper-evident")
        page.screenshot(path=str(shots / "packet-1440.png"), full_page=True)

        # 1280 viewport
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{base}/?run=R-E2E", wait_until="networkidle")
        page.screenshot(path=str(shots / "workbench-1280.png"), full_page=True)

        browser.close()

    external = [
        url for url in requests
        if not url.startswith(base) and not url.startswith("data:") and not url.startswith("blob:")
    ]
    assert external == [], external
    assert console_errors == [], console_errors
    assert page_errors == [], page_errors


@pytest.mark.e2e
def test_mobile_390_no_overflow_and_nav_reachable(server) -> None:
    """Every route fits a 390px viewport; the mobile nav exposes every link."""
    base = server["base"]
    shots = Path(server["data"]) / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    routes = [
        ("workbench", f"{base}/?run=R-E2E&feature=PA-VEH-01"),
        ("manifest", f"{base}/manifest?run=R-E2E"),
        ("manifest-excluded", f"{base}/manifest?run=R-E2E&excluded=1"),
        ("reconstruction", f"{base}/reconstruction?run=R-E2E"),
        ("reconstruction-draft", f"{base}/reconstruction?run=R-E2E&tab=draft"),
        ("reconstruction-assumptions", f"{base}/reconstruction?run=R-E2E&tab=assumptions"),
        ("reconstruction-comparison", f"{base}/reconstruction?run=R-E2E&tab=comparison"),
        ("findings", f"{base}/findings?run=R-E2E"),
        ("findings-selected", f"{base}/findings?run=R-E2E&selected=F-008"),
        ("evaluation", f"{base}/evaluation?run=R-E2E"),
        ("packet", f"{base}/packet?run=R-E2E"),
        ("runs", f"{base}/runs"),
        ("settings", f"{base}/settings"),
        ("about", f"{base}/about"),
        ("import", f"{base}/import"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        for name, url in routes:
            page.goto(url, wait_until="networkidle")
            width = page.evaluate("() => window.innerWidth")
            scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
            body_width = page.evaluate("() => document.body.scrollWidth")
            assert scroll_width <= width + 1, (name, scroll_width, width)
            assert body_width <= width + 1, (name, body_width, width)

            toggle = page.locator("[data-nav-toggle]")
            expect(toggle).to_be_visible()
            toggle.click()
            expect(toggle).to_have_attribute("aria-expanded", "true")
            links = page.locator(".sidebar .side-link")
            expect(links).to_have_count(9)
            for index in range(links.count()):
                link = links.nth(index)
                expect(link).to_be_visible()
                box = link.bounding_box()
                assert box is not None, (name, index)
                assert box["x"] >= -1, (name, index, box)
                assert box["x"] + box["width"] <= width + 1, (name, index, box)
            open_width = page.evaluate("() => document.documentElement.scrollWidth")
            assert open_width <= width + 1, (name, "nav open", open_width, width)
            toggle.click()
            expect(toggle).to_have_attribute("aria-expanded", "false")

            if name == "workbench":
                hint = page.locator("[data-spine-scroll-hint]")
                expect(hint).to_be_visible()
                graph_width = page.evaluate(
                    "() => document.querySelector('.spine-svg').getBoundingClientRect().width"
                )
                assert graph_width >= 672, graph_width
            if name == "findings-selected":
                expect(page.locator("tr.selected")).to_have_count(1)
                expect(page.locator(".selected-flag")).to_have_count(1)
                selected_cells = page.locator("tr.selected td")
                expect(selected_cells.first).to_have_attribute("aria-current", "true")
                expect(selected_cells.first).to_contain_text("PF-GW-PKG-001")
                assert selected_cells.nth(6).inner_text().strip() == "open"
            if name == "runs":
                expect(page.locator("[data-runs-table] [data-scroll-hint]")).to_be_visible()

            page.screenshot(path=str(shots / f"mobile-390-{name}.png"), full_page=True)

        browser.close()

    assert console_errors == [], console_errors
    assert page_errors == [], page_errors
