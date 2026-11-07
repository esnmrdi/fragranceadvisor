"""Shared Patchright browser helpers for the FragranceArchiver crawlers."""

import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import sleep

from lxml import html
from patchright.sync_api import Error as PatchrightError, sync_playwright

BASE_URL = "https://www.fragrantica.com"
REQUEST_TIMEOUT_MS = 60000
REQUEST_DELAYS = (2.6, 3.6, 4.2, 5.7, 6.1)
RATE_LIMIT_COOLDOWN_SECONDS = 300
RETRY_AFTER_BUFFER_SECONDS = 2
HEADLESS = False


class CloudflareChallengeError(RuntimeError):
    """Raised when a Cloudflare challenge/interstitial is detected."""


# Everything a crawl can raise while fetching: Patchright errors (navigation timeouts, a
# closed browser) do not derive from RuntimeError, so they must be listed explicitly.
FETCH_ERRORS = (PatchrightError, RuntimeError, OSError)


def cloudflare_challenge_reason(page):
    """Return a diagnostic reason if the current page appears to be a challenge."""
    final_url = page.url.lower()
    if "__cf_chl_rt_tk" in final_url or "/cdn-cgi/challenge-platform/" in final_url:
        return "Cloudflare challenge URL detected"

    try:
        title = page.title().strip().lower()
    except PatchrightError:
        title = ""

    if title.startswith(("just a moment", "attention required")):
        return "Cloudflare challenge/interstitial title detected: {!r}".format(title)

    try:
        body_text = page.locator("body").inner_text(timeout=3000).lower()
    except PatchrightError:
        body_text = ""

    phrases = (
        "verify you are human",
        "performing security verification",
        "checking your browser",
        "enable javascript and cookies to continue",
    )
    if any(phrase in body_text for phrase in phrases):
        return "Cloudflare verification text detected in page body"

    return None


class BrowserClient:
    """Own a visible Patchright Chromium browser and its page/context."""

    def __init__(self, headless=HEADLESS, timeout_ms=REQUEST_TIMEOUT_MS):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        try:
            self.browser = self._playwright.chromium.launch(headless=self.headless)
            self.context = self.browser.new_context()
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout_ms)
        except BaseException:
            # __exit__ is not called when __enter__ fails; don't leak the driver process.
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.browser is not None:
                self.browser.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()

    @staticmethod
    def _pace_request(url, operation):
        """Add a small randomized pause before each outbound request."""
        delay = random.uniform(*REQUEST_DELAYS)
        print(
            "Waiting {:.1f} seconds before {} {}.".format(delay, operation, url),
            flush=True,
        )
        sleep(delay)

    @staticmethod
    def _rate_limit_wait(url, headers, operation):
        """Honor Retry-After, or use the five-minute fallback, plus a safety buffer."""
        retry_after = headers.get("retry-after")
        wait_seconds = RATE_LIMIT_COOLDOWN_SECONDS

        if retry_after:
            try:
                # Retry-After may be a number of seconds.
                wait_seconds = max(0.0, float(retry_after.strip()))
            except (AttributeError, TypeError, ValueError):
                try:
                    # Or it may be an HTTP-date.
                    retry_date = parsedate_to_datetime(retry_after)
                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(tzinfo=timezone.utc)
                    wait_seconds = max(
                        0.0,
                        (retry_date - datetime.now(timezone.utc)).total_seconds(),
                    )
                except (TypeError, ValueError, OverflowError):
                    print(
                        "Invalid Retry-After header {!r}; using {}-second fallback.".format(
                            retry_after, RATE_LIMIT_COOLDOWN_SECONDS
                        ),
                        flush=True,
                    )

        wait_seconds += RETRY_AFTER_BUFFER_SECONDS
        print(
            "HTTP 429 while {} {}. Waiting at least {:.1f} seconds before retrying.".format(
                operation, url, wait_seconds
            ),
            flush=True,
        )
        sleep(wait_seconds)

    def fetch_tree(self, url, timeout_ms=None):
        """Navigate, retry HTTP 429 after the required cooldown, and parse HTML."""
        while True:
            self._pace_request(url, "loading")
            response = self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_ms or self.timeout_ms,
            )
            if response is None:
                raise RuntimeError("No HTTP response received for {}".format(url))

            # Handle 429 before challenge and generic HTTP error checks.
            if response.status == 429:
                self._rate_limit_wait(url, response.headers, "loading")
                continue

            challenge_reason = cloudflare_challenge_reason(self.page)
            if challenge_reason:
                raise CloudflareChallengeError(
                    "{} while loading {} (HTTP {}; final URL: {}).".format(
                        challenge_reason, url, response.status, self.page.url
                    )
                )

            if response.status >= 400:
                detail = "HTTP {} for {}".format(response.status, url)
                raise RuntimeError(detail)

            return html.fromstring(self.page.content())

    def download_image(self, image_url, destination):
        """Download an image, retrying HTTP 429 after the required cooldown."""
        destination = Path(destination)
        if destination.exists():
            return

        destination.parent.mkdir(parents=True, exist_ok=True)

        while True:
            self._pace_request(image_url, "downloading image")
            response = self.context.request.get(
                image_url,
                timeout=self.timeout_ms,
            )
            try:
                if response.status == 429:
                    self._rate_limit_wait(
                        image_url, response.headers, "downloading image"
                    )
                    continue

                if not response.ok:
                    raise RuntimeError(
                        "HTTP {} downloading image {}".format(
                            response.status, image_url
                        )
                    )

                destination.write_bytes(response.body())
                return
            finally:
                response.dispose()
