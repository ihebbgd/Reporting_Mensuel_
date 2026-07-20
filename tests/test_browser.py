"""Real browser acceptance test; uses synthetic CSVs and an isolated database."""

import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from app.main import create_app

pytestmark = pytest.mark.browser


@pytest.fixture
def live_server(app_config):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(app_config), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "Test server did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        sock.close()
        assert not thread.is_alive()


def test_desktop_mobile_workflow(live_server, app_config):
    root = Path(__file__).resolve().parents[1]
    screenshots = root / "artifacts" / "browser"
    screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1050}, reduced_motion="reduce"
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(live_server)
        page.locator("#access-key").fill("incorrect")
        page.locator("#login-form button").click()
        expect(page.locator("#login-error")).to_be_visible()
        page.locator("#access-key").fill(app_config.api_access_key)
        page.locator("#login-form button").click()
        expect(page.locator("#login-dialog")).not_to_be_visible()
        for year in (2024, 2025):
            page.locator("#open-import").click()
            if year == 2024:
                page.locator("#csv-file").set_input_files(
                    {"name": "invalid.csv", "mimeType": "text/csv", "buffer": b"bad file"}
                )
                page.locator("#submit-import").click()
                expect(page.locator("#import-error")).to_be_visible()
            page.locator("#csv-file").set_input_files(root / "examples" / f"demo_{year}.csv")
            expect(page.locator("#import-year")).to_have_value(str(year))
            expect(page.locator("#use-ai")).not_to_be_checked()
            if year == 2025:
                options = page.locator("#baseline-report option").all()
                assert len(options) == 2
                page.locator("#baseline-report").select_option(index=1)
            page.locator("#submit-import").click()
            expect(page.locator("#import-dialog")).not_to_be_visible()
            expect(page.locator("#report-content")).to_be_visible(timeout=60000)
            expect(page.locator("#year-label")).to_have_text(str(year), timeout=60000)
        expect(page.locator("#ca")).to_have_text("1\u202f344\u202f000")
        assert (
            page.locator("#activity-chart").evaluate(
                "(c) => Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).filter((v,i)=>i%4===3 && v>0).length"
            )
            > 10000
        )
        overflow = page.evaluate(
            """() => [...document.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > innerWidth + 1 || e.getBoundingClientRect().left < -1).map(e => ({tag: e.tagName, id: e.id, cls: e.className, left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right})).slice(0, 10)"""
        )
        assert not overflow, overflow
        page.screenshot(path=str(screenshots / "dashboard-desktop.png"), full_page=True)
        with page.expect_download() as download_info:
            page.locator("#download").click()
        download = download_info.value
        download.save_as(screenshots / "demo-report.pdf")
        assert (screenshots / "demo-report.pdf").read_bytes().startswith(b"%PDF")
        page.locator("#tab-monthly").click()
        expect(page.locator("#monthly-rows tr")).to_have_count(12)
        page.locator("#tab-monthly").press("ArrowRight")
        expect(page.locator("#tab-alerts")).to_have_attribute("aria-selected", "true")
        page.locator("#tab-alerts").click()
        expect(page.locator("#anomaly-rows tr")).not_to_have_count(0)
        page.locator("#tab-analysis").click()
        expect(page.locator("#analysis-note")).to_contain_text("Synthèse locale")
        page.locator("[data-view=compare]").click()
        page.locator("#previous-report").select_option(index=2)
        page.locator("#current-report").select_option(index=1)
        page.locator("#compare-form button").click()
        expect(page.locator("#comparison-result")).to_be_visible()
        expect(page.locator("#comparison-rows")).to_contain_text("12")
        page.screenshot(path=str(screenshots / "comparison-desktop.png"), full_page=True)
        page.locator("[data-view=history]").click()
        expect(page.locator("#history-rows tr")).to_have_count(2)
        page.screenshot(path=str(screenshots / "history-desktop.png"), full_page=True)
        page.locator("[data-view=dashboard]").click()
        page.locator("#tab-overview").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(250)
        expect(page.locator("#activity-chart")).to_be_visible()
        overflow = page.evaluate(
            """() => [...document.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > innerWidth + 1 || e.getBoundingClientRect().left < -1).map(e => ({tag: e.tagName, id: e.id, cls: e.className, left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right})).slice(0, 10)"""
        )
        assert not overflow, overflow
        page.screenshot(path=str(screenshots / "dashboard-mobile.png"), full_page=True)
        page.locator("#open-import").click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator("#submit-import")).to_be_in_viewport()
        page.screenshot(path=str(screenshots / "import-mobile.png"), full_page=True)
        page.locator("#close-import").click()
        page.locator("[data-view=history]").click()
        page.locator("#history-rows button[title^=Supprimer]").first.click()
        page.locator("#cancel-delete").click()
        expect(page.locator("#history-rows tr")).to_have_count(2)
        page.locator("#history-rows button[title^=Supprimer]").first.click()
        page.locator("#confirm-delete").click()
        expect(page.locator("#history-rows tr")).to_have_count(1)
        page.reload()
        expect(page.locator("#report-content")).to_be_visible()
        page.set_viewport_size({"width": 1440, "height": 1050})
        page.locator("#logout").click()
        expect(page.locator("#login-dialog")).to_be_visible()
        assert not errors, errors
        context.close()
        browser.close()
