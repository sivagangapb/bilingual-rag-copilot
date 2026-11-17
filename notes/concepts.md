# Concepts: Phase 0

## 1. What problem does RAG solve?
A plain LLM answers from memory, like a closed-book exam. RAG makes it an open-book exam:
it looks up the right passages first, then answers from them.

Plain LLM problems:
- Knowledge cutoff: doesn't know anything after training (e.g. the 2026 AI Act amendment)
- Hallucination: confidently invents facts or article numbers
- Private data: never saw company-internal documents

RAG = Retrieve (search documents) → Augment (put passages in the prompt) → Generate (answer with citations)

Benefits: up to date without retraining, checkable sources, cheaper than fine-tuning.
Limit: RAG is only as good as its retrieval. If the right passage isn't found, the LLM can't use it.

## 2. What is an embedding?
GPS coordinates for meaning. Text becomes a vector (list of numbers); similar meanings
land close together, even with no shared words ("car" ≈ "automobile").

Search: embed all chunks once → embed the question → find the closest vectors (cosine similarity).

Rules:
- Question and documents must use the SAME embedding model (same map)
- A multilingual model puts DE and EN in the same space → "Datenschutz" ≈ "data protection"
- Weak on exact tokens: numbers, IDs, rare terms

## 3. Why chunk documents?
Hand someone the right page, not the whole book.
- Context window: can't send hundreds of pages with every question (limit + cost)
- Precision: a whole-document embedding is a blurry average; small chunks match specific questions
- Citations: a chunk labelled "Art. 5(1)" can be cited exactly

Trade-off:
- Too small → loses context ("this obligation"… which one?)
- Too big → blurry match, wasted tokens

Strategies: fixed size + overlap (simple, cuts mid-sentence) vs. structure-based
(per article/paragraph, better for legal text). Compare both in Phase 1.

## 4. BM25 vs. embedding search
- BM25 = smart Ctrl+F: exact word matching; rare words count more (IDF); repeated words
  have diminishing returns; long chunks slightly penalized
- Embeddings = a librarian who understands meaning

| Query | BM25 | Embeddings |
|---|---|---|
| "Art. 83(4)", exact IDs | ✅ | ❌ |
| Rare term / abbreviation | ✅ | ❌ |
| Paraphrase ("face recognition at work") | ❌ | ✅ |
| EN question, DE documents | ❌ no shared words | ✅ (multilingual model) |
| Synonyms ("fine" vs "penalty") | ❌ | ✅ |

They fail on opposite things → hybrid search (combine both) usually wins. Test in Phases 3–4.

## Check questions
1. Why not embed questions with model A and documents with model B?
   → Different models = different coordinate systems; distances between them are meaningless.
2. "What does Art. 9 GDPR say?" Which search finds it?
   → BM25: exact token match on "Art. 9"; embeddings handle numbers poorly.
3. RAG gives a wrong answer though the LLM is excellent. Most likely cause?
   → Retrieval failed: the right chunk wasn't retrieved (or chunking split it badly).
4. Why does BM25 fail completely on cross-lingual questions?
   → It matches exact words; an English question shares no words with German text.