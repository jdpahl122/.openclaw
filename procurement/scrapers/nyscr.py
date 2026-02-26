"""NYS Contract Reporter scraper.

Uses Playwright for all page interactions (login, filtering, pagination,
detail pages) since the site uses reCAPTCHA v3 and session-bound cookies.
HTML parsing is done with BeautifulSoup for speed and robustness.

Login strategy:
  reCAPTCHA v3 silently scores users and rejects headless browsers.  We
  work around this by using a **persistent session**:
    1. On the first run (or when the session has expired), Playwright opens
       a *headed* (visible) browser window so the user can complete login
       normally.  The session cookies are saved to ``data/nyscr_session.json``.
    2. On subsequent runs the saved session is loaded into a headless
       context, avoiding reCAPTCHA entirely.
"""

from __future__ import annotations

import logging
import re


def parse_mwbe_sdvob_goals(soup) -> dict:
    """Extract SDVOB, MBE, and WBE goal percentages from a detail page.

    Works with a BeautifulSoup object.  Returns a dict with keys
    ``sdvob_goal``, ``mbe_goal``, ``wbe_goal`` (floats or None).
    """
    goals: dict = {"sdvob_goal": None, "mbe_goal": None, "wbe_goal": None}
    _GOAL_MAP = {
        "sdvob goal": "sdvob_goal",
        "mbe goal": "mbe_goal",
        "wbe goal": "wbe_goal",
    }
    for strong in soup.find_all("strong"):
        text = (strong.get_text() or "").strip().rstrip(":").lower()
        key = _GOAL_MAP.get(text)
        if not key:
            continue
        sibling_text = strong.next_sibling
        if sibling_text:
            match = re.search(r"([\d.]+)\s*%", str(sibling_text))
            if match:
                goals[key] = float(match.group(1))
    return goals
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Tag

import config
from models.rfq import RFQ
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

_DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%B %d, %Y"]
_SEARCH_URL = f"{config.NYSCR_BASE_URL}/Ads/Search"
_LOGIN_URL = f"{config.NYSCR_BASE_URL}/Account/Login"
_RAW_DIR = config.DATA_DIR / "raw"
_SESSION_FILE = config.DATA_DIR / "nyscr_session.json"

# Sidebar checkbox IDs for target categories
_CATEGORY_IDS = {
    "Information Technology": "SidebarCategories-16",
}


def _parse_date(text: str) -> Optional[date]:
    text = text.strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


