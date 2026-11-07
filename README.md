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
bypass. Requests are sequential and paced by randomized delays in
`browser_client.py`.

HTTP 429 responses are retried for the same URL after the server's
`Retry-After` interval plus a two-second buffer. If that header is missing or
invalid, the client waits five minutes plus the buffer. Other HTTP errors and
Cloudflare challenges stop the current crawl without marking the URL complete.

## Perfume URL discovery

Run:

```bash
python perfumes_extract_manifest.py
```

The browser opens visibly. The crawler visits country and designer pages. It
writes discovered URLs incrementally to `perfumes_manifest.txt.tmp` and saves
its next country/designer position in `perfumes_manifest.state.json`.

If an HTTP error or a Cloudflare challenge is detected, the crawl stops and
preserves the manifest and checkpoint. If a challenge page appears, handle
access through the browser/site's normal supported process; the crawler does
not attempt to bypass it. Rerun the script to resume from its saved position.

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

The notes index is a single-page discovery step, so it has no per-page crawl
checkpoint. It deduplicates the extracted URLs and writes to
`notes_manifest.txt.tmp` first, then atomically replaces `notes_manifest.txt`
only after successful extraction. A failed request or write leaves the
previous completed manifest untouched. Rerunning repeats this one-page
discovery operation.

## Scraping and URL-based resume

Run:

```bash
python perfumes_scraper.py
python notes_scraper.py
```

Each scraper records completed source URLs in a `scrape_progress` table in its
own SQLite database (`perfumes.sqlite` or `notes.sqlite`). A scraped data row
and its URL completion marker are committed in one transaction. On restart,
the scraper reads the completion ledger and processes only URLs not yet
recorded as complete. It can therefore resume even if manifest entries are
reordered or new URLs are added.

Images are downloaded through the same browser context and stored in
`fragrantica_images/perfumes/` and `fragrantica_images/notes/`.

### Existing database migration

Older database files do not have URL completion records. On the first run with
this version, the scraper seeds the progress table from the first N unique URLs
in the current manifest, where N is the existing number of database records.
This preserves the old sequential-resume behavior **only if the manifest is
still in the same order and contains the original entries**. Verify that before
the first upgraded run. If the manifest was reordered, edited, or shortened,
do not let the automatic migration run: back up the database and reconcile
records to source URLs first. After migration, URL-based tracking is used.

The progress ledger is stored inside the existing SQLite database, so it is
backed up together with the scraped records. Do not delete the
`scrape_progress` table if you want URL-based resume to work.

### Names and years

Fragrantica's URLs have already lost apostrophes, periods, ampersands and
accents (`Victoria-s-Secret`), so building names from the URL gives
`Victoria S Secret`. `perfumes_scraper.py` therefore looks through the page's own
text for the words whose letters and digits match the URL and keeps them as
written there (`Victoria's Secret`, `D.S. & Durga`, `Bohème`). If nothing on the
page matches, it falls back to the URL's spelling. The launch year comes from the
page title, or from the "launched in YYYY" sentence when the title has none.

Each row records where its names came from (`title_source` / `brand_source`,
either `page` or `url`) and the raw page title inside the `perfume` JSON, so
names and years can be re-derived later without re-crawling. `clean.py` leaves
`page` names exactly as scraped and only re-cases the `url` ones.

### Trying it before a long crawl

Check the extraction on a few pages with a scratch database first (`--limit` counts pages still to do):

```bash
python perfumes_scraper.py --db scratch.sqlite --limit 20
```

Each printed row shows `names_from`, which should be `page/page` for nearly
every perfume. The final lines count how many names came from the page and how
many rows have a year, accords, notes, longevity and sillage. A field that is
near zero means the site's page layout changed and its selectors need updating,
which is much cheaper to find out here than after a full crawl. Delete
`scratch.sqlite` afterwards.

Fragrantica redesigned its pages after the original data was collected, so
`perfumes_scraper.py` reads both layouts (the new one first). Accords and notes
are in the page HTML and are read from there. Longevity and sillage votes are
filled in by script after the page opens, so they may come back empty until the
scraper scrolls and waits for them.

### Rebuilding the database

Progress is tracked per URL in the `scrape_progress` table of `perfumes.sqlite`, so
with the existing (complete) file the scraper has nothing left to do. To re-scrape
everything, move or delete `perfumes.sqlite` first (an old database without that table
is migrated by row position, which would carry over its known gaps), then rerun the
scraper and the export/clean/build steps below. Perfume ids and slugs are derived from
the names, so they change wherever a name changes.

## Pipeline

1. `perfumes_extract_manifest.py` / `notes_extract_manifest.py` - collect page URLs.
2. `perfumes_scraper.py` / `notes_scraper.py` - scrape URLs into
   `perfumes.sqlite` / `notes.sqlite`.
3. `export.py` - export `perfumes.sqlite` to `perfumes.json`.
4. `clean.py` - normalize `perfumes.json` into `perfumes_clean.json`. Perfumes
   whose Fragrantica page has no title are dropped (`--keep-unnamed` keeps them).
5. `build_app_db.py` - build the searchable `app.db` from `perfumes_clean.json`.

`perfumes.json` and `perfumes_clean.json` are generated intermediates and
are not tracked in git; `perfumes.sqlite`, `notes.sqlite` and the manifests
are the source data, and `app.db` is the shipped output. After re-scraping or
changing `clean.py`, rerun steps 3-5 so `app.db` stays in sync:

```bash
python export.py && python clean.py --report && python build_app_db.py
```

`check_db.py` prints sample rows from `perfumes.sqlite` for a quick sanity
check. `db_helper.py` holds the SQLite helpers and URL completion ledger used
by both scrapers.
