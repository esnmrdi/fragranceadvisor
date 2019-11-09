from lxml import html
import requests


def main():
    countries = ["United States", "France", "Italy", "United Kingdom", "Germany", "Spain", "United Arab Emirates (UAE)",
                 "Russia", "Switzerland", "Netherlands", "Japan", "England", "Canada", "Brazil", "Poland", "Australia"]
    with open("manifest.txt", "w") as f:
        for country in countries:
            page1 = requests.get("http://www.fragrantica.com/country/" + country + ".html")
            tree1 = html.fromstring(page1.content)
            page1.close()
            brand_urls = tree1.xpath("//div[@class='nduList']/p/a")
            for brand_url in brand_urls:
                page2 = requests.get("http://www.fragrantica.com" + brand_url.get("href"))
                tree2 = html.fromstring(page2.content)
                perfume_urls = tree2.xpath("//div[@class='perfumeslist']/div/div/p/a")
                for perfume_url in perfume_urls:
                    url = "http://www.fragrantica.com" + perfume_url.get("href") + "\n"
                    f.write(url)
                    print(url)


if __name__ == "__main__":
    main()
