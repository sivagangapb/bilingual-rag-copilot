# bilingual-rag-copilot


A question-answering system over the **EU AI Act** and **GDPR** in **German and English**,
with exact article-level citations (e.g. *Art. 5(1)(f) AI Act*) and measured retrieval quality.

Ask in English or German; the answer is grounded in the official legal text and cites its sources.
If the answer isn't in the documents, the system says so instead of guessing.

> 🚧 **Status:** Phase 0 complete: source documents collected and analysed. Retrieval pipeline in progress.

## Why this project
Companies need assistants that answer questions over long, complex documents in more than one
language, with sources they can check. The EU AI Act and GDPR are used as a public test case:
official German and English versions share an identical structure, which allows exact
cross-lingual evaluation. The pipeline itself is document-agnostic.

## Planned features
- [x] Source documents: consolidated EUR-Lex versions (EN + DE), with versioning and provenance
- [ ] Structure-aware parsing and chunking (chapters, articles, paragraphs, points)
- [ ] Hand-checked evaluation set (~100 questions: lookup, multi-hop, cross-lingual, unanswerable)
- [ ] Retrieval comparison: BM25 vs. multilingual embeddings vs. hybrid + reranker
- [ ] Answer generation with citations and refusal on unanswerable questions
- [ ] GraphRAG comparison on multi-hop questions
- [ ] FastAPI + Docker deployment, CI evaluation gate, latency and cost tracking

## Data
| Law | Version | Languages |
|---|---|---|
| GDPR (Reg. 2016/679) | Consolidated, 04.05.2016 (incl. corrigenda) | EN, DE |
| EU AI Act (Reg. 2024/1689) | Consolidated, 27.07.2026 (incl. amendment 2026/1744 and corrigenda) | EN, DE |

Source: [EUR-Lex](https://eur-lex.europa.eu). Full provenance in [`data/raw/MANIFEST.md`](data/raw/MANIFEST.md).

⚠️ Consolidated texts are for documentation purposes only and are not legally binding.
This project is not legal advice.

## Project structure