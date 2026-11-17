"""Run automatic checks on the parsed chunks. Exit code 1 if any check fails."""
import json
import re
import sys
from collections import Counter

from bs4 import BeautifulSoup

from parse import FILES, clean, parse_file

# What we know must be true about the source documents
EXPECTED_ARTICLES = {"gdpr": 99, "aiact": 119}
EXPECTED_ANNEXES = {"gdpr": 0, "aiact": 14}
MIN_CHARS = 20
MIN_COVERAGE = 0.98   # chunks must contain at least 98% of the source text

SKIP_CLASSES = {"title-article-norm", "eli-title", "title-annex-1", "title-annex-2",
                "separator-annex", "modref"}


def source_chars(path):
    """Characters of article + annex body text in the raw HTML (headings excluded)."""
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    units = soup.select('div.eli-subdivision[id^="art_"]')
    units += soup.find_all("div", id=re.compile(r"^anx_[IVXLC]+$"))
    total = 0
    for unit in units:
        for el in unit.find_all(recursive=False):
            if not SKIP_CLASSES & set(el.get("class", [])):
                total += len(clean(el.get_text(" ")))
    return total

failures = []


def check(condition, message):
    """Print PASS/FAIL for one check and remember failures."""
    print(("  PASS  " if condition else "  FAIL  ") + message)
    if not condition:
        failures.append(message)


results = {}
for path, law, lang in FILES:
    chunks = parse_file(path, law, lang)
    results[(law, lang)] = chunks
    print(f"\n{law} {lang}: {len(chunks)} chunks")

    articles = {c["article"] for c in chunks if c["article"] is not None}
    check(len(articles) == EXPECTED_ARTICLES[law],
          f"every article produced chunks ({len(articles)}/{EXPECTED_ARTICLES[law]})")

    annexes = {c["annex"] for c in chunks if c["annex"] is not None}
    check(len(annexes) == EXPECTED_ANNEXES[law],
          f"every annex produced chunks ({len(annexes)}/{EXPECTED_ANNEXES[law]})")

    dups = [cid for cid, n in Counter(c["chunk_id"] for c in chunks).items() if n > 1]
    check(not dups, f"chunk_ids are unique {dups[:3] if dups else ''}")

    marked = [c["chunk_id"] for c in chunks if re.search(r"[►▼◄]", c["text"])]
    check(not marked, f"no consolidation markers left {marked[:3] if marked else ''}")

    tiny = [c["chunk_id"] for c in chunks if c["n_chars"] < MIN_CHARS]
    check(not tiny, f"no near-empty chunks (< {MIN_CHARS} chars) {tiny[:3] if tiny else ''}")

    schemas = {tuple(sorted(c)) for c in chunks}
    check(len(schemas) == 1, "all chunks have the same fields")

    wrong_lang = [c["chunk_id"] for c in chunks if c["lang"] != lang or c["law"] != law]
    check(not wrong_lang, "law/lang fields match the file")

    coverage = sum(c["n_chars"] for c in chunks) / source_chars(path)
    check(coverage >= MIN_COVERAGE,
          f"no text lost: chunks contain {coverage:.1%} of the source text (min {MIN_COVERAGE:.0%})")

print("\nEN <-> DE alignment")
for law in EXPECTED_ARTICLES:
    en = {c["align_id"] for c in results[(law, "en")]}
    de = {c["align_id"] for c in results[(law, "de")]}
    only_en, only_de = sorted(en - de), sorted(de - en)
    check(not only_en and not only_de,
          f"{law}: every EN chunk has a DE twin (only EN: {only_en[:3]}, only DE: {only_de[:3]})")

print("\nEval set")
eval_path = "eval/questions.jsonl"
try:
    with open(eval_path, encoding="utf-8") as f:
        questions = [json.loads(line) for line in f]
except FileNotFoundError:
    questions = []
    print(f"  (no {eval_path} yet, skipped)")
if questions:
    known = {c["align_id"] for chunks in results.values() for c in chunks}
    bad_gold = [(q["qid"], g) for q in questions for g in q["gold"] if g not in known]
    check(not bad_gold, f"every gold id exists in the chunks {bad_gold[:3] if bad_gold else ''}")
    qids = [q["qid"] for q in questions]
    check(len(qids) == len(set(qids)), "question ids are unique")
    no_gold = [q["qid"] for q in questions if not q["gold"] and q["type"] != "unanswerable"]
    check(not no_gold, f"only 'unanswerable' questions have empty gold {no_gold[:3] if no_gold else ''}")

print()
if failures:
    print(f"❌ {len(failures)} check(s) failed")
    sys.exit(1)
print("✅ all checks passed")