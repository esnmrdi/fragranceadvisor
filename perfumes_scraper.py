from lxml import html
import requests
import json
from perfumes_db_helper import PerfumesDBHelper
from urllib import request, error


def represents_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


def main():
    DB = PerfumesDBHelper("perfumes.sqlite")
    DB.setup()
    with open("perfumes_manifest.txt", "r") as f:
        perfume_urls = f.readlines()
    number_of_perfumes = len(perfume_urls)
    flag = DB.number_of_records()
    for index in range(flag, number_of_perfumes):
        try:
            url = perfume_urls[index][:-1]
            page = requests.get(url)
            tree = html.fromstring(page.content)
            brand_and_perfume = url[35:-6].split("/")
            brand = brand_and_perfume[0].replace("-", " ")
            perfume_title = brand_and_perfume[1].split("-")
            perfume_title = " ".join(perfume_title[:-1])
            perfume_image_url = tree.xpath("//meta[@property='og:image']/@content")[0]
            if perfume_image_url:
                perfume_image_file_name = perfume_image_url.split("/")[-1]
                request.urlretrieve(perfume_image_url, "fragrantica_images/perfumes/" + perfume_image_file_name)
            else:
                perfume_image_file_name = None
            perfume = {"title": perfume_title, "image": perfume_image_file_name}
            page_title = tree.xpath("//title/text()")[0]
            if not page_title:
                launch_year = None
            else:
                launch_year = page_title[-4:]
                if not represents_int(launch_year):
                    launch_year = None
            main_accords = tree.xpath("//div[@id='prettyPhotoGallery']/div/div/span/text()")
            if main_accords:
                if "main accords" in main_accords:
                    main_accords.remove("main accords")
                if "Videos" in main_accords:
                    main_accords.remove("Videos")
                if "Pictures" in main_accords:
                    main_accords.remove("Pictures")
            else:
                main_accords = None
            notes_captions = tree.xpath("//h3/text()")
            notes = {}
            if "Fragrance Notes" in notes_captions:
                note_tags = tree.xpath("//span[@class='rtgNote']/img")
                notes["general"] = [note_tag.get("title") for note_tag in note_tags]
            elif "Perfume Pyramid" in notes_captions:
                top_notes = tree.xpath("//p[b/text()='Top Notes']/span[@class='rtgNote']/img")
                middle_notes = tree.xpath("//p[b/text()='Middle Notes']/span[@class='rtgNote']/img")
                base_notes = tree.xpath("//p[b/text()='Base Notes']/span[@class='rtgNote']/img")
                if top_notes:
                    notes["top"] = [top_note.get("title") for top_note in top_notes]
                else:
                    notes["top"] = None
                if middle_notes:
                    notes["middle"] = [middle_note.get("title") for middle_note in middle_notes]
                else:
                    notes["middle"] = None
                if base_notes:
                    notes["base"] = [base_note.get("title") for base_note in base_notes]
                else:
                    notes["base"] = None
            else:
                notes = None
            longevity_votes = tree.xpath("//table[@class='voteLS long']/tr/td[@class='ndSum']/text()")
            if longevity_votes:
                longevity = {"poor": longevity_votes[0], "weak": longevity_votes[1], "moderate": longevity_votes[2],
                             "long lasting": longevity_votes[3], "very long lasting": longevity_votes[4]}
            else:
                longevity = None
            sillage_votes = tree.xpath("//table[@class='voteLS sil']/tr/td[@class='ndSum']/text()")
            if sillage_votes:
                sillage = {"soft": sillage_votes[0], "moderate": sillage_votes[1], "heavy": sillage_votes[2],
                           "enormous": sillage_votes[3]}
            else:
                sillage = None
            print({"count": "{0}/{1}".format(index, number_of_perfumes), "brand": brand, "perfume": perfume})
            DB.add_record(tuple([brand, json.dumps(perfume), launch_year, json.dumps(main_accords), json.dumps(notes),
                                json.dumps(longevity), json.dumps(sillage)]))
        except error.HTTPError:
            continue

if __name__ == "__main__":
    main()
