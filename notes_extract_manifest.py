"""Extract the Fragrantica note manifest with Patchright."""

from urllib.parse import urljoin

from browser_client import BASE_URL, FETCH_ERRORS, BrowserClient


def main():
    # Fetch first and write afterwards, so a failed request cannot wipe the existing manifest.
    try:
        with BrowserClient() as client:
            tree = client.fetch_tree(urljoin(BASE_URL, "/notes/"))
    except FETCH_ERRORS as exc:
        print("Could not fetch the notes page; notes_manifest.txt was not changed: {}".format(exc))
        return 1

    note_urls = [
        urljoin(BASE_URL, href)
        for href in tree.xpath("//div[@class='notebox']/a/@href")
    ]
    if not note_urls:
        print("No note URLs were found; notes_manifest.txt was not changed.")
        return 1

    with open("notes_manifest.txt", "w", encoding="utf-8") as output:
        for url in note_urls:
            output.write(url + "\n")
            print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
