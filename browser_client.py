"""Shared Patchright browser helpers for the FragranceAdvisor crawlers."""

from pathlib import Path

from lxml import html
from patchright.sync_api import Error as PatchrightError, sync_playwright

BASE_URL = "https://www.fragrantica.com"
REQUEST_TIMEOUT_MS = 60000
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

    def fetch_tree(self, url, timeout_ms=None):
        """Navigate to a page, reject errors/challenges, and parse rendered HTML."""
        response = self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_ms or self.timeout_ms,
        )
        if response is None:
            raise RuntimeError("No HTTP response received for {}".format(url))

        challenge_reason = cloudflare_challenge_reason(self.page)
        if challenge_reason:
            raise CloudflareChallengeError(
                "{} while loading {} (HTTP {}; final URL: {}).".format(
                    challenge_reason, url, response.status, self.page.url
                )
            )

        if response.status >= 400:
            retry_after = response.headers.get("retry-after")
            detail = "HTTP {} for {}".format(response.status, url)
            if retry_after:
                detail += " (Retry-After: {})".format(retry_after)
            raise RuntimeError(detail)

        return html.fromstring(self.page.content())

    def download_image(self, image_url, destination):
        """Download an image using this browser context's request client."""
        destination = Path(destination)
        if destination.exists():
            return

        response = self.context.request.get(
            image_url,
            timeout=self.timeout_ms,
        )
        try:
            if not response.ok:
                raise RuntimeError(
                    "HTTP {} downloading image {}".format(response.status, image_url)
                )
            destination.write_bytes(response.body())
        finally:
            response.dispose()
