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

def get_driver():

    chrome_options = Options()
    # "Anonymous" browsing: separate session with no persistent cookies/history.
    #chrome_options.add_argument("--incognito")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")

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
    return driver