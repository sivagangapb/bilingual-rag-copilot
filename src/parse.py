import json
import re
from collections import Counter

from bs4 import BeautifulSoup

# Which article holds the definitions in each law
DEFINITIONS_ARTICLE = {"gdpr": "4", "aiact": "3"}

# Language-specific labels for headers and citations
LAW_NAMES = {
    ("gdpr", "en"): "GDPR", ("gdpr", "de"): "DSGVO",
    ("aiact", "en"): "AI Act", ("aiact", "de"): "KI-Verordnung",
}
WORDS = {
    "en": {"article": "Article", "paragraph": "paragraph", "definition": "definition"},
    "de": {"article": "Artikel", "paragraph": "Absatz", "definition": "Begriffsbestimmung"},
}

# ►C1, ►M1, ▼B, ▼M2 ... and the closing ◄
MARKER_RE = re.compile(r"[►▼]\s*[A-Z]\d*|◄")


def number_of(label):
    """Extract a clean number from labels like '1.', '(1)', '‘5', '„(5', '14a'."""
    match = re.search(r"\d+[a-z]?", label)
    return match.group(0) if match else label.strip()


def clean(text):
    """Remove consolidation markers and collapse whitespace."""
    text = MARKER_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_chunk(law, lang, art, unit_type, sub_no, text):
    """Build one chunk card. sub_no = paragraph or definition number (or None)."""
    name = LAW_NAMES[(law, lang)]
    w = WORDS[lang]
    number = art["number"]

    if unit_type == "paragraph":
        suffix, cite, label = f"par_{sub_no}", f"({sub_no})", f", {w['paragraph']} {sub_no}"
    elif unit_type == "definition":
        suffix, cite, label = f"def_{sub_no}", f"({sub_no})", f", {w['definition']} ({sub_no})"
    else:  # whole article
        suffix, cite, label = "full", "", ""

    return {
        "chunk_id": f"{law}_{lang}_art_{number}_{suffix}",
        "align_id": f"{law}_art_{number}_{suffix}",
        "law": law,
        "lang": lang,
        "unit_type": unit_type,
        "chapter": art["chapter"],
        "chapter_title": art["chapter_title"],
        "article": number,
        "article_title": art["title"],
        "paragraph": sub_no,
        "citation": f"{name} Art. {number}{cite}",
        "text": text,
        "embed_text": f"{name}, {w['article']} {number}, {art['title']}{label}: {text}",
        "n_chars": len(text),
    }


def parse_article(art_div, law, lang):
    """Turn one article <div> into a list of chunk cards."""
    number = art_div["id"].removeprefix("art_")
    chapter_div = art_div.find_parent("div", id=re.compile(r"^cpt_"))
    art = {
        "number": number,
        "title": clean(art_div.find("p", class_="stitle-article-norm").get_text(" ")),
        "chapter": chapter_div["id"].removeprefix("cpt_"),
        "chapter_title": clean(chapter_div.find("p", class_="title-division-2").get_text(" ")),
    }

    # Case 1: definitions article -> one card per definition
    if number == DEFINITIONS_ARTICLE[law]:
        chunks = []
        for item in art_div.find_all("div", class_="grid-list", recursive=False):
            def_no = number_of(item.find("div", class_="grid-list-column-1").get_text())
            text = clean(item.find("div", class_="grid-list-column-2").get_text(" "))
            chunks.append(make_chunk(law, lang, art, "definition", def_no, text))
        return chunks

    # Case 2: numbered paragraphs -> one card per paragraph
    paragraphs = art_div.find_all("div", class_="norm", recursive=False)
    if paragraphs:
        chunks = []
        for par in paragraphs:
            par_no = number_of(par.find("span", class_="no-parag").get_text())
            text = clean(par.find("div", class_="inline-element").get_text(" "))
            chunks.append(make_chunk(law, lang, art, "paragraph", par_no, text))
        return chunks

    # Case 3: no numbered paragraphs -> whole article is one card
    body = [el for el in art_div.find_all(recursive=False)
            if "title-article-norm" not in el.get("class", [])
            and "eli-title" not in el.get("class", [])]
    text = clean(" ".join(el.get_text(" ") for el in body))
    return [make_chunk(law, lang, art, "article", None, text)]


def parse_file(path, law, lang):
    """Parse all articles of one HTML file."""
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    chunks = []
    for art_div in soup.select('div.eli-subdivision[id^="art_"]'):
        chunks.extend(parse_article(art_div, law, lang))
    return chunks


FILES = [
    ("data/raw/gdpr_en_20160504.html", "gdpr", "en"),
    ("data/raw/gdpr_de_20160504.html", "gdpr", "de"),
    ("data/raw/aiact_en_20260727.html", "aiact", "en"),
    ("data/raw/aiact_de_20260727.html", "aiact", "de"),
]

if __name__ == "__main__":
    for path, law, lang in FILES:
        chunks = parse_file(path, law, lang)
        types = Counter(c["unit_type"] for c in chunks)
        print(f"{law} {lang}: {len(chunks)} chunks {dict(types)}")

    # Look at one German definition card
    de = parse_file("data/raw/gdpr_de_20160504.html", "gdpr", "de")
    print(json.dumps(de[3], ensure_ascii=False, indent=2))