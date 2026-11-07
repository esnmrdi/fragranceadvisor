"""Scrape perfume details using Patchright and save them to SQLite."""

import argparse
import json
import re
import unicodedata
from pathlib import Path
from time import sleep

from browser_client import FETCH_ERRORS, BrowserClient
from db_helper import PerfumesDBHelper

REQUEST_DELAY_SECONDS = 5
IMAGE_DIR = Path("fragrantica_images/perfumes")
PERFUME_URL = re.compile(
    r"/perfume/(?P<brand>[^/]+)/(?P<title>.+)-\d+\.html?$",
    re.IGNORECASE,
)
YEAR = r"(1[5-9]\d\d|20\d\d)"
EDGE_PUNCTUATION = " ,;:|•–—-\"“”"


def note_titles(tree, label):
    """Note names listed under a pyramid heading such as 'Top Notes'."""
    imgs = tree.xpath("//p[b/text()='{}']/span[@class='rtgNote']/img".format(label))
    return [img.get("title") for img in imgs] or None


def _skeleton_pair(text):
    """Lowercase letters and digits of `text`, in two forms: accents folded (é -> e) and
    accented letters dropped (é -> nothing). URL slugs treat accents either way."""
    folded = unicodedata.normalize("NFKD", text).lower()
    plain = unicodedata.normalize("NFC", text).lower()
    return (
        "".join(ch for ch in folded if ch.isascii() and ch.isalnum()),
        "".join(ch for ch in plain if ch.isascii() and ch.isalnum()),
    )


def find_name(texts, slug_text):
    """Recover a properly written name from the page.

    The URL slug has lost apostrophes, periods, ampersands and accents ("Victoria-s-Secret"),
    but it keeps the letters and digits in order. So look through `texts` (most reliable first)
    for a run of words that reduces to the same letters and digits as the slug and return
    those words as written on the page. Returns None when nothing on the page matches; the
    caller then keeps the slug's version.
    """
    wanted = set(_skeleton_pair(slug_text)) - {""}
    if not wanted:
        return None
    longest = max(len(skeleton) for skeleton in wanted)
    for text in texts:
        words = text.split()
        pairs = [_skeleton_pair(word) for word in words]
        for start, first in enumerate(pairs):
            if not any(first):
                continue  # a name starts on a real word, not on a lone '&' or '-'
            fold = plain = ""
            for end in range(start, len(words)):
                fold += pairs[end][0]
                plain += pairs[end][1]
                if any(pairs[end]) and {fold, plain} & wanted:
                    name = " ".join(words[start:end + 1]).strip(EDGE_PUNCTUATION)
                    return unicodedata.normalize("NFC", name)  # one form for accents, whatever the page used
                if len(fold) > longest and len(plain) > longest:
                    break
    return None


def page_name_candidates(tree):
    """Texts on the page that spell out the brand and the perfume name, most specific first."""
    texts = []
    for xpath in (
        "//a[contains(@href, '/designers/')]//text()",  # brand link, one string per node
        "//*[@itemprop='name']//text()",
    ):
        texts += tree.xpath(xpath)
    texts.append(" ".join(tree.xpath("(//h1)[1]/text()")))   # the name without its <small> suffix
    texts.append(" ".join(tree.xpath("(//h1)[1]//text()")))
    texts += tree.xpath("//meta[@property='og:title']/@content")
    texts += tree.xpath("//title/text()")
    seen, ordered = set(), []
    for text in texts:
        text = " ".join(str(text).split())
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def launch_year(page_title, tree):
    """The year the page title ends with, else the 'launched in YYYY' sentence; None if neither."""
    match = re.search(r"(?<!\d)" + YEAR + r"\s*$", page_title)
    if match:
        return match.group(1)
    body = " ".join(tree.xpath("//body//text()[not(ancestor::script) and not(ancestor::style)]"))
    match = re.search(r"\blaunched in " + YEAR + r"\b", body)
    return match.group(1) if match else None


