"""Two retrievers over the chunk corpus: BM25 (keywords) and multilingual embeddings (meaning)."""
import json
from pathlib import Path

import bm25s
import numpy as np
from bm25s.stopwords import STOPWORDS_EN, STOPWORDS_GERMAN

PROCESSED = Path("data/processed")
STOPWORDS = {"en": STOPWORDS_EN, "de": STOPWORDS_GERMAN}
TOKEN_PATTERN = r"(?u)\b\w+\b"   # keep 1-character tokens, so "Article 6" keeps the "6"


def load_corpus(lang):
    """All chunks of one language (GDPR + AI Act together)."""
    chunks = []
    for law in ["gdpr", "aiact"]:
        with open(PROCESSED / f"{law}_{lang}.jsonl", encoding="utf-8") as f:
            chunks += [json.loads(line) for line in f]
    return chunks


class BM25Retriever:
    """Keyword search: scores chunks by overlapping words (rare words count more)."""

    name = "bm25"

    def __init__(self, chunks, lang):
        self.chunks = chunks
        self.stopwords = STOPWORDS[lang]
        tokens = bm25s.tokenize([c["embed_text"] for c in chunks], token_pattern=TOKEN_PATTERN,
                                stopwords=self.stopwords, show_progress=False)
        self.index = bm25s.BM25()
        self.index.index(tokens, show_progress=False)

    def search(self, query, top_n=50):
        tokens = bm25s.tokenize([query], token_pattern=TOKEN_PATTERN,
                                stopwords=self.stopwords, show_progress=False)
        ids, scores = self.index.retrieve(tokens, k=min(top_n, len(self.chunks)), show_progress=False)
        return [(self.chunks[i], float(s)) for i, s in zip(ids[0], scores[0])]


class EmbeddingRetriever:
    """Meaning search: compares the question vector with every chunk vector (cosine similarity)."""

    def __init__(self, chunks, lang, model_name="intfloat/multilingual-e5-base"):
        from sentence_transformers import SentenceTransformer   # slow import, only when needed

        self.name = "emb:" + model_name.split("/")[-1].replace("multilingual-", "")
        self.chunks = chunks
        self.model = SentenceTransformer(model_name)
        # e5 models expect these prefixes: "query: " for questions, "passage: " for documents
        self.is_e5 = "e5" in model_name

        cache = PROCESSED / f"emb_{model_name.split('/')[-1]}_{lang}.npy"
        if cache.exists() and np.load(cache).shape[0] == len(chunks):
            self.vectors = np.load(cache)
        else:
            texts = [("passage: " if self.is_e5 else "") + c["embed_text"] for c in chunks]
            self.vectors = self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                             show_progress_bar=True)
            np.save(cache, self.vectors)

    def search(self, query, top_n=50):
        q = self.model.encode([("query: " if self.is_e5 else "") + query], normalize_embeddings=True)[0]
        scores = self.vectors @ q                  # cosine similarity (vectors are normalised)
        best = np.argsort(-scores)[:top_n]
        return [(self.chunks[i], float(scores[i])) for i in best]