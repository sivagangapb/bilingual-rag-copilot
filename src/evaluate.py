"""Run the eval set against the retrievers and print Hit@k / Recall@k / MRR tables.

Usage:
    uv run python src/evaluate.py                    # test split, BM25 + embeddings
    uv run python src/evaluate.py --split dev
    uv run python src/evaluate.py --retrievers bm25  # only BM25 (fast)
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from retrievers import BM25Retriever, EmbeddingRetriever, load_corpus

K_VALUES = (1, 5, 10)


def ranked_align_ids(results):
    """Chunks -> unique align_ids in rank order (parts of one paragraph count once)."""
    seen, ranked = set(), []
    for chunk, _ in results:
        if chunk["align_id"] not in seen:
            seen.add(chunk["align_id"])
            ranked.append(chunk["align_id"])
    return ranked


def score(ranked, gold):
    """Metrics for one question."""
    gold = set(gold)
    m = {}
    for k in K_VALUES:
        top = set(ranked[:k])
        m[f"hit@{k}"] = float(bool(top & gold))            # at least one correct chunk in top k
        m[f"recall@{k}"] = len(top & gold) / len(gold)      # share of correct chunks in top k
    first = next((i for i, a in enumerate(ranked[:10], 1) if a in gold), None)
    m["mrr@10"] = 1 / first if first else 0.0               # 1 = correct chunk ranked first
    return m


def average(rows):
    return {key: sum(r[key] for r in rows) / len(rows) for key in rows[0]}


def print_table(title, groups, columns):
    print(f"\n{title}")
    print(f"  {'':40s}" + "".join(f"{c:>10s}" for c in columns) + f"{'n':>6s}")
    for name, rows in groups.items():
        avg = average(rows)
        print(f"  {name:40s}" + "".join(f"{avg[c]:10.2f}" for c in columns) + f"{len(rows):6d}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test", "all"], default="test")
    parser.add_argument("--retrievers", nargs="+", default=["bm25", "emb"], choices=["bm25", "emb"])
    parser.add_argument("--model", default="intfloat/multilingual-e5-base")
    args = parser.parse_args()

    with open("eval/questions.jsonl", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f]
    questions = [q for q in questions
                 if q["gold"] and (args.split == "all" or q["split"] == args.split)]
    print(f"{len(questions)} answerable questions ({args.split} split)")

    per_question = []
    for corpus_lang in ["en", "de"]:
        chunks = load_corpus(corpus_lang)
        retrievers = []
        if "bm25" in args.retrievers:
            retrievers.append(BM25Retriever(chunks, corpus_lang))
        if "emb" in args.retrievers:
            retrievers.append(EmbeddingRetriever(chunks, corpus_lang, args.model))

        for r in retrievers:
            for q in questions:
                ranked = ranked_align_ids(r.search(q["question"]))
                per_question.append({
                    "qid": q["qid"], "retriever": r.name, "type": q["type"],
                    "q_lang": q["lang"], "corpus_lang": corpus_lang,
                    "setting": "same-language" if q["lang"] == corpus_lang else "cross-lingual",
                    "top10": ranked[:10], "gold": q["gold"], **score(ranked, q["gold"]),
                })

    metric_cols = ["hit@1", "hit@5", "recall@5", "recall@10", "mrr@10"]

    groups = defaultdict(list)
    for row in per_question:
        groups[f"{row['retriever']} | {row['setting']}"].append(
            {k: row[k] for k in metric_cols})
    print_table("Overall", dict(sorted(groups.items())), metric_cols)

    by_type = defaultdict(list)
    for row in per_question:
        by_type[f"{row['retriever']} | {row['setting'][:5]} | {row['type']}"].append(
            {"hit@5": row["hit@5"], "recall@5": row["recall@5"]})
    print_table("By question type", dict(sorted(by_type.items())), ["hit@5", "recall@5"])

    out = Path("eval/results")
    out.mkdir(parents=True, exist_ok=True)
    out_file = out / f"phase3_{args.split}.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for row in per_question:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nPer-question results saved -> {out_file}")


if __name__ == "__main__":
    main()