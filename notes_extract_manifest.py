from lxml import html
import requests


def main():
    with open("notes_manifest.txt", "w", encoding="utf-8") as f:
        page = requests.get("http://www.fragrantica.com/notes/")
        tree = html.fromstring(page.content)
        page.close()
        note_urls = tree.xpath("//div[@class='notebox']/a/@href")
        for note_url in note_urls:
            url = note_url + "\n"
            f.write(url)
            print(url)


if __name__ == "__main__":
    main()
