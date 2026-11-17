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
    "en": {"article": "Article", "paragraph": "paragraph", "definition": "definition",
           "annex": "Annex", "point": "point"},
    "de": {"article": "Artikel", "paragraph": "Absatz", "definition": "Begriffsbestimmung",
           "annex": "Anhang", "point": "Nummer"},
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
        "annex": None,
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

    # Case 2: numbered paragraphs -> one card per paragraph.
    # A paragraph can continue AFTER its div.norm: extra subparagraphs appear as
    # sibling elements (e.g. <p class="norm">), so we attach them to the paragraph
    # before them instead of dropping them.
    if art_div.find("div", class_="norm", recursive=False):
        paragraphs = []                      # list of [par_no, [text pieces]]
        for el in art_div.find_all(recursive=False):
            classes = el.get("class", [])
            if "title-article-norm" in classes or "eli-title" in classes:
                continue
            if el.name == "div" and "norm" in classes:
                par_no = number_of(el.find("span", class_="no-parag").get_text())
                body = el.find("div", class_="inline-element")
                paragraphs.append([par_no, [body.get_text(" ")]])
            elif paragraphs:
                paragraphs[-1][1].append(el.get_text(" "))
        return [
            make_chunk(law, lang, art, "paragraph", par_no, clean(" ".join(pieces)))
            for par_no, pieces in paragraphs
        ]

    # Case 3: no numbered paragraphs -> whole article is one card
    body = [el for el in art_div.find_all(recursive=False)
            if "title-article-norm" not in el.get("class", [])
            and "eli-title" not in el.get("class", [])]
    text = clean(" ".join(el.get_text(" ") for el in body))
    return [make_chunk(law, lang, art, "article", None, text)]


def parse_file(path, law, lang):
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    chunks = []
    for art_div in soup.select('div.eli-subdivision[id^="art_"]'):
        chunks.extend(parse_article(art_div, law, lang))
    for anx_div in soup.find_all("div", id=re.compile(r"^anx_[IVXLC]+$")):
        chunks.extend(parse_annex(anx_div, law, lang))
    return chunks


def make_annex_chunk(law, lang, annex_no, annex_title, point_no, text):
    """Build one annex card. point_no = None means the whole annex."""
    name = LAW_NAMES[(law, lang)]
    w = WORDS[lang]
    if point_no is None:
        unit_type, suffix, cite, label = "annex", "full", "", ""
    else:
        unit_type, suffix = "annex_point", f"pt_{point_no}"
        cite, label = f", {w['point']} {point_no}", f", {w['point']} {point_no}"

    return {
        "chunk_id": f"{law}_{lang}_anx_{annex_no}_{suffix}",
        "align_id": f"{law}_anx_{annex_no}_{suffix}",
        "law": law,
        "lang": lang,
        "unit_type": unit_type,
        "chapter": None,
        "chapter_title": None,
        "article": None,
        "article_title": None,
        "annex": annex_no,
        "paragraph": point_no,
        "citation": f"{name} {w['annex']} {annex_no}{cite}",
        "text": text,
        "embed_text": f"{name}, {w['annex']} {annex_no}{', ' + annex_title if annex_title else ''}{label}: {text}",
        "n_chars": len(text),
    }


def parse_annex(anx_div, law, lang):
    """One card per numbered point if the annex is a clean numbered list, else one card."""
    annex_no = anx_div["id"].removeprefix("anx_")
    # Title = every annex heading except the first one ("ANNEX III"). Some annexes have none.
    headings = anx_div.find_all("p", class_=["title-annex-1", "title-annex-2"], recursive=False)
    annex_title = clean(" ".join(h.get_text(" ") for h in headings[1:]))

    skip = {"title-annex-1", "title-annex-2", "separator-annex", "modref"}
    body = [el for el in anx_div.find_all(recursive=False)
            if not skip & set(el.get("class", []))]
    items = [el for el in body if "grid-list" in el.get("class", [])]
    labels = [clean(i.find("div", class_="grid-list-column-1").get_text()) for i in items]

    body_chars = sum(len(clean(el.get_text(" "))) for el in body)
    item_chars = sum(len(clean(i.get_text(" "))) for i in items)
    is_numbered_list = (
        len(items) >= 2
        and all(re.fullmatch(r"\d+\.", lab) for lab in labels)   # "1.", "2.", ...
        and len(set(labels)) == len(labels)                       # no restarts
        and item_chars >= 0.9 * body_chars                         # (almost) all text is in the list
    )

    if is_numbered_list:
        chunks = []
        for item in items:
            point_no = number_of(item.find("div", class_="grid-list-column-1").get_text())
            text = clean(item.find("div", class_="grid-list-column-2").get_text(" "))
            chunks.append(make_annex_chunk(law, lang, annex_no, annex_title, point_no, text))
        return chunks

    text = clean(" ".join(el.get_text(" ") for el in body))
    return [make_annex_chunk(law, lang, annex_no, annex_title, None, text)]


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

    # Look at one annex card: AI Act Annex III, point 4 (employment)
    ai = parse_file("data/raw/aiact_en_20260727.html", "aiact", "en")
    card = next(c for c in ai if c["chunk_id"] == "aiact_en_anx_III_pt_4")
    print(json.dumps(card, ensure_ascii=False, indent=2)[:900])