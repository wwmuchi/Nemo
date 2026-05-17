"""
Compute political-compass coordinates for each LLM model (chatgpt, claude,
gemini, grok) as the mean of per-question score-weighted centroids of the
8 ideologue anchors.

For each row (one model answering one question) we compute:

    (x_q, y_q) = sum_i (score_q_i * c_i) / sum_i score_q_i

where c_i is the known compass coordinate of ideologue i. A model's
point coordinate is the mean of those per-question (x_q, y_q) across all
of that model's rows. The same aggregation is applied per (model,
category) for the by-category breakdown.

This matches server.py and plot_compass.py exactly: every coordinate
anywhere in the project is a weighted centroid, with no other math
involved.

Outputs (written next to this script):
  - model_coordinates.csv               one row per model
  - model_coordinates_by_category.csv   one row per (model, category)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = (
    REPO_ROOT
    / "political_questions"
    / "main_bots_answering_questions"
    / "responses_export_enriched_scored.csv"
)
OUT_DIR = Path(__file__).resolve().parent

# Ideologue coordinates from
# scoring_answers/ideologue_personas/ideologue_coordinates.md.
# Convention: econ axis -10 (left) to +10 (right); social axis -10
# (libertarian) to +10 (authoritarian).
IDEOLOGUES: dict[str, tuple[str, tuple[float, float]]] = {
    "FREEDMAN_BOT": ("Milton Friedman", (3.0, -8.0)),
    "KIM_BOT": ("Kim Jong Un", (-9.5, 9.5)),
    "MACRON_BOT": ("Emmanuel Macron", (7.0, 4.5)),
    "MAMDANI_BOT": ("Zohran Mamdani", (-3.5, -3.5)),
    "MILEI_BOT": ("Javier Milei", (10.0, -3.0)),
    "AOC_BOT": ("Alexandria Ocasio-Cortez", (-4.0, -3.5)),
    "PUTIN_BOT": ("Vladimir Putin", (-3.5, 9.0)),
    "TRUMP_BOT": ("Donald Trump", (9.0, 9.0)),
}

BOT_COLS = list(IDEOLOGUES.keys())
ANCHOR_COORDS = np.array([IDEOLOGUES[b][1] for b in BOT_COLS], dtype=float)


def weighted_centroid(scores: np.ndarray) -> tuple[float, float]:
    """Score-weighted average of the 8 ideologue coordinates. Falls back to
    the plain anchor centroid if the score sum is non-positive."""
    total = float(scores.sum())
    if total <= 0:
        return float(ANCHOR_COORDS[:, 0].mean()), float(ANCHOR_COORDS[:, 1].mean())
    x = float((scores * ANCHOR_COORDS[:, 0]).sum() / total)
    y = float((scores * ANCHOR_COORDS[:, 1]).sum() / total)
    return x, y


def parse_scores(row: dict) -> np.ndarray | None:
    out = []
    for col in BOT_COLS:
        v = row.get(col, "")
        if v == "" or v is None:
            return None
        try:
            out.append(float(v))
        except ValueError:
            return None
    return np.array(out, dtype=float)


def load_rows(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def compute_per_model(rows: list[dict]) -> list[dict]:
    by_model: dict[str, list[np.ndarray]] = defaultdict(list)
    for row in rows:
        scores = parse_scores(row)
        if scores is None:
            continue
        by_model[row["MODEL"]].append(scores)

    out: list[dict] = []
    for model, score_list in sorted(by_model.items()):
        arr = np.vstack(score_list)
        points = np.array([weighted_centroid(s) for s in arr])
        x, y = points.mean(axis=0)

        row_out = {
            "model": model,
            "econ_x": round(float(x), 4),
            "social_y": round(float(y), 4),
            "n_questions": int(arr.shape[0]),
        }
        # Per-figure mean affinity scores (used by the site's probe panel,
        # not by the coordinate above).
        for col, mean in zip(BOT_COLS, arr.mean(axis=0)):
            row_out[f"mean_{col}"] = round(float(mean), 3)
        out.append(row_out)
    return out


def compute_per_category(rows: list[dict]) -> list[dict]:
    bucket: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    for row in rows:
        scores = parse_scores(row)
        if scores is None:
            continue
        bucket[(row["MODEL"], row["CATEGORY"])].append(scores)

    out: list[dict] = []
    for (model, category), score_list in sorted(bucket.items()):
        arr = np.vstack(score_list)
        points = np.array([weighted_centroid(s) for s in arr])
        x, y = points.mean(axis=0)
        out.append({
            "model": model,
            "category": category,
            "econ_x": round(float(x), 4),
            "social_y": round(float(y), 4),
            "n_questions": int(arr.shape[0]),
        })
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        print(f"No rows to write for {path.name}")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows):3d} rows -> {path}")


def main() -> None:
    rows = load_rows(CSV_PATH)
    print(f"Loaded {len(rows)} rows from {CSV_PATH.name}")

    per_model = compute_per_model(rows)
    per_cat = compute_per_category(rows)

    write_csv(OUT_DIR / "model_coordinates.csv", per_model)
    write_csv(OUT_DIR / "model_coordinates_by_category.csv", per_cat)

    print("\nPer-model coordinates:")
    for r in per_model:
        print(
            f"  {r['model']:<8s}  ({r['econ_x']:+6.2f}, {r['social_y']:+6.2f})  "
            f"n={r['n_questions']}"
        )


if __name__ == "__main__":
    main()
