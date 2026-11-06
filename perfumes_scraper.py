"""Scrape perfume details using Patchright and save them to SQLite."""

import json
import re
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


def note_titles(tree, label):
    """Note names listed under a pyramid heading such as 'Top Notes'."""
    imgs = tree.xpath("//p[b/text()='{}']/span[@class='rtgNote']/img".format(label))
    return [img.get("title") for img in imgs] or None


def scrape_perfume(client, url):
    """Fetch and parse one perfume page. Returns (perfume dict, record tuple)."""
    match = PERFUME_URL.search(url)
    if not match:
        raise ValueError("Unrecognised perfume URL: {}".format(url))

    brand = match.group("brand").replace("-", " ")
    perfume_title = match.group("title").replace("-", " ")
    tree = client.fetch_tree(url)

    image_urls = tree.xpath("//meta[@property='og:image']/@content")
    if image_urls:
        perfume_image_url = image_urls[0]
        perfume_image_file_name = perfume_image_url.split("/")[-1]
        client.download_image(
            perfume_image_url, IMAGE_DIR / perfume_image_file_name
        )
    else:
        perfume_image_file_name = None

    perfume = {"title": perfume_title, "image": perfume_image_file_name}
    page_titles = tree.xpath("//title/text()")
    launch_year = page_titles[0].strip()[-4:] if page_titles else None
    if launch_year is not None and not launch_year.isdigit():
        launch_year = None

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
        brand, json.dumps(perfume), launch_year, json.dumps(main_accords),
        json.dumps(notes), json.dumps(longevity), json.dumps(sillage),
    )
    return perfume, record


def main():
    db = PerfumesDBHelper("perfumes.sqlite")
    db.setup()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open("perfumes_manifest.txt", encoding="utf-8") as manifest:
        perfume_urls = [line.strip() for line in manifest if line.strip()]

    number_of_perfumes = len(perfume_urls)
    start_index = db.number_of_records()

    try:
        with BrowserClient() as client:
            for index in range(start_index, number_of_perfumes):
                url = perfume_urls[index]
                perfume, record = scrape_perfume(client, url)
                print({
                    "count": "{}/{}".format(index + 1, number_of_perfumes),
                    "brand": record[0],
                    "perfume": perfume,
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
