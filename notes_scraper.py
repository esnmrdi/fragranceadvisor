"""Scrape note pages and download their images using Patchright."""

import json
from pathlib import Path
from time import sleep
from urllib.parse import urljoin

from browser_client import FETCH_ERRORS, BrowserClient
from db_helper import NotesDBHelper

REQUEST_DELAY_SECONDS = 5
IMAGE_DIR = Path("fragrantica_images/notes")


def scrape_note(client, url):
    """Fetch one note page and save its images. Returns (title, image file names)."""
    tree = client.fetch_tree(url)
    titles = tree.xpath("//h1/text()")
    if not titles:
        raise ValueError("No title found on {}".format(url))

    note_title = titles[0]
    note_image_file_names = []
    for image_url in tree.xpath("//h3/following-sibling::div/div/img/@src"):
        image_file_name = image_url.split("/")[-1]
        note_image_file_names.append(image_file_name)
        client.download_image(
            urljoin(url, image_url), IMAGE_DIR / image_file_name
        )

    return note_title, note_image_file_names


def main():
    db = NotesDBHelper("notes.sqlite")
    db.setup()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    with open("notes_manifest.txt", encoding="utf-8") as manifest:
        note_urls = [line.strip() for line in manifest if line.strip()]

    number_of_notes = len(note_urls)
    start_index = db.number_of_records()

    try:
        with BrowserClient() as client:
            for index in range(start_index, number_of_notes):
                note_title, image_names = scrape_note(client, note_urls[index])
                print({
                    "count": "{}/{}".format(index + 1, number_of_notes),
                    "note": note_title,
                })
                db.add_record((note_title, json.dumps(image_names)))
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
