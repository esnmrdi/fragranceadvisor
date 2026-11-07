"""Extract the Fragrantica note manifest and replace it atomically."""

from pathlib import Path
from urllib.parse import urljoin

from browser_client import BASE_URL, FETCH_ERRORS, BrowserClient

OUTPUT_PATH = Path("notes_manifest.txt")
TEMP_OUTPUT_PATH = Path("notes_manifest.txt.tmp")


def main():
    # Fetch and validate the page before touching the existing manifest.
    try:
        with BrowserClient() as client:
            tree = client.fetch_tree(urljoin(BASE_URL, "/notes/"))
    except FETCH_ERRORS as exc:
        print("Could not fetch the notes page; {} was not changed: {}".format(
            OUTPUT_PATH, exc
        ))
        return 1

    note_urls = list(dict.fromkeys(
        urljoin(BASE_URL, href)
        for href in tree.xpath("//div[@class='notebox']/a/@href")
        if href.strip()
    ))
    if not note_urls:
        print("No note URLs were found; {} was not changed.".format(OUTPUT_PATH))
        return 1

    try:
        with TEMP_OUTPUT_PATH.open("w", encoding="utf-8") as output:
            for url in note_urls:
                output.write(url + "\n")
            output.flush()
        TEMP_OUTPUT_PATH.replace(OUTPUT_PATH)
    except OSError as exc:
        print("Could not save {}: {}".format(OUTPUT_PATH, exc))
        return 1

    print("Saved {} unique note URLs to {}.".format(len(note_urls), OUTPUT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
