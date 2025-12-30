
from __future__ import annotations

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import time
import re
import json
from pathlib import Path
from typing import Optional

_RESPOSTAS_REGEX_PATTERN = re.compile(
    r"^Ler\s+\d+(?:,\d+)?(?:\s+mil)?\s+respostas$"
)

# TODO: add TQDM to track progress per page

def _parse_pt_count(raw: str | None) -> Optional[int]:
    """Parse counts like '10448', '3 mil', '1 mi', '3 mil', '1 mi'."""
    if raw is None:
        return None
    s = raw.strip().lower().replace("\u00a0", " ")
    if not s:
        return None

    multiplier = 1
    if " mi" in s or s.endswith("mi"):
        multiplier = 1_000_000
        s = s.replace("mi", "").strip()
    elif " mil" in s or s.endswith("mil"):
        multiplier = 1_000
        s = s.replace("mil", "").strip()

    # Keep digits + comma/dot for potential decimals (e.g. '3,2')
    cleaned = re.sub(r"[^0-9\,\.]", "", s)
    if not cleaned:
        return None

    # If there's a decimal separator, treat it as decimal; else integer.
    if "," in cleaned or "." in cleaned:
        # Convert Brazilian decimal comma to dot and remove thousand separators.
        # Heuristic: if both separators appear, assume one is thousands and the other decimal.
        if "," in cleaned and "." in cleaned:
            # Common formats: '1.234,5' or '1,234.5'
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        else:
            # Only one separator present; assume it's decimal if followed by 1-2 digits.
            if "," in cleaned:
                cleaned = cleaned.replace(".", "")
                cleaned = cleaned.replace(",", ".")
            else:
                # only '.'
                cleaned = cleaned.replace(",", "")

        try:
            return int(float(cleaned) * multiplier)
        except ValueError:
            return None

    try:
        return int(cleaned) * multiplier
    except ValueError:
        return None


def _extract_metric_from_label(label: str, metric_word: str) -> Optional[int]:
    """Extract metric value from a group aria-label (Portuguese UI)."""
    # Example: "10448 respostas, 11353 reposts, 79072 curtidas, 1325 items salvos, 2965777 visualizações"
    pattern = re.compile(
        rf"(?P<num>[0-9][0-9\s\.,\u00a0]*(?:\s+mil|\s+mi)?)\s+{re.escape(metric_word)}",
        re.IGNORECASE,
    )
    m = pattern.search(label or "")
    if not m:
        return None
    return _parse_pt_count(m.group("num"))



def scrap_twitter_page(driver: WebDriver, url: str, timeout_s: float = 20.0) -> list[dict]:
    """Scrape a public X profile page and per-tweet metrics from the tweet page."""

    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")

    driver.get(url.strip())
    WebDriverWait(driver, timeout_s).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(driver, timeout_s).until(
        lambda d: any(
            (el.text or "").strip() == "Seguir"
            for el in d.find_elements(By.XPATH, "//span[normalize-space()='Seguir']")
        )
    )
    time.sleep(2)  # Extra wait to ensure dynamic content loads
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)  # Wait for potential new content to load after scrolling
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)  # Allow content to stabilize after scrolling back to top
    scroll_height = driver.execute_script("return document.body.scrollHeight;")
    text_list = []
    href_list = []

    def extract_tweet_content():
        timeline_div = WebDriverWait(driver, timeout_s).until(
            lambda d: d.find_element(By.XPATH, "//div[starts-with(@aria-label, 'Timeline: Posts de ')]")
        )
        inner_div = timeline_div.find_element(By.XPATH, ".//div")
        cell_inner_divs = inner_div.find_elements(By.XPATH, ".//div[@data-testid='cellInnerDiv']")

        for cell_div in cell_inner_divs:
            try:
                article_el = cell_div.find_element(By.TAG_NAME, "article")
            except Exception:
                # Some timeline cells aren't tweets (no <article>); skip them
                continue
            a = article_el.find_element(
                By.XPATH,
                ".//a[contains(@href, '/status/') and not(contains(@href, '/analytics'))][1]"
            )
            href = a.get_attribute("href")
            if href not in href_list:
                href_list.append(href)
            cell_div_text = cell_div.text
            if cell_div_text not in text_list:
                text_list.append(cell_div.text)

    step = max(int(scroll_height // 20), 1)
    for i in range(0, 22):
        y = min(i * step, int(scroll_height))
        driver.execute_script("window.scrollTo(0, arguments[0]);", y)
        extract_tweet_content()
        time.sleep(1)  # Small delay to allow content to load

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    extract_tweet_content()
    
    href_list = [href for href in href_list if href.lower().startswith(url.lower())]
    posts_dict_list = []

    for href in href_list:
        driver.get(href)
        WebDriverWait(driver, timeout_s).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        time.sleep(1)  # Extra wait to ensure dynamic content loads

        WebDriverWait(driver, timeout_s).until(
            lambda d: any(
                _RESPOSTAS_REGEX_PATTERN.match((el.text or "").strip())
                for el in d.find_elements(By.XPATH, "//span")
            )
        )

        # Tweet datetime
        time_el = WebDriverWait(driver, timeout_s).until(
            lambda d: d.find_element(By.XPATH, "//article//time[@datetime]")
        )
        post_datetime = time_el.get_attribute("datetime")

        post_text_list = driver.find_elements(By.XPATH, "//article//div[@data-testid='tweetText']")
        assert len(post_text_list) >= 0 and len(post_text_list) <= 2, f"Unexpected number of tweet text elements: {len(post_text_list)}"
        post_text = post_text_list[0].text if len(post_text_list) >= 1 else None
        post_subtext = str(post_text_list[1].text) if len(post_text_list) == 2 else None

        has_video = bool(driver.find_elements(By.XPATH, "//div[@data-testid='videoComponent']"))

        images = driver.find_elements(By.XPATH,"//article//img[@alt and @draggable='true' and @src and @class]")
        images = [image for image in images if "profile_images" not in (image.get_attribute("src") or "")]

        # Metrics group div: aria-label contains 'respostas, reposts, curtidas, ... visualizações'
        metrics_div = WebDriverWait(driver, timeout_s).until(
            lambda d: d.find_element(
                By.XPATH,
                "//div[@role='group' and @aria-label and "
                "contains(@aria-label, 'respostas') and "
                "contains(@aria-label, 'reposts') and "
                "contains(@aria-label, 'curtidas') and "
                "contains(@aria-label, 'items salvos') and "
                "contains(@aria-label, 'visualiza')"  # matches 'visualizações'
                "]",
            )
        )
        aria_label = (metrics_div.get_attribute("aria-label") or "").strip()

        post_dict = {
            "permalink": href,
            "datetime": post_datetime,
            "text": post_text,
            "subtext": post_subtext,
            "has_video": has_video,
            "image_count": len(images),
            "answers": _extract_metric_from_label(aria_label, "respostas"),
            "reposts": _extract_metric_from_label(aria_label, "reposts"),
            "likes": _extract_metric_from_label(aria_label, "curtidas"),
            "saves": _extract_metric_from_label(aria_label, "items salvos"),
            "views": _extract_metric_from_label(aria_label, "visualizações"),
            "aria_label": aria_label,
        }

        posts_dict_list.append(post_dict)
    
    username = url.split("/")[-1]
    out_dir = Path("data")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{username}.json"

    out_path.write_text(
        json.dumps(posts_dict_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return posts_dict_list