from lxml import html
import requests
import json
from notes_db_helper import NotesDBHelper
import shutil


def main():
    DB = NotesDBHelper("notes.sqlite")
    DB.setup()
    with open("notes_manifest.txt", "r") as f:
        note_urls = f.readlines()
    number_of_notes = len(note_urls)
    flag = DB.number_of_records()
    for index in range(flag, number_of_notes):
        try:
            url = note_urls[index][:-1]
            page = requests.get(url)
            tree = html.fromstring(page.content)
            note_title = tree.xpath("//h1/text()")[0]
            note_image_urls = tree.xpath("//h3/following-sibling::div/div/img/@src")
            note_image_file_names = []
            for note_image_url in note_image_urls:
                note_image_file_name = note_image_url.split("/")[-1]
                note_image_file_names.append(note_image_file_name)
                r = requests.get("http://www.fragrantica.com" + note_image_url, stream=True)
                if r.status_code == 200:
                    with open("fragrantica_images/notes/" + note_image_file_name, 'wb') as f:
                        r.raw.decode_content = True
                        shutil.copyfileobj(r.raw, f)
            print({"count": "{0}/{1}".format(index, number_of_notes), "note": note_title})
            DB.add_record(tuple([note_title, json.dumps(note_image_file_names)]))
        except requests.exceptions.ConnectionError:
            DB.add_record(tuple([note_title, None]))
            continue

if __name__ == "__main__":
    main()
