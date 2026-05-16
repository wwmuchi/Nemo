"""ModelDNA v2 - fallback CSV pre-computation.

Reads scores.json and writes the four headline aggregations to data/*.csv.
Run this Saturday night (plan Section 21). The CSVs are a tertiary safety net:
if both Snowflake and the live dashboard fail on demo day, the numbers and the
slide screenshots still exist on disk.

Run:  python precompute_fallback.py
"""
import os
import analysis

OUT_DIR = "data"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = analysis.load_scores("scores.json")

    tables = {
        "refusal.csv": analysis.refusal_table(df),
        "asymmetry.csv": analysis.asymmetry_table(df),
        "reproducibility.csv": analysis.reproducibility_table(df),
        "audit.csv": analysis.audit_table(df),
    }
    for name, table in tables.items():
        path = os.path.join(OUT_DIR, name)
        table.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(table)} rows)")

    with open(os.path.join(OUT_DIR, "headline.txt"), "w") as f:
        f.write(analysis.headline(df) + "\n")
    print(f"  wrote {OUT_DIR}/headline.txt")

    if analysis.is_synthetic("scores.json"):
        print("\nNOTE: source scores.json is SYNTHETIC - these CSVs are "
              "scaffolding, not real results.")
    print("\nFallback CSVs ready.")


if __name__ == "__main__":
    main()
