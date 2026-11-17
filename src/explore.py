from bs4 import BeautifulSoup


def inspect_file(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "lxml")

    title = soup.find("title").get_text()
    articles = soup.select('div.eli-subdivision[id^="art_"]')

    print(f"{title} -> {len(articles)} articles")


files = [
    "data/raw/gdpr_en_20160504.html",
    "data/raw/gdpr_de_20160504.html",
    "data/raw/aiact_en_20260727.html",
    "data/raw/aiact_de_20260727.html",
]

for path in files:
    inspect_file(path)