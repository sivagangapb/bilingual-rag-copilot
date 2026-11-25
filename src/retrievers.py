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


_MODELS = {}


def load_embedding_model(model_name):
    """Load each model only once, even if several retrievers use it (saves memory and time)."""
    if model_name not in _MODELS:
        from sentence_transformers import SentenceTransformer   # slow import, only when needed
        _MODELS[model_name] = SentenceTransformer(model_name)
    return _MODELS[model_name]


class EmbeddingRetriever:
    """Meaning search: compares the question vector with every chunk vector (cosine similarity)."""

    def __init__(self, chunks, lang, model_name="intfloat/multilingual-e5-base"):
        self.name = "emb:" + model_name.split("/")[-1].replace("multilingual-", "")
        self.chunks = chunks
        self.model = load_embedding_model(model_name)
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


# --------------------------------------------------------------------------- Phase 4

import re   # noqa: E402  (kept next to the Phase 4 code it belongs to)

# Which words in a question point to which law
LAW_PATTERNS = {
    "gdpr": r"\b(gdpr|dsgvo|general data protection regulation|datenschutz-grundverordnung)\b",
    "aiact": r"\b(ai act|ai regulation|ki-verordnung|ki-vo|artificial intelligence act)\b",
}
# "Article 17", "Art. 9(1)", "Artikel 6 Absatz 3", "Art. 49 Abs. 1", "Article 4a"
ARTICLE_RE = re.compile(
    r"\b(?:article|artikel|art\.?)\s*(\d+[a-z]?)"
    r"(?:\s*\((\d+[a-z]?)\)|\s*(?:paragraph|absatz|abs\.?)\s*(\d+[a-z]?))?",
    re.IGNORECASE)
# "Annex III, point 8", "Anhang III Nr. 8", "Annex III"
ANNEX_RE = re.compile(
    r"\b(?:annex|anhang)\s+([IVXLC]+)\b(?:\s*,?\s*(?:point|nummer|nr\.?)\s*(\d+))?",
    re.IGNORECASE)


MAX_PINNED = 5   # at most this many cited chunks are forced to the top


class CitationLookup:
    """If the question names an article/annex ("Art. 17 GDPR"), fetch those chunks directly."""

    def __init__(self, chunks):
        self.chunks = chunks

    def find(self, query):
        laws = [law for law, pat in LAW_PATTERNS.items() if re.search(pat, query, re.IGNORECASE)]
        laws = laws or ["gdpr", "aiact"]          # law not named -> look in both

        hits = []
        for m in ARTICLE_RE.finditer(query):
            article, paragraph = m.group(1).lower(), m.group(2) or m.group(3)
            hits += [c for c in self.chunks if c["law"] in laws and c["article"] == article
                     and (paragraph is None or c["paragraph"] == paragraph)]
        for m in ANNEX_RE.finditer(query):
            annex, point = m.group(1).upper(), m.group(2)
            hits += [c for c in self.chunks if c["law"] in laws and c["annex"] == annex
                     and (point is None or c["paragraph"] == point)]
        return hits


GERMAN_HINTS = re.compile(
    r"[äöüß]|\b(der|die|das|und|ist|ein|eine|nicht|mit|wie|was|wann|darf|muss|ich|wir|für"
    r"|nach|gilt|kann|welche|sind)\b", re.IGNORECASE)


def detect_language(text):
    """Tiny rule-based detector: German if it has umlauts/ß or common German words."""
    return "de" if GERMAN_HINTS.search(text) else "en"


def rrf(rankings, k=60):
    """Reciprocal Rank Fusion: combine several ranked lists into one.

    Each list gives a chunk 1 / (k + rank) points; the points are summed.
    A chunk ranked high in BOTH lists beats one ranked high in only one.
    """
    scores = {}
    for ranking in rankings:
        for rank, (chunk, _) in enumerate(ranking, start=1):
            entry = scores.setdefault(chunk["chunk_id"], [chunk, 0.0])
            entry[1] += 1 / (k + rank)
    return sorted(((c, s) for c, s in scores.values()), key=lambda x: -x[1])


class Reranker:
    """Cross-encoder: reads question + chunk TOGETHER and scores how well they match.

    Much more precise than embeddings, but slow -> only used on the top candidates.
    """

    def __init__(self, model_name="BAAI/bge-reranker-v2-m3"):
        from sentence_transformers import CrossEncoder

        self.name = model_name.split("/")[-1]
        self.model = CrossEncoder(model_name, max_length=512)

    def rerank(self, query, candidates):
        scores = self.model.predict([(query, c["embed_text"]) for c, _ in candidates],
                                    batch_size=16, show_progress_bar=False)
        order = sorted(range(len(candidates)), key=lambda i: -scores[i])
        return [(candidates[i][0], float(scores[i])) for i in order]


class HybridRetriever:
    """BM25 + embeddings fused with RRF, optionally + citation lookup + reranker.

    bm25_mode:
      "always"        -> always fuse BM25 with embeddings
      "same-language" -> only use BM25 when the question is in the corpus language
                         (BM25 finds nothing useful across languages and only adds noise)
      "never"         -> embeddings only
    """

    def __init__(self, bm25, emb, corpus_lang, citations=None, reranker=None,
                 rerank_top=20, bm25_mode="always"):
        self.bm25, self.emb, self.corpus_lang = bm25, emb, corpus_lang
        self.citations, self.reranker, self.rerank_top = citations, reranker, rerank_top
        self.bm25_mode = bm25_mode
        base = {"always": "hybrid", "same-language": "lang-hybrid", "never": "emb"}[bm25_mode]
        self.name = base + ("+cite" if citations else "") + ("+rerank" if reranker else "")

    def use_bm25(self, query):
        if self.bm25_mode == "always":
            return True
        if self.bm25_mode == "same-language":
            return detect_language(query) == self.corpus_lang
        return False

    def search(self, query, top_n=50):
        rankings = [self.emb.search(query, top_n)]
        if self.use_bm25(query):
            rankings.append(self.bm25.search(query, top_n))

        # Citation lookup. A precise citation ("Art. 49 Abs. 1") gives a few chunks -> put them
        # first. A loose mention ("... nach Anhang III") gives many -> only add them as one more
        # vote in the fusion, so they don't push everything else out of the top 5.
        cited, pin_first = [], False
        if self.citations:
            cited = self.citations.find(query)
            if 0 < len(cited) <= MAX_PINNED:
                pin_first = True
            elif cited:
                rankings.append([(c, 1.0) for c in cited])

        results = rrf(rankings)[:top_n]

        if self.reranker:
            head = self.reranker.rerank(query, results[: self.rerank_top])
            results = head + results[self.rerank_top:]

        if pin_first:
            cited_ids = {c["chunk_id"] for c in cited}
            results = [(c, 1.0) for c in cited] + [r for r in results if r[0]["chunk_id"] not in cited_ids]

        return results[:top_n]
