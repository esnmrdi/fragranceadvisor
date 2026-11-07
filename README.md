# fragrancearchiver

A Python project for collecting fragrance specifications.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
patchright install chromium
```

The four crawling scripts use a shared visible Chromium browser through
Patchright. They use ordinary browser navigation and page rendering, with no
stealth settings, CAPTCHA solvers, proxy rotation, or automated challenge
bypass. Requests are sequential and deliberately paced.

## Perfume URL discovery

Run:

```bash
python perfumes_extract_manifest.py
```

The browser opens visibly. The crawler visits country and designer pages with a
10-second delay between page requests. It writes discovered URLs incrementally
to `perfumes_manifest.txt.tmp` and saves its next country/designer position in
`perfumes_manifest.state.json`.

If an HTTP error or a Cloudflare challenge is detected, the crawl stops and
preserves the manifest and checkpoint. If a challenge page appears, handle
access through the browser/site's normal supported process; the crawler does
not attempt to bypass it. The crawler resumes from its saved position when run
again.

Do not delete the temporary manifest or state file if you want to resume. Once
all countries are processed, the temporary manifest is renamed to
`perfumes_manifest.txt`.

The crawler also migrates legacy `manifest.txt.tmp` or `manifest.txt` files
to the new `perfumes_manifest.txt.tmp` checkpoint name when appropriate.
If a legacy manifest exists without a checkpoint, its URLs are retained and
discovery safely restarts from the first country, skipping duplicates.

## Notes manifest

Run:

```bash
python notes_extract_manifest.py
```

The script writes `notes_manifest.txt` only after it successfully extracts
note links. A failed request leaves the previous manifest untouched.

## Scraping

Run:

```bash
python perfumes_scraper.py
python notes_scraper.py
```

Both scrapers use the shared Patchright browser client and download images
through the same browser context. They retain the existing SQLite schemas and
resume from the number of records already saved.

## Pipeline

1. `perfumes_extract_manifest.py` / `notes_extract_manifest.py` - collect page URLs.
2. `perfumes_scraper.py` / `notes_scraper.py` - scrape URLs into
   `perfumes.sqlite` / `notes.sqlite`.
3. `export.py` - export `perfumes.sqlite` to `perfumes.json`.
4. `clean.py` - normalize `perfumes.json` into `perfumes_clean.json`. Perfumes
   whose Fragrantica page has no title are dropped (`--keep-unnamed` keeps them).
5. `build_app_db.py` - build the searchable `app.db` from `perfumes_clean.json`.

`perfumes.json` and `perfumes_clean.json` are generated intermediates and are
not tracked in git; `perfumes.sqlite`, `notes.sqlite` and the manifests are the
source data, and `app.db` is the shipped output. After re-scraping or changing
`clean.py`, rerun steps 3-5 so `app.db` stays in sync:

```bash
python export.py && python clean.py --report && python build_app_db.py
```

`check_db.py` prints sample rows from `perfumes.sqlite` for a quick sanity
check. `db_helper.py` holds the SQLite helpers the two scrapers write through.
