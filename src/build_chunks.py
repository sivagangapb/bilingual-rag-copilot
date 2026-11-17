"""Parse all files, split over-long chunks, save to data/processed/*.jsonl."""
import json
import re
from pathlib import Path

from parse import FILES, parse_file

MAX_CHARS = 2000          # ~400-500 tokens; only ~4% of chunks are longer
OUT_DIR = Path("data/processed")

# Split after . ; : when the next piece starts like a new sentence or a list point,
# e.g. "...data; (b) processing..." or "...required. The provider...".
# "Art. 6" or "No. 300/2008" are NOT split (a digit follows).
BOUNDARY_RE = re.compile(r"(?<=[.;:])\s+(?=[(A-ZÄÖÜ„‘'\"]|[a-z]\))")


def split_text(text, max_chars):
    """Greedily pack sentence-like pieces into parts of at most max_chars."""
    pieces = BOUNDARY_RE.split(text)
    parts, current = [], ""
    for piece in pieces:
        # A single piece longer than max_chars: cut it at word boundaries
        while len(piece) > max_chars:
            cut = piece.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                parts.append(current)
                current = ""
            parts.append(piece[:cut])
            piece = piece[cut:].strip()
        if current and len(current) + 1 + len(piece) > max_chars:
            parts.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        parts.append(current)
    return parts


def split_chunk(chunk, max_chars=MAX_CHARS):
    """Return [chunk] if short enough, else several part-chunks.

    align_id stays the SAME for all parts: EN and DE may split into a different
    number of parts (German is longer), so alignment works at the parent level.
    """
    if chunk["n_chars"] <= max_chars:
        return [{**chunk, "part": 1, "n_parts": 1}]

    header = chunk["embed_text"][: -len(chunk["text"])]   # "GDPR, Article 6, ...: "
    texts = split_text(chunk["text"], max_chars)
    return [
        {
            **chunk,
            "chunk_id": f"{chunk['chunk_id']}_p{i}",
            "part": i,
            "n_parts": len(texts),
            "text": text,
            "embed_text": header + text,
            "n_chars": len(text),
        }
        for i, text in enumerate(texts, start=1)
    ]


def stats(chunks):
    n = sorted(c["n_chars"] for c in chunks)
    return f"{len(n):4d} chunks | median {n[len(n) // 2]:4d} | max {n[-1]:4d} chars"


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, law, lang in FILES:
        chunks = parse_file(path, law, lang)
        final = [part for c in chunks for part in split_chunk(c)]

        out_path = OUT_DIR / f"{law}_{lang}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for c in final:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        print(f"{law} {lang}")
        print(f"  before split: {stats(chunks)}")
        print(f"  after split:  {stats(final)}")
        print(f"  saved -> {out_path}")