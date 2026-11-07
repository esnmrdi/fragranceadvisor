"""Scrape note pages and download their images using Patchright."""

import json
from pathlib import Path
from urllib.parse import urljoin

from browser_client import FETCH_ERRORS, BrowserClient
from db_helper import NotesDBHelper

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
        client.download_image(urljoin(url, image_url), IMAGE_DIR / image_file_name)

    return note_title, note_image_file_names


def main():
    db = NotesDBHelper("notes.sqlite")
    db.setup()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open("notes_manifest.txt", encoding="utf-8") as manifest:
            note_urls = list(dict.fromkeys(
                line.strip() for line in manifest if line.strip()
            ))
        db.migrate_legacy_progress(note_urls)
        completed = db.completed_urls()
    except (OSError, ValueError, RuntimeError) as exc:
        print("Could not prepare notes scrape: {}".format(exc))
        db.close()
        return 1

    total = len(note_urls)
    pending = [url for url in note_urls if url not in completed]
    print(
        "Notes scrape: {} URLs in manifest, {} already complete, {} remaining.".format(
            total, len(completed), len(pending)
        ),
        flush=True,
    )

    try:
        with BrowserClient() as client:
            for position, url in enumerate(pending, start=1):
                note_title, image_names = scrape_note(client, url)
                db.add_record_for_url(url, (note_title, json.dumps(image_names)))
                completed.add(url)
                print({
                    "progress": "{}/{}".format(position, len(pending)),
                    "completed_total": len(completed),
                    "note": note_title,
                }, flush=True)
    except (*FETCH_ERRORS, ValueError) as exc:
        print(
            "Scrape paused: {}. {} URLs are recorded as complete; rerun to continue "
            "with the remaining URLs.".format(exc, len(completed)),
            flush=True,
        )
        return 1
    finally:
        db.close()

    print("Completed: {} note URLs processed.".format(len(completed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