def scrape_perfume(client, url):
    """Fetch and parse one perfume page. Returns (perfume dict, record tuple)."""
    match = PERFUME_URL.search(url)
    if not match:
        raise ValueError("Unrecognised perfume URL: {}".format(url))

    url_brand = match.group("brand").replace("-", " ")
    url_title = match.group("title").replace("-", " ")
    tree = client.fetch_tree(url)

    names = page_name_candidates(tree)
    page_brand = find_name(names, url_brand)
    page_title_name = find_name(names, url_title)
    brand = page_brand or url_brand

    image_urls = tree.xpath("//meta[@property='og:image']/@content")
    if image_urls:
        perfume_image_url = image_urls[0]
        perfume_image_file_name = perfume_image_url.split("/")[-1]
        client.download_image(
            perfume_image_url, IMAGE_DIR / perfume_image_file_name
        )
    else:
        perfume_image_file_name = None

    page_titles = tree.xpath("//title/text()")
    page_title = " ".join(page_titles[0].split()) if page_titles else ""
    perfume = {
        "title": page_title_name or url_title,
        "image": perfume_image_file_name,
        # Where each name came from, so clean.py only re-cases the slug-derived ones.
        "title_source": "page" if page_title_name else "url",
        "brand_source": "page" if page_brand else "url",
        # Raw page title, kept so names and years can be re-derived without re-crawling.
        "page_title": page_title,
    }

    main_accords = [
        accord for accord in tree.xpath("//div[@id='prettyPhotoGallery']/div/div/span/text()")
        if accord not in ("Videos", "Pictures", "main accords")
    ] or None

    notes_captions = tree.xpath("//h3/text()")
    if "Fragrance Notes" in notes_captions:
        note_tags = tree.xpath("//span[@class='rtgNote']/img")
        notes = {"general": [tag.get("title") for tag in note_tags]}
    elif "Perfume Pyramid" in notes_captions:
        notes = {
            "top": note_titles(tree, "Top Notes"),
            "middle": note_titles(tree, "Middle Notes"),
            "base": note_titles(tree, "Base Notes"),
        }
    else:
        notes = None

    longevity_votes = tree.xpath("//table[@class='voteLS long']/tr/td[@class='ndSum']/text()")
    if len(longevity_votes) >= 5:
        longevity = {
            "poor": longevity_votes[0], "weak": longevity_votes[1],
            "moderate": longevity_votes[2], "long lasting": longevity_votes[3],
            "very long lasting": longevity_votes[4],
        }
    else:
        longevity = None

    sillage_votes = tree.xpath("//table[@class='voteLS sil']/tr/td[@class='ndSum']/text()")
    if len(sillage_votes) >= 4:
        sillage = {
            "soft": sillage_votes[0], "moderate": sillage_votes[1],
            "heavy": sillage_votes[2], "enormous": sillage_votes[3],
        }
    else:
        sillage = None

    record = (
        brand, json.dumps(perfume), launch_year(page_title, tree), json.dumps(main_accords),
        json.dumps(notes), json.dumps(longevity), json.dumps(sillage),
    )
    return perfume, record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default="perfumes.sqlite", help="SQLite file to write (default: %(default)s)"
    )
    parser.add_argument(
        "--limit", type=int,
        help="scrape at most this many pages; try it with a scratch --db before a full crawl",
    )
    args = parser.parse_args(argv)

    db = PerfumesDBHelper(args.db)
    db.setup()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open("perfumes_manifest.txt", encoding="utf-8") as manifest:
        perfume_urls = [line.strip() for line in manifest if line.strip()]

    number_of_perfumes = len(perfume_urls)
    start_index = db.number_of_records()
    end_index = number_of_perfumes
    if args.limit is not None:
        end_index = min(number_of_perfumes, start_index + args.limit)
    from_page = {"title": 0, "brand": 0}

    try:
        with BrowserClient() as client:
            for index in range(start_index, end_index):
                url = perfume_urls[index]
                perfume, record = scrape_perfume(client, url)
                from_page["title"] += perfume["title_source"] == "page"
                from_page["brand"] += perfume["brand_source"] == "page"
                print({
                    "count": "{}/{}".format(index + 1, number_of_perfumes),
                    "brand": record[0],
                    "title": perfume["title"],
                    "year": record[2],
                    "names_from": "{}/{}".format(perfume["title_source"], perfume["brand_source"]),
                })
                db.add_record(record)
                sleep(REQUEST_DELAY_SECONDS)
    except (*FETCH_ERRORS, ValueError) as exc:
        print(
            "Stopped at row {}: {}. Fix the problem and re-run to resume from this row.".format(
                db.number_of_records(), exc
            )
        )
        return 1
    finally:
        db.close()

    scraped = end_index - start_index
    if scraped > 0:
        print(
            "Done: {} page(s). Names written as on the page: {} titles, {} brands "
            "(the rest fall back to the URL slug).".format(
                scraped, from_page["title"], from_page["brand"]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
