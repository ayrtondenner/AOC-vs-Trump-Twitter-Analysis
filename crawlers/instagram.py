from __future__ import annotations

import ctypes
from typing import Iterable

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def _get_primary_monitor_width() -> int:
    # Primary monitor width (in pixels)
    return int(ctypes.windll.user32.GetSystemMetrics(0))


def _move_window_to_second_monitor_right(driver: webdriver.Chrome) -> None:
    """Best-effort: assumes the 2nd monitor is to the right of the primary."""
    try:
        primary_width = _get_primary_monitor_width()
        # If there is only one monitor, this will still be a valid coordinate but
        # the OS will keep the window on the available display.
        driver.set_window_position(primary_width + 10, 0)
    except Exception:
        # If anything goes wrong (non-Windows, missing permissions, etc.), do nothing.
        pass


def scrap_instagram_page(url: str) -> None:
    """Open a Chrome window via Selenium, move to 2nd monitor, maximize, visit URL, scroll once."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")

    def wait_for_document_ready(driver: webdriver.Chrome, timeout_s: float = 20.0) -> None:
        WebDriverWait(driver, timeout_s).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

    def wait_and_click_fechar_svg(driver: webdriver.Chrome, timeout_s: float = 20.0) -> None:
        # Instagram sometimes shows a modal that can be closed with an SVG icon labeled "Fechar".
        svg_css = "svg[aria-label='Fechar']"
        svg_xpath = "//svg[@aria-label='Fechar']"
        print(f"[INFO] Waiting for Fechar SVG: {svg_css}")
        try:
            svg = WebDriverWait(driver, timeout_s).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, svg_css))
            )
        except TimeoutException:
            print(f"[WARN] Timeout waiting for Fechar SVG after {timeout_s:.0f}s")
            return

        print("[INFO] Fechar SVG found; clicking its parent...")
        parent = svg.find_element(By.XPATH, "..")
        # In practice the SVG itself often won't click, but the direct parent does.
        # Also, the parent may be a <div>/<span> and never become "clickable" by Selenium's heuristic,
        # so we avoid element_to_be_clickable and do a JS click.
        try:
            WebDriverWait(driver, 5.0).until(EC.visibility_of(parent))
        except Exception:
            pass

        driver.execute_script("arguments[0].click();", parent)
        print("[INFO] Fechar parent clicked (JS click)")

    chrome_options = Options()
    # "Anonymous" browsing: separate session with no persistent cookies/history.
    #chrome_options.add_argument("--incognito")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")

    driver: webdriver.Chrome | None = None
    try:
        # Selenium Manager is missing in your environment (selenium-manager.exe not present),
        # so we bypass it by providing an explicit chromedriver binary via webdriver-manager.
        try:
            from webdriver_manager.chrome import ChromeDriverManager
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency: webdriver-manager. Install it with: python -m pip install -U webdriver-manager"
            ) from exc

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        _move_window_to_second_monitor_right(driver)
        driver.maximize_window()

        driver.get("https://www.google.com.br")
        driver.get(url)
        wait_for_document_ready(driver)
        wait_and_click_fechar_svg(driver, timeout_s=15.0)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        # One scroll only; no hard sleeps.
    finally:
        if driver is not None:
            driver.quit()


def run_sync(urls: Iterable[str]) -> None:
    for url in urls:
        scrap_instagram_page(url)