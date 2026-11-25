"""The copilot: question -> retrieve top chunks -> LLM writes a cited answer (or refuses).

Usage:
    uv run python src/copilot.py "How fast must a data breach be reported?"
    uv run python src/copilot.py "Darf mein Arbeitgeber KI zur Emotionserkennung nutzen?"
"""
import json
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

from retrievers import (MAX_PINNED, BM25Retriever, CitationLookup, EmbeddingRetriever,
                        HybridRetriever, Reranker, detect_language, load_corpus)

load_dotenv()                                         # reads OPENAI_API_KEY from .env
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TOP_K = 6                                             # chunks shown to the LLM
OVERALL = 20                                          # candidates from both laws together
PER_LAW = 10                                          # extra candidates per law before reranking

SYSTEM_PROMPT = """You are a legal information assistant for the EU AI Act and the GDPR.
Answer ONLY using the numbered sources provided. Rules:
1. Every factual statement must cite its source number(s) in square brackets, e.g. [1] or [2][4].
2. If the sources answer the question fully OR PARTLY, set "answerable" to true: answer the
   parts the sources support and say clearly which part they do not cover.
   Only if the sources contain nothing relevant, set "answerable" to false and say so briefly.
   Never use outside knowledge, even if you know the answer.
3. Write the answer in the language given under "Answer language" - even if the question
   mentions another country or language (e.g. "German motorways" -> still English).
4. Be concise: 2-6 sentences, plain language. But if the question asks for a list (e.g.
   principles, conditions, obligations), include ALL items the sources give.
5. You give legal information, not legal advice.

Return JSON only, exactly in this shape:
{"answerable": true or false, "answer": "...", "sources_used": [list of source numbers]}"""


class Copilot:
    def __init__(self, model=MODEL):
        self.client = OpenAI()
        self.model = model
        reranker = Reranker()
        self.retrievers = {}
        for lang in ["en", "de"]:
            chunks = load_corpus(lang)
            self.retrievers[lang] = HybridRetriever(
                BM25Retriever(chunks, lang), EmbeddingRetriever(chunks, lang), lang,
                citations=CitationLookup(chunks), reranker=reranker, bm25_mode="never")

    def retrieve(self, question):
        """Search in the question's language and make sure BOTH laws get a say.

        Why: for questions like "GDPR vs AI Act fines?" the top results were all from one law,
        so the LLM never saw the other half of the answer. Now each law contributes its best
        candidates, the reranker sorts them together, and the final list contains at least the
        best chunk of each law.
        """
        lang = detect_language(question)
        retriever = self.retrievers[lang]

        # 1. candidates: directly cited articles + best 20 overall (as in Phase 4)
        #    + best 10 per law (so the second law is never missing from the pool)
        cited = retriever.citations.find(question)
        pool = cited + [c for c, _ in retriever.emb.search(question, top_n=OVERALL)]
        pool += [c for law in ["gdpr", "aiact"]
                 for c, _ in retriever.emb.search(question, top_n=PER_LAW, law=law)]
        candidates, seen_ids = [], set()
        for chunk in pool:
            if chunk["chunk_id"] not in seen_ids:
                seen_ids.add(chunk["chunk_id"])
                candidates.append((chunk, 0.0))

        # 2. one reranking pass over all candidates; a precise citation ("Art. 49 Abs. 1")
        #    stays pinned first, like in Phase 4
        ranked = [c for c, _ in retriever.reranker.rerank(question, candidates)]
        if 0 < len(cited) <= MAX_PINNED:
            cited_ids = {c["chunk_id"] for c in cited}
            ranked = cited + [c for c in ranked if c["chunk_id"] not in cited_ids]

        # 3. unique paragraphs (parts of one paragraph count once), in ranked order
        unique, seen = [], set()
        for chunk in ranked:
            if chunk["align_id"] not in seen:
                seen.add(chunk["align_id"])
                unique.append(chunk)

        # 4. top K, but guarantee the best chunk of each law is included
        top = unique[:TOP_K]
        for law in ["gdpr", "aiact"]:
            if not any(c["law"] == law for c in top):
                best_of_law = next((c for c in unique if c["law"] == law), None)
                if best_of_law:
                    top = top[:-1] + [best_of_law]     # replace the weakest slot
        return lang, top

    def answer(self, question):
        start = time.time()
        lang, chunks = self.retrieve(question)
        sources = "\n\n".join(f"[{i}] {c['citation']}\n{c['text']}" for i, c in enumerate(chunks, 1))

        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Sources:\n\n{sources}\n\nQuestion: {question}\n\n"
                    f"Answer language: {'German' if lang == 'de' else 'English'}")},
            ],
        )
        data = json.loads(response.choices[0].message.content)

        used = [n for n in data.get("sources_used", []) if isinstance(n, int) and 1 <= n <= len(chunks)]
        return {
            "question": question,
            "lang": lang,
            "answerable": bool(data.get("answerable", True)),
            "answer": data.get("answer", ""),
            "citations": [chunks[n - 1]["citation"] for n in used],
            "cited_align_ids": [chunks[n - 1]["align_id"] for n in used],
            "retrieved_align_ids": [c["align_id"] for c in chunks],
            "sources_text": sources,
            "latency_s": round(time.time() - start, 2),
            "tokens": response.usage.total_tokens if response.usage else None,
        }


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How fast must a data breach be reported?"
    result = Copilot().answer(question)
    print(f"\nQ: {result['question']}\n")
    print(result["answer"] if result["answerable"] else f"(not answerable) {result['answer']}")
    print("\nSources:", ", ".join(result["citations"]) or "-")
    print(f"[{result['latency_s']} s, {result['tokens']} tokens]")
