import json
import re

from bs4 import BeautifulSoup


def clean(text):
    """Collapse all whitespace (spaces, newlines, tabs) into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def parse_article(soup, art_id, law, lang):
    """Turn one article into a list of chunk cards (one per paragraph)."""
    art = soup.find("div", id=art_id)

    # --- article info ---
    number = art_id.removeprefix("art_")                       # "art_1" -> "1"
    title = clean(art.find("p", class_="stitle-article-norm").get_text())

    # --- chapter info: walk UP the tree to the chapter container ---
    chapter_div = art.find_parent("div", id=re.compile(r"^cpt_"))
    chapter = chapter_div["id"].removeprefix("cpt_")           # "cpt_I" -> "I"
    chapter_title = clean(chapter_div.find("p", class_="title-division-2").get_text())

    # --- paragraphs: only DIRECT children with class "norm" ---
    chunks = []
    for par in art.find_all("div", class_="norm", recursive=False):
        par_no = clean(par.find("span", class_="no-parag").get_text()).rstrip(".")
        body = par.find("div", class_="inline-element")
        text = clean(body.get_text(" "))

        chunks.append({
            "chunk_id": f"{law}_{lang}_art_{number}_par_{par_no}",
            "align_id": f"{law}_art_{number}_par_{par_no}",
            "law": law,
            "lang": lang,
            "unit_type": "paragraph",
            "chapter": chapter,
            "chapter_title": chapter_title,
            "article": number,
            "article_title": title,
            "paragraph": par_no,
            "citation": f"{law.upper()} Art. {number}({par_no})",
            "text": text,
            "embed_text": f"{law.upper()}, Article {number}, {title}, paragraph {par_no}: {text}",
            "n_chars": len(text),
        })
    return chunks


if __name__ == "__main__":
    with open("data/raw/gdpr_en_20160504.html", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    for chunk in parse_article(soup, "art_1", law="gdpr", lang="en"):
        print(json.dumps(chunk, ensure_ascii=False, indent=2))