"""Run automatic checks on the parsed chunks. Exit code 1 if any check fails."""
import re
import sys
from collections import Counter

from parse import FILES, parse_file

# What we know must be true about the source documents
EXPECTED_ARTICLES = {"gdpr": 99, "aiact": 119}
EXPECTED_ANNEXES = {"gdpr": 0, "aiact": 14}
MIN_CHARS = 20

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

print("\nEN <-> DE alignment")
for law in EXPECTED_ARTICLES:
    en = {c["align_id"] for c in results[(law, "en")]}
    de = {c["align_id"] for c in results[(law, "de")]}
    only_en, only_de = sorted(en - de), sorted(de - en)
    check(not only_en and not only_de,
          f"{law}: every EN chunk has a DE twin (only EN: {only_en[:3]}, only DE: {only_de[:3]})")

print()
if failures:
    print(f"❌ {len(failures)} check(s) failed")
    sys.exit(1)
print("✅ all checks passed")