"""Polite HTTP fetching: rotating user agents, random delays, robots.txt, Playwright fallback."""
import logging
import os
import random
import re
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger("pricewatch.fetch")

# Plain-HTTP requests present as Safari. Bot managers (Akamai and friends) compare the User-Agent with the
# TLS fingerprint and client-hint headers; a Chrome or Firefox UA coming from Python's TLS stack is an
# instant 403, while Safari sends no client hints and gets a lenient profile. The headless browser path
# builds its own UA from the real Chromium version (see get_rendered).
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
]


def client_hints(ua: str) -> dict:
    """Chromium browsers always send these next to their User-Agent. A Chrome UA without them is an easy
    bot tell (Akamai answers such requests with HTTP 400), so add the matching set."""
    m = re.search(r"(?:Chrome|Chromium)/(\d+)", ua)
    if not m:
        return {}
    v = m.group(1)
    brand = "Microsoft Edge" if "Edg/" in ua else "Google Chrome"
    platform = "macOS" if "Macintosh" in ua else "Linux" if "X11" in ua else "Windows"
    return {"Sec-CH-UA": f'"Chromium";v="{v}", "Not;A=Brand";v="24", "{brand}";v="{v}"',
            "Sec-CH-UA-Mobile": "?0", "Sec-CH-UA-Platform": f'"{platform}"'}


class FetchError(Exception):
    pass


class RobotsDisallowed(FetchError):
    pass


class Fetcher:
    def __init__(self, min_delay=None, max_delay=None, respect_robots=None, timeout=30):
        self.min_delay = float(min_delay if min_delay is not None else os.getenv("MIN_DELAY", "2"))
        self.max_delay = float(max_delay if max_delay is not None else os.getenv("MAX_DELAY", "6"))
        self.respect_robots = (respect_robots if respect_robots is not None
                               else os.getenv("RESPECT_ROBOTS", "1") != "0")
        self.timeout = timeout
        self.session = requests.Session()
        self._robots = {}
        self._last_request = 0.0
        self._pw = None
        self._browser = None

    # -- politeness -------------------------------------------------------
    def _headers(self):
        ua = random.choice(USER_AGENTS)
        h = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",   # "br" needs the brotli package (requirements.txt)
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none",
        }
        h.update(client_hints(ua))
        return h

    def _throttle(self):
        wait = random.uniform(self.min_delay, self.max_delay)
        elapsed = time.time() - self._last_request
        if self._last_request and elapsed < wait:
            time.sleep(wait - elapsed)
        self._last_request = time.time()

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        host = urlparse(url).netloc
        rp = self._robots.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(f"{urlparse(url).scheme}://{host}/robots.txt",
                                     headers=self._headers(), timeout=15)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:
                    rp.parse([])  # no robots.txt / blocked -> allow
            except requests.RequestException:
                rp.parse([])
            self._robots[host] = rp
        return rp.can_fetch("*", url)

    # -- plain HTTP --------------------------------------------------------
    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self._throttle()
        try:
            r = self.session.get(url, headers=self._headers(), timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as e:
            raise FetchError(f"request failed: {e}") from e
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code}")
        return r.text

    def get_json(self, url: str, referer: str = None):
        """Same politeness rules, but for JSON APIs."""
        if not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self._throttle()
        headers = {**self._headers(), "Accept": "application/json, text/plain, */*"}
        if referer:
            headers["Referer"] = referer
        try:
            r = self.session.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            raise FetchError(f"request failed: {e}") from e
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise FetchError("response was not JSON") from e

    # -- headless browser --------------------------------------------------
    def get_rendered(self, url: str, wait_ms: int = 2500, wait_for: str = None) -> str:
        if not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self._throttle()
        try:
            from playwright.sync_api import sync_playwright, Error as PWError
        except ImportError as e:
            raise FetchError("playwright not installed") from e
        if self._browser is None:
            self._pw = sync_playwright().start()
            # Full Chromium in new-headless mode: passes bot checks (Zara, SSENSE) that block the headless shell.
            try:
                self._browser = self._pw.chromium.launch(channel="chromium", headless=True)
            except PWError:
                self._browser = self._pw.chromium.launch(headless=True)
        # Use the real Chromium major version: Playwright sends Sec-CH-UA from the actual browser, and a UA
        # claiming a different version is an inconsistency bot managers reject outright.
        major = (self._browser.version or "").split(".")[0] or "128"
        ua = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
        ctx = self._browser.new_context(user_agent=ua, locale="en-US", viewport={"width": 1366, "height": 900})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        # Don't waste bandwidth on images/fonts/media; we only need the DOM.
        ctx.route("**/*", lambda route: route.abort()
                  if route.request.resource_type in ("image", "font", "media") else route.continue_())
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=wait_ms + 5000)
                except PWError:
                    pass
            page.wait_for_timeout(wait_ms)
            return page.content()
        except PWError as e:
            raise FetchError(f"browser failed: {str(e).splitlines()[0]}") from e
        finally:
            ctx.close()

    def close(self):
        if self._browser:
            self._browser.close()
            self._pw.stop()
            self._browser = self._pw = None
