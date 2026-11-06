"""Discover perfume URLs with Patchright and maintain a resumable manifest."""

import json
import re
from pathlib import Path
from time import sleep
from urllib.parse import urljoin, urlsplit

from browser_client import BASE_URL, FETCH_ERRORS, BrowserClient, CloudflareChallengeError

REQUEST_DELAY_SECONDS = 10
OUTPUT_PATH = Path("perfumes_manifest.txt")
TEMP_OUTPUT_PATH = Path("perfumes_manifest.txt.tmp")
STATE_PATH = Path("perfumes_manifest.state.json")
LEGACY_TEMP_PATH = Path("manifest.txt.tmp")
LEGACY_OUTPUT_PATH = Path("manifest.txt")

COUNTRIES = [
    "United States", "France", "Italy", "United Kingdom", "United Arab Emirates", "Germany",
    "Brazil", "Russia", "Spain", "Netherlands", "Australia", "Turkey", "Japan", "South Korea",
    "Canada", "Sweden", "Switzerland", "Poland", "Romania", "Saudi Arabia", "China", "Portugal",
    "India", "Mexico", "Thailand",
]

BRAND_PATH = re.compile(r"/designers/[^/]+\.html$", re.IGNORECASE)
PERFUME_PATH = re.compile(r"/perfume/[^/]+/[^/]+-\d+\.html?$", re.IGNORECASE)


def migrate_legacy_manifest():
    """Preserve URL lists written by older versions using manifest.txt names."""
    if TEMP_OUTPUT_PATH.exists():
        return
    if LEGACY_TEMP_PATH.exists():
        LEGACY_TEMP_PATH.replace(TEMP_OUTPUT_PATH)
        print("Resuming from legacy temporary manifest: {}".format(TEMP_OUTPUT_PATH))
    elif LEGACY_OUTPUT_PATH.exists() and not OUTPUT_PATH.exists():
        LEGACY_OUTPUT_PATH.replace(TEMP_OUTPUT_PATH)
        print("Migrated legacy manifest to {}".format(TEMP_OUTPUT_PATH))


def load_progress():
    """Return the next country/designer position and URLs already checkpointed."""
    migrate_legacy_manifest()
    seen = set()
    if TEMP_OUTPUT_PATH.exists():
        with TEMP_OUTPUT_PATH.open(encoding="utf-8") as manifest:
            seen = {line.strip() for line in manifest if line.strip()}

    if STATE_PATH.exists():
        with STATE_PATH.open(encoding="utf-8") as state_file:
            state = json.load(state_file)
        country_index = int(state.get("country_index", 0))
        brand_index = int(state.get("brand_index", 0))
        if not 0 <= country_index <= len(COUNTRIES) or brand_index < 0:
            raise ValueError("Invalid crawl position in {}".format(STATE_PATH))
        return country_index, brand_index, seen

    return 0, 0, seen


def save_progress(country_index, brand_index):
    """Atomically save the next position to process."""
    temporary_state = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
    with temporary_state.open("w", encoding="utf-8") as state_file:
        json.dump({"country_index": country_index, "brand_index": brand_index}, state_file)
        state_file.flush()
    temporary_state.replace(STATE_PATH)


def main():
    try:
        country_index, brand_index, seen = load_progress()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("Could not read crawl checkpoint: {}".format(exc))
        return 1

    print(
        "Starting at country {}/{}; {} unique URLs already saved.".format(
            min(country_index + 1, len(COUNTRIES)), len(COUNTRIES), len(seen)
        )
    )

    try:
        with BrowserClient() as client:
            with TEMP_OUTPUT_PATH.open("a", encoding="utf-8") as output:
                for current_country_index in range(country_index, len(COUNTRIES)):
                    country = COUNTRIES[current_country_index]
                    country_url = urljoin(BASE_URL, "/country/{}.html".format(country))
                    print("[Country] {}".format(country_url))
                    country_tree = client.fetch_tree(country_url)
                    sleep(REQUEST_DELAY_SECONDS)

                    brand_hrefs = list(dict.fromkeys(
                        href for href in country_tree.xpath(
                            "//a[contains(@href, '/designers/')]/@href"
                        )
                        if BRAND_PATH.fullmatch(urlsplit(href).path)
                    ))

                    start_brand = brand_index if current_country_index == country_index else 0
                    if start_brand > len(brand_hrefs):
                        raise ValueError(
                            "Checkpoint designer index {} exceeds {} designers for {}".format(
                                start_brand, len(brand_hrefs), country
                            )
                        )

                    for current_brand_index in range(start_brand, len(brand_hrefs)):
                        brand_url = urljoin(BASE_URL, brand_hrefs[current_brand_index])
                        print("[Designer {}/{}] {}".format(
                            current_brand_index + 1, len(brand_hrefs), brand_url
                        ))
                        brand_tree = client.fetch_tree(brand_url)

                        perfume_hrefs = list(dict.fromkeys(
                            href for href in brand_tree.xpath(
                                "//a[contains(@href, '/perfume/')]/@href"
                            )
                            if PERFUME_PATH.fullmatch(urlsplit(href).path)
                        ))

                        added = 0
                        for perfume_href in perfume_hrefs:
                            perfume_url = urljoin(BASE_URL, perfume_href)
                            if perfume_url in seen:
                                continue
                            seen.add(perfume_url)
                            output.write(perfume_url + "\n")
                            added += 1

                        output.flush()
                        if current_brand_index + 1 < len(brand_hrefs):
                            save_progress(current_country_index, current_brand_index + 1)
                        else:
                            save_progress(current_country_index + 1, 0)

                        print("[Saved] {} new URLs; {} total unique URLs.".format(
                            added, len(seen)
                        ))
                        sleep(REQUEST_DELAY_SECONDS)

                    save_progress(current_country_index + 1, 0)
                    brand_index = 0

        if not seen:
            print("No perfume URLs were found; the existing manifest was not replaced.")
            return 1

        TEMP_OUTPUT_PATH.replace(OUTPUT_PATH)
        STATE_PATH.unlink(missing_ok=True)
        print("Completed: saved {} unique perfume URLs to {}.".format(len(seen), OUTPUT_PATH))
        return 0

    except CloudflareChallengeError as exc:
        print("Cloudflare challenge detected; crawl paused without advancing the checkpoint.")
        print("{}".format(exc))
        print("Progress remains in {} and {}. Resume later when normal access is available.".format(
            TEMP_OUTPUT_PATH, STATE_PATH
        ))
        return 1
    except (*FETCH_ERRORS, ValueError) as exc:
        print(
            "Crawl stopped: {}. Progress remains in {} and {}. "
            "Wait before rerunning; the crawler will resume from its checkpoint.".format(
                exc, TEMP_OUTPUT_PATH, STATE_PATH
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
