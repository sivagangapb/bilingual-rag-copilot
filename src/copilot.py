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

from retrievers import (BM25Retriever, CitationLookup, EmbeddingRetriever, HybridRetriever,
                        Reranker, detect_language, load_corpus)

load_dotenv()                                         # reads OPENAI_API_KEY from .env
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TOP_K = 5                                             # chunks shown to the LLM

SYSTEM_PROMPT = """You are a legal information assistant for the EU AI Act and the GDPR.
Answer ONLY using the numbered sources provided. Rules:
1. Every factual statement must cite its source number(s) in square brackets, e.g. [1] or [2][4].
2. If the sources do not contain the answer, set "answerable" to false and say so briefly.
   Do NOT use outside knowledge, even if you know the answer.
3. Write the answer in the language given under "Answer language" - even if the question
   mentions another country or language (e.g. "German motorways" -> still English).
4. Be concise: 2-5 sentences. Plain language, no legal jargon where avoidable.
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
        """Search the documents in the question's language (same-language scored best: 0.89 vs 0.81)."""
        lang = detect_language(question)
        results = self.retrievers[lang].search(question)
        top, seen = [], set()
        for chunk, _ in results:                      # skip extra parts of the same paragraph
            if chunk["align_id"] not in seen:
                seen.add(chunk["align_id"])
                top.append(chunk)
            if len(top) == TOP_K:
                break
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
