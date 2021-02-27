import sqlite3
from perfumes_rearranged_db_helper import PerfumesRearrangedDBHelper
import json


def main():
    DB = PerfumesRearrangedDBHelper("perfumes_rearranged.sqlite")
    DB.setup()
    conn = sqlite3.connect("perfumes.sqlite")
    c = conn.cursor()
    c.execute("SELECT * FROM perfumes")
    result = c.fetchall()
    for item in result:
        brand = item[0]
        brand = brand.rstrip()
        brand = brand.lstrip()
        perfume = json.loads(item[1])["title"]
        perfume = perfume.rstrip()
        perfume = perfume.lstrip()
        image = json.loads(item[1])["image"]
        launch_year = item[2]
        temp = json.loads(item[3])
        if not temp:
            main_accords = json.dumps(None)
        else:
            main_accords = json.dumps(temp)
        temp = json.loads(item[4])
        if temp is not None and "general" in temp:
            notes = json.dumps(temp["general"])
        else:
            notes = json.dumps(temp)
        temp = json.loads(item[5])
        longevity = json.dumps([temp["poor"], temp["weak"], temp["moderate"], temp["long lasting"],
                                temp["very long lasting"]])
        temp = json.loads(item[6])
        sillage = json.dumps([temp["soft"], temp["moderate"], temp["heavy"], temp["enormous"]])
        print(brand, perfume)
        DB.add_record(tuple([brand, perfume, image, launch_year, main_accords, notes, longevity, sillage]))


if __name__ == "__main__":
    main()
