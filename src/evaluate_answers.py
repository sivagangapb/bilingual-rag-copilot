"""Phase 5 evaluation: answer every eval question with the copilot, then grade the answers.

Usage:
    uv run python src/evaluate_answers.py               # dev split
    uv run python src/evaluate_answers.py --split test
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from copilot import Copilot

JUDGE_PROMPT = """You grade answers of a legal Q&A assistant about the EU AI Act and GDPR.
You get: the question, a reference answer, the sources the assistant saw, and its answer.

Grade two things:
- "correct": does the answer agree with the reference answer on the key facts?
   "yes" = key facts right, "partial" = some right / something important missing, "no" = wrong.
- "faithful": is EVERY claim in the answer supported by the sources shown?
   true or false. Ignore whether it matches the reference here - only check against the sources.

Return JSON only: {"correct": "yes" | "partial" | "no", "faithful": true | false, "reason": "one sentence"}"""


def judge(copilot, q, result, sources_text):
    """LLM-as-judge: grade one answer for correctness and faithfulness."""
    response = copilot.client.chat.completions.create(
        model=copilot.model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": (
                f"Question: {q['question']}\n\nReference answer: {q['answer']}\n\n"
                f"Sources:\n{sources_text}\n\nAssistant answer: {result['answer']}")},
        ],
    )
    return json.loads(response.choices[0].message.content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    args = parser.parse_args()

    with open("eval/questions.jsonl", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f]
    questions = [q for q in questions if args.split == "all" or q["split"] == args.split]

    copilot = Copilot()
    rows = []
    for i, q in enumerate(questions, 1):
        result = copilot.answer(q["question"])
        row = {"qid": q["qid"], "type": q["type"], "lang": q["lang"], "gold": q["gold"], **result}

        if q["gold"]:                                     # answerable question
            row["judge"] = judge(copilot, q, result, result["sources_text"]) if result["answerable"] else None
            row["citation_hit"] = bool(set(result["cited_align_ids"]) & set(q["gold"]))
        rows.append(row)
        print(f"[{i}/{len(questions)}] {q['qid']} {q['type']:12s} "
              f"{'answered' if result['answerable'] else 'REFUSED '} {result['latency_s']:5.1f}s")

    # ---------------------------------------------------------------- report
    answerable = [r for r in rows if r["gold"]]
    unanswerable = [r for r in rows if not r["gold"]]
    answered = [r for r in answerable if r["answerable"]]

    def share(items, cond):
        return sum(1 for r in items if cond(r)) / len(items) if items else 0.0

    print(f"\n=== Answer quality ({args.split} split) ===")
    print(f"Answerable questions:           {len(answerable)}")
    print(f"  wrongly refused:              {share(answerable, lambda r: not r['answerable']):.0%}")
    print(f"  correct (judge 'yes'):        {share(answered, lambda r: r['judge']['correct'] == 'yes'):.0%}"
          f"  (+ partial {share(answered, lambda r: r['judge']['correct'] == 'partial'):.0%})")
    print(f"  faithful to sources:          {share(answered, lambda r: r['judge']['faithful']):.0%}")
    print(f"  cites a gold paragraph:       {share(answered, lambda r: r['citation_hit']):.0%}")
    print(f"Unanswerable questions:         {len(unanswerable)}")
    print(f"  correctly refused:            {share(unanswerable, lambda r: not r['answerable']):.0%}")
    latencies = sorted(r["latency_s"] for r in rows)
    print(f"Latency: median {latencies[len(latencies) // 2]:.1f}s, max {latencies[-1]:.1f}s | "
          f"tokens total: {sum(r['tokens'] or 0 for r in rows)}")

    by_type = defaultdict(list)
    for r in answered:
        by_type[r["type"]].append(r)
    print("\nCorrect ('yes') by question type:")
    for t, items in sorted(by_type.items()):
        print(f"  {t:12s} {share(items, lambda r: r['judge']['correct'] == 'yes'):.0%}  (n={len(items)})")

    out = Path("eval/results") / f"answers_{args.split}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nAll answers + grades saved -> {out}  (read some yourself!)")


if __name__ == "__main__":
    main()