class NYSCRScraper(BaseScraper):
    """Scraper for https://www.nyscr.ny.gov"""

    name = "nyscr"

    def __init__(self) -> None:
        _RAW_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # ---------------------------------------------------------- browser mgmt

    def _start_browser(self, *, headless: bool = True) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()

        launch_kwargs: dict = {"headless": headless}

        # For interactive login, use the real Chrome install + anti-detect
        # flags so reCAPTCHA v3 doesn't flag us as a bot.
        if not headless:
            launch_kwargs["channel"] = "chrome"
            launch_kwargs["args"] = [
                "--disable-blink-features=AutomationControlled",
            ]

        self._browser = self._pw.chromium.launch(**launch_kwargs)

        ctx_kwargs: dict = {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
        }

        # Load saved session cookies if available
        if headless and _SESSION_FILE.exists():
            ctx_kwargs["storage_state"] = str(_SESSION_FILE)
            logger.info("Loading saved session from %s", _SESSION_FILE)

        self._context = self._browser.new_context(**ctx_kwargs)
        self._page = self._context.new_page()

        # Apply stealth patches to hide automation signals
        try:
            from playwright_stealth import Stealth
            stealth = Stealth(navigator_platform_override="MacIntel")
            stealth.apply_stealth_sync(self._page)
        except ImportError:
            logger.debug("playwright-stealth not installed; skipping stealth")

        logger.info("Browser started (headless=%s)", headless)

    def _stop_browser(self) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._page = self._browser = self._context = self._pw = None

    def _save_session(self) -> None:
        """Persist cookies / localStorage so future headless runs skip login."""
        self._context.storage_state(path=str(_SESSION_FILE))
        logger.info("Session saved to %s", _SESSION_FILE)

    # ---------------------------------------------------------------- login

    def _is_logged_in(self) -> bool:
        """Navigate to search and return True if the session is authenticated."""
        page = self._page
        page.goto(_SEARCH_URL, wait_until="networkidle")
        html = page.content()
        for marker in ("Log Out", "Logout", "Sign Out",
                       "/Account/Manage", "/Account/Logout"):
            if marker in html:
                return True
        return False

    def _ensure_authenticated(self) -> None:
        """Make sure we have a valid authenticated session.

        Tries the saved session first (headless).  If that fails, opens a
        visible browser window for the user to complete login interactively.
        """
        # Fast path: saved session is still valid
        if _SESSION_FILE.exists():
            if self._is_logged_in():
                logger.info("Authenticated via saved session")
                return
            logger.info("Saved session expired -- need fresh login")

        # Need a fresh login -- must use headed browser for reCAPTCHA v3
        self._stop_browser()
        self._start_browser(headless=False)

        self._interactive_login()
        self._save_session()

        # Switch back to headless for the rest of the scraping
        self._stop_browser()
        self._start_browser(headless=True)

        if not self._is_logged_in():
            _save_screenshot(self._page, "login_verify_failure")
            raise RuntimeError(
                "Login session did not persist. Please try again."
            )
        logger.info("Authenticated via fresh interactive login")

    def _interactive_login(self) -> None:
        """Open a visible browser, fill credentials, submit, and verify.

        Uses the real Chrome browser with stealth patches so reCAPTCHA v3
        gives a passing score.  If the auto-submit is rejected, the browser
        stays open so the user can retry manually.
        """
        if not config.NYSCR_USERNAME or not config.NYSCR_PASSWORD:
            raise RuntimeError("NYSCR credentials not configured in .env")

        page = self._page
        logger.info("Opening login page in Chrome...")
        page.goto(_LOGIN_URL, wait_until="networkidle")

        # Fill the form
        page.fill("#Username", config.NYSCR_USERNAME)
        page.fill("#Password", config.NYSCR_PASSWORD)

        # Let reCAPTCHA v3 token populate
        page.wait_for_timeout(3000)

        # Auto-submit
        page.click('button[type="submit"], input[type="submit"]')
        logger.info("Login form submitted, waiting for redirect...")

        # Wait up to 10s for the page to leave /Account/Login or /Authenticate
        try:
            page.wait_for_url(
                lambda url: "/Account/Login" not in url
                and "/Account/Authenticate" not in url,
                timeout=10_000,
            )
        except Exception:
            # Auto-submit may have been rejected by reCAPTCHA.
            # Check for error text and let the user retry in the open window.
            html = page.content()
            if "Unable to verify" in html or "not a robot" in html:
                print(
                    "\n"
                    "╔═══════════════════════════════════════════════════════════╗\n"
                    "║  reCAPTCHA blocked the auto-submit.                      ║\n"
                    "║  The browser is still open -- please log in manually.    ║\n"
                    "║  The window will close automatically once logged in.     ║\n"
                    "╚═══════════════════════════════════════════════════════════╝\n"
                )
                # Re-fill in case the form was cleared
                try:
                    page.fill("#Username", config.NYSCR_USERNAME)
                    page.fill("#Password", config.NYSCR_PASSWORD)
                except Exception:
                    pass

                try:
                    page.wait_for_url(
                        lambda url: "/Account/Login" not in url
                        and "/Account/Authenticate" not in url,
                        timeout=120_000,
                    )
                except Exception:
                    _save_screenshot(page, "interactive_login_timeout")
                    raise RuntimeError(
                        "Login timed out (2 min). Please try again."
                    )
            else:
                _save_screenshot(page, "login_unknown_state")
                raise RuntimeError(
                    "Login did not redirect. Check the browser window."
                )

        # Give the post-login page a moment to settle
        page.wait_for_timeout(1500)

        # Verify authentication
        page.goto(_SEARCH_URL, wait_until="networkidle")
        html = page.content()
        for marker in ("Log Out", "Logout", "/Account/Logout", "/Account/Manage"):
            if marker in html:
                logger.info("Interactive login successful")
                return

        _save_screenshot(page, "interactive_login_failure")
        raise RuntimeError(
            "Interactive login did not result in an authenticated session."
        )

    # ------------------------------------------------------ search + filter

    def _apply_category_filter(self) -> None:
        """Navigate to the search page with IT category filter applied.

        The search form uses ``method="get"``, so we can encode all filter
        parameters directly in the URL.  This avoids interacting with the
        sidebar checkboxes (which are hidden behind "View More" toggles
        and have ``Filter``-class JS listeners that cause context issues).
        """
        page = self._page

        # Category value 16 = "Information Technology"
        params = (
            "Categories%5B%5D=16"  # Categories[]=16
            "&Top=50"
            "&Skip=0"
            "&Sort=-DateIssued"
        )
        url = f"{_SEARCH_URL}?{params}"
        logger.info("Loading filtered search: %s", url)
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(800)

    # ----------------------------------------------------------- pagination

    def _collect_all_listings(self, max_pages: int) -> list[dict]:
        """Paginate through search results and collect listing metadata.

        Returns a flat list of dicts (one per listing).
        """
        all_listings: list[dict] = []
        page_num = 0

        while True:
            page_num += 1
            if max_pages and page_num > max_pages:
                break

            html = self._page.content()
            self._save_raw_html(html, page_num)

            listings = self._parse_listings(html)
            logger.info(
                "Page %d: %d listings (total so far: %d)",
                page_num, len(listings), len(all_listings) + len(listings),
            )
            all_listings.extend(listings)

            if not self._go_next_page():
                break

        return all_listings

    def _go_next_page(self) -> bool:
        """Click the Next button. Returns False when there are no more pages."""
        btn = self._page.query_selector("button.Next:not([disabled])")
        if not btn:
            return False
        try:
            btn.click()
            self._page.wait_for_load_state("networkidle")
            self._page.wait_for_timeout(800)
            return True
        except Exception as exc:
            logger.warning("Next-page click failed: %s", exc)
            return False

    # ------------------------------------------------------- listing parser

    def _parse_listings(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        for item in soup.select("div.opp-list-item[data-ad-id]"):
            rec = self._parse_listing(item)
            if rec and rec.get("cr_number"):
                results.append(rec)
        return results

    def _parse_listing(self, item: Tag) -> Optional[dict]:
        ad_id = item.get("data-ad-id", "")
        data: dict = {
            "cr_number": str(ad_id),
            "title": "",
            "agency": "",
            "division": "",
            "issue_date": "",
            "due_date": "",
            "ad_end_date": "",
            "location": "",
            "category": "",
            "ad_type": "",
            "note": "",
            "detail_url": "",
        }

        # Title -- prefer the `title` attribute on the coloured bar div,
        # which contains the untruncated text.
        title_div = item.select_one("div.bg-primary.text-light")
        if title_div:
            full_title = title_div.get("title", "") or ""
            if full_title.startswith("Full Title:"):
                full_title = full_title[len("Full Title:"):].strip()
            data["title"] = _clean(full_title) if full_title else _clean(title_div.get_text())

        # Label / value pairs (div.w-exact-8 = label, next sibling = value)
        for label_el in item.select("div.w-exact-8"):
            raw_label = _clean(label_el.get_text()).rstrip(":").lower()
            val_el = label_el.find_next_sibling("div")
            if not val_el:
                continue
            val = _clean(val_el.get_text())

            field_map = {
                "cr#": "cr_number",
                "agency": "agency",
                "division": "division",
                "issue date": "issue_date",
                "due date": "due_date",
                "ad end date": "ad_end_date",
                "location": "location",
                "category": "category",
                "ad type": "ad_type",
            }
            key = field_map.get(raw_label)
            if key:
                data[key] = val

        # Alert / note
        alert = item.select_one("div.alert")
        if alert:
            data["note"] = _clean(alert.get_text())

        # Detail link -- when logged in this is a real URL; when not, it
        # points to /Account/Login.
        link = item.select_one("a.ad-action-link")
        if link:
            href = link.get("href", "")
            if href and "/Account/Login" not in href:
                data["detail_url"] = _abs(href)

        # Fallback: construct URL from ad-id
        if not data["detail_url"] and ad_id:
            data["detail_url"] = f"{config.NYSCR_BASE_URL}/Ads/View?ID={ad_id}"

        return data

    # -------------------------------------------------------- detail pages

    def _fetch_detail(self, listing: dict) -> dict:
        """Navigate to the detail page and extract extra info + attachment URLs."""
        url = listing.get("detail_url", "")
        if not url:
            return {}

        cr = listing.get("cr_number", "unknown")
        logger.info("Fetching detail for CR# %s: %s", cr, url)

        try:
            self._page.goto(url, wait_until="networkidle")
            self._page.wait_for_timeout(500)
        except Exception as exc:
            logger.warning("Could not load detail page %s: %s", url, exc)
            return {}

        html = self._page.content()
        raw_path = _RAW_DIR / f"detail_{cr}.html"
        raw_path.write_text(html, encoding="utf-8")

        soup = BeautifulSoup(html, "html.parser")

        # Full page text for downstream keyword matching
        raw_text = soup.get_text(" ", strip=True)[:50000]

        # Attachment links -- NYSCR uses:
        #   /Ads/Step6Download?id=... (actual RFQ attachments, with download attr)
        #   /Ads/GeneratePdf?id=...   (ad detail summary PDF)
        # We skip /Home/DownloadDailyIssue (nav-bar daily issue PDFs).
        attachment_urls: list[dict] = []
        for a in soup.find_all("a", href=True):
            href = str(a["href"])
            download_attr = a.get("download", "")

            if "Step6Download" in href or "GeneratePdf" in href:
                filename = download_attr or href.split("/")[-1].split("?")[0] or "attachment"
                attachment_urls.append({
                    "url": _abs(href),
                    "filename": filename,
                })

        # Deduplicate (each attachment appears twice for mobile/desktop)
        seen: set[str] = set()
        unique_attachments: list[dict] = []
        for att in attachment_urls:
            key = att["url"]
            if key not in seen:
                seen.add(key)
                unique_attachments.append(att)

        # Parse MWBE / SDVOB goal percentages (supplementary)
        goals = parse_mwbe_sdvob_goals(soup)

        return {
            "raw_text": raw_text,
            "attachment_urls": unique_attachments,
            **goals,
        }

    def _download_attachments(self, attachments: list[dict], cr: str) -> list[str]:
        """Download attachment files using the browser context (shares cookies).

        Each item in *attachments* is ``{"url": ..., "filename": ...}``.
        """
        if not attachments:
            return []

        dest_dir = _RAW_DIR / cr
        dest_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []

        for att in attachments:
            url = att["url"]
            filename = att.get("filename") or "attachment"
            local_path = dest_dir / filename

            if local_path.exists():
                paths.append(str(local_path))
                continue

            try:
                resp = self._context.request.get(url)
                if resp.ok:
                    local_path.write_bytes(resp.body())
                    logger.info("Downloaded %s -> %s", filename, local_path)
                    paths.append(str(local_path))
                else:
                    logger.warning("HTTP %s downloading %s", resp.status, url)
            except Exception as exc:
                logger.warning("Download error for %s: %s", url, exc)

        return paths

    # ============================================================ main entry

    def scrape(self, max_pages: int = 0) -> list[RFQ]:
        """Full scrape: login -> filter -> paginate -> fetch details.

        Args:
            max_pages: Max search-result pages to walk (0 = all).
        """
        self._start_browser()
        try:
            return self._run(max_pages)
        finally:
            self._stop_browser()

    def _run(self, max_pages: int) -> list[RFQ]:
        # 1. Authenticate (uses saved session or interactive login)
        self._ensure_authenticated()

        # 2. Apply category filter and submit search
        self._apply_category_filter()

        total = self._result_count()
        logger.info("Filtered result count: %d", total)

        # 3. Collect listing metadata from all result pages
        listings = self._collect_all_listings(max_pages)
        logger.info("Collected %d listings from search results", len(listings))

        # 4. Visit each detail page and build RFQ objects
        rfqs: list[RFQ] = []
        for i, listing in enumerate(listings, 1):
            cr = listing.get("cr_number", "")
            logger.info("[%d/%d] Processing CR# %s", i, len(listings), cr)

            detail = self._fetch_detail(listing)
            attachments = self._download_attachments(
                detail.get("attachment_urls", []), cr,
            )

            rfq = RFQ(
                cr_number=cr,
                title=listing.get("title", ""),
                agency=listing.get("agency", ""),
                category=listing.get("category", ""),
                issue_date=_parse_date(listing.get("issue_date", "")),
                due_date=_parse_date(listing.get("due_date", "")),
                ad_end_date=_parse_date(listing.get("ad_end_date", "")),
                division=listing.get("division", ""),
                location=listing.get("location", ""),
                ad_type=listing.get("ad_type", ""),
                note=listing.get("note", ""),
                detail_url=listing.get("detail_url", ""),
                source_site="nyscr",
                raw_text=detail.get("raw_text", ""),
                attachment_paths=attachments,
                sdvob_goal=detail.get("sdvob_goal"),
                mbe_goal=detail.get("mbe_goal"),
                wbe_goal=detail.get("wbe_goal"),
                created_at=datetime.now(),
            )
            rfqs.append(rfq)

        logger.info("Scrape complete -- %d RFQs", len(rfqs))
        return rfqs

    # ------------------------------------------------------------- helpers

    def _result_count(self) -> int:
        html = self._page.content()
        soup = BeautifulSoup(html, "html.parser")
        h2 = soup.select_one("h2")
        if h2:
            m = re.search(r"(\d[\d,]*)", h2.get_text())
            if m:
                return int(m.group(1).replace(",", ""))
        return 0

    @staticmethod
    def _save_raw_html(html: str, page_num: int) -> None:
        path = _RAW_DIR / f"search_page_{page_num}.html"
        path.write_text(html, encoding="utf-8")


# ================================================================ utilities

def _abs(href: str) -> str:
    """Turn a relative href into an absolute NYSCR URL."""
    if href.startswith("http"):
        return href
    return f"{config.NYSCR_BASE_URL}{href}"


def _is_attachment(href: str) -> bool:
    lower = href.lower().split("?")[0]
    return any(
        lower.endswith(ext)
        for ext in (".pdf", ".xlsx", ".xls", ".csv", ".doc", ".docx", ".zip")
    )


def _save_screenshot(page, name: str) -> Path:
    dest = _RAW_DIR / f"{name}.png"
    page.screenshot(path=str(dest))
    logger.warning("Screenshot saved: %s", dest)
    return dest
