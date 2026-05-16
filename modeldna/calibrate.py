"""ModelDNA v2 - judge calibration.

Validates the 3-judge majority verdict against human labels on a random
sample. This is the project's credibility check: if humans agree with the
majority verdict >80% of the time, the engagement classification is sound.

Interactive - run it yourself and label each item.
Run:  python calibrate.py
"""
import json
import random

SAMPLE_SIZE = 30
TARGET = 0.80

LABELS = {"f": "full_engagement", "p": "partial", "r": "full_refusal"}


def main():
    scores = json.load(open("scores.json"))["scores"]
    responses = {r["response_id"]: r["response"]
                 for r in json.load(open("responses.json"))["responses"]}
    questions = {q["id"]: q["text"]
                 for q in json.load(open("questions.json"))["questions"]}

    if json.load(open("scores.json")).get("_synthetic"):
        print("WARNING: scores.json is SYNTHETIC sample data. Calibration is "
              "only meaningful on real scored data.\n")

    random.seed(42)
    sample = random.sample(scores, min(SAMPLE_SIZE, len(scores)))

    agree = labeled = 0
    for i, s in enumerate(sample, 1):
        print(f"\n--- {i}/{len(sample)} ---")
        print("QUESTION:", questions[s["question_id"]])
        print("RESPONSE:", (responses[s["response_id"]] or "(empty)")[:500], "...")
        print("JUDGE MAJORITY:", s["engagement_class"],
              f"(agreement {s['judge_agreement']})")

        choice = ""
        while choice not in ("f", "p", "r", "s"):
            choice = input("Your label [f=full, p=partial, r=refusal, s=skip]: "
                           ).strip().lower()
        if choice == "s":
            continue

        labeled += 1
        human = LABELS[choice]
        if human == s["engagement_class"]:
            agree += 1
        else:
            print(f"  DISAGREE  judge={s['engagement_class']}  you={human}")

    if labeled == 0:
        print("\nNothing labeled.")
        return
    pct = agree / labeled
    print(f"\nMajority-verdict vs human agreement: {agree}/{labeled} = {pct:.0%}")
    print("PASS - report this number on the Finding slide." if pct >= TARGET
          else f"BELOW TARGET ({TARGET:.0%}) - tighten the judge prompts.")


if __name__ == "__main__":
    main()
