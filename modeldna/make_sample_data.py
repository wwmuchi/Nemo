"""ModelDNA v2 - synthetic sample data generator.

Produces responses.json and scores.json filled with RANDOM, FAKE data so the
dashboard can be built and demoed before the real inference + scoring run
finishes (plan timeline: dashboard is built Sat afternoon, before real scored
data is ready).

  *** THE NUMBERS THIS PRODUCES ARE NOT REAL MEASUREMENTS. ***

The output files carry a "_synthetic": true flag. The dashboard detects that
flag and shows a red warning banner. Always replace these with real data from
inference.py + score.py before submitting or presenting any finding.

Run:  python make_sample_data.py
"""
import json
import random

random.seed()  # intentionally NOT fixed - discourages treating output as stable

ENG_SCORE = {"full_engagement": 1.0, "partial": 0.5, "full_refusal": 0.0}


def _engagement(p_full, p_partial):
    r = random.random()
    if r < p_full:
        return "full_engagement"
    if r < p_full + p_partial:
        return "partial"
    return "full_refusal"


def main(questions_file="questions.json", n_repeats=3):
    questions = json.load(open(questions_file))["questions"]
    models = ["chatgpt", "claude", "gemini", "grok"]

    # Random per-model, per-lean tendencies so the dashboard shows variety.
    # Randomized every run on purpose: this is scaffolding, not a result.
    tendency = {}
    for m in models:
        base = random.uniform(0.55, 0.9)
        tendency[m] = {
            "left":    min(0.97, base + random.uniform(-0.12, 0.12)),
            "right":   min(0.97, base + random.uniform(-0.12, 0.12)),
            "neutral": random.uniform(0.93, 0.99),
        }

    responses, scores = [], []
    for q in questions:
        for m in models:
            p_full = tendency[m][q["lean"]]
            for rep in range(1, n_repeats + 1):
                rid = f"{q['id']}__{m}__r{rep}"
                eng = _engagement(p_full, p_partial=(1 - p_full) * 0.5)
                responses.append({
                    "response_id": rid, "question_id": q["id"],
                    "category": q["category"], "pair_id": q["pair_id"],
                    "lean": q["lean"], "model": m, "model_id": f"{m}-sample",
                    "repeat": rep,
                    "response": f"[SYNTHETIC SAMPLE RESPONSE - {eng}]",
                    "error": None,
                })
                # Simulate 3 judges agreeing most of the time.
                votes = [eng if random.random() < 0.85
                         else random.choice(list(ENG_SCORE)) for _ in range(3)]
                majority = max(set(votes), key=votes.count)
                scores.append({
                    "response_id": rid, "question_id": q["id"],
                    "category": q["category"], "pair_id": q["pair_id"],
                    "lean": q["lean"], "model": m, "repeat": rep,
                    "engagement_class": majority,
                    "engagement_score": ENG_SCORE[majority],
                    "judge_agreement": round(votes.count(majority) / 3, 3),
                    "judge_strict": votes[0], "judge_lenient": votes[1],
                    "judge_neutral": votes[2],
                    "personal_expression": random.random() < 0.1,
                })

    note = "SYNTHETIC SAMPLE DATA - random numbers, NOT real measurements"
    json.dump({"_synthetic": True, "_note": note, "responses": responses},
              open("responses.json", "w"), indent=2)
    json.dump({"_synthetic": True, "_note": note, "scores": scores},
              open("scores.json", "w"), indent=2)
    print(f"Wrote SYNTHETIC responses.json ({len(responses)}) and "
          f"scores.json ({len(scores)}).")
    print("These are fake. Replace with real inference.py + score.py output "
          "before presenting anything.")


if __name__ == "__main__":
    main()
