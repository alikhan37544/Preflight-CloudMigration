"""Playwright golden path against a real local server.

The server is started as a subprocess with a temporary run store. The test
also captures screenshots used by the demo package and checks for external
network requests and console errors.
"""

from __future__ import annotations

import os
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
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("e2e-data")
    store = RunStore(data)
    store.create_run("R-E2E", project_id="demo", snapshot_id="S-E2E", fixture_id="demo-slice-300")
    execute_run(
        DEMO, store, "R-E2E", project_id="demo", fixture_id="demo-slice-300",
        tier="demo", reference_path=REFERENCE,
    )
    env = os.environ.copy()
    env["PREFLIGHT_DATA_DIR"] = str(data)
    env["PREFLIGHT_FIXTURES_DIR"] = str(REPO / "fixtures")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/api/health", timeout=1.0).status_code == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.25)
    if not ready:
        proc.terminate()
        output = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
        raise RuntimeError(f"server did not start:\n{output}")
    yield data
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.e2e
def test_golden_path(server) -> None:
    shots = Path(server) / "screenshots"
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
        page.goto(f"{BASE}/?run=R-E2E", wait_until="networkidle")
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
        page.goto(f"{BASE}/manifest?run=R-E2E", wait_until="networkidle")
        expect(page.locator("h1")).to_have_text("Manifest")
        expect(page.locator(".manifest-table tbody tr")).not_to_have_count(0)
        expect(page.locator("body")).to_contain_text("excluded files")
        page.screenshot(path=str(shots / "manifest-1440.png"), full_page=True)

        # Reconstruction: accept the first mapping
        page.goto(f"{BASE}/reconstruction?run=R-E2E", wait_until="networkidle")
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
        page.goto(f"{BASE}/findings?run=R-E2E", wait_until="networkidle")
        expect(page.locator("body")).to_contain_text("Official Cloud Assurance: not run")
        page.locator('a:has-text("Inspect")').first.click()
        expect(page.locator(".detail-panel")).to_contain_text("Remediation")
        expect(page.locator(".pill-claim")).not_to_have_count(0)
        page.screenshot(path=str(shots / "findings-1440.png"), full_page=True)

        # Evaluation
        page.goto(f"{BASE}/evaluation?run=R-E2E", wait_until="networkidle")
        expect(page.locator(".metric-card")).to_have_count(6)
        expect(page.locator("body")).to_contain_text("not a benchmark")
        page.screenshot(path=str(shots / "evaluation-1440.png"), full_page=True)

        # Packet
        page.goto(f"{BASE}/packet?run=R-E2E", wait_until="networkidle")
        expect(page.locator("body")).to_contain_text("Download packet HTML")
        expect(page.locator("body")).to_contain_text("tamper-evident")
        page.screenshot(path=str(shots / "packet-1440.png"), full_page=True)

        # 1280 viewport
        page.set_viewport_size({"width": 1280, "height": 800})
        page.goto(f"{BASE}/?run=R-E2E", wait_until="networkidle")
        page.screenshot(path=str(shots / "workbench-1280.png"), full_page=True)

        browser.close()

    external = [
        url for url in requests
        if not url.startswith(BASE) and not url.startswith("data:") and not url.startswith("blob:")
    ]
    assert external == [], external
    assert console_errors == [], console_errors
    assert page_errors == [], page_errors
