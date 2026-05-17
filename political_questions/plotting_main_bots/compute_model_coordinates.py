"""
Compute political-compass coordinates for each LLM model (chatgpt, claude,
gemini, grok) by trilaterating its similarity scores against the 8 ideologue
"bots" whose compass coordinates are known.

Method (chosen by the user):
  - For each row (question), the CSV gives 8 similarity scores (0-10 in theory;
    1-8 in practice for this dataset) measuring how closely the model's answer
    aligns with each ideologue.
  - We treat (SIM_MAX - score) * SCALE as a target Euclidean distance from the
    model's location to that ideologue's known coordinate on the compass.
  - We solve a weighted nonlinear least-squares problem: find (x, y) that
    minimizes sum_i (||x - c_i|| - d_i)^2 across the 8 anchors.
  - We do this twice per model:
      (a) "Point" estimate: trilaterate on the model's MEAN score per
          ideologue across all questions -> one coordinate per model.
      (b) "Spread" estimate: trilaterate per question, then report the mean
          and std-dev across questions. This gives a confidence cloud.
  - We also produce a per-(model, category) breakdown using approach (a).

Scale choice:
  SIM_MAX = 10 (theoretical max similarity in the scoring rubric)
  SCALE   = 2.0 (so score 10 -> distance 0; score 0 -> distance 20, which is
                 one full axis span of the compass; score 5 -> distance 10)
  This is configurable below.

Outputs (written next to this script):
  - model_coordinates.csv             one row per model
  - model_coordinates_by_category.csv  one row per (model, category)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SIM_MAX = 8.0  # observed max score in this dataset (the rubric tops at 10
               # in theory, but no model scored above 8)
SCALE = 2.0   # 1 similarity-point == this many compass-units of distance

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
# Maps CSV column name -> (display_name, (econ_x, social_y)).
# Convention: econ axis -10 (left) to +10 (right); social axis -10 (libertarian)
# to +10 (authoritarian).
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


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------


def scores_to_distances(scores: np.ndarray) -> np.ndarray:
    """Map similarity scores -> target distances."""
    return (SIM_MAX - scores) * SCALE


def trilaterate(scores: np.ndarray) -> tuple[float, float]:
    """Find the (x, y) whose distances to the 8 anchors best match the
    distances implied by `scores`. Uniform-weight nonlinear least-squares -
    every anchor's residual r_i = ||x - c_i|| - d_i counts equally, so
    "model is like ideologue X" and "model is unlike ideologue Y" carry
    the same geometric weight per anchor.
    """
    distances = scores_to_distances(scores)

    # Initial guess: score-weighted centroid of the anchors (heuristic only,
    # doesn't change the optimum).
    pull = scores + 1e-6
    x0 = (pull[:, None] * ANCHOR_COORDS).sum(axis=0) / pull.sum()

    def residuals(p: np.ndarray) -> np.ndarray:
        diffs = ANCHOR_COORDS - p
        dists = np.sqrt((diffs ** 2).sum(axis=1))
        return dists - distances

    result = least_squares(
        residuals,
        x0=x0,
        bounds=([-15.0, -15.0], [15.0, 15.0]),
        method="trf",
    )
    return float(result.x[0]), float(result.x[1])


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_rows(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def row_scores(row: dict) -> np.ndarray | None:
    """Extract the 8 bot scores from a row as a numpy array, or None if any
    are missing / non-numeric."""
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


def is_all_five(scores: np.ndarray) -> bool:
    """True if every bot scored exactly 5 (a totally neutral, no-signal row).
    Such rows are dropped entirely before aggregation/trilateration."""
    return bool(np.all(scores == 5))


# ---------------------------------------------------------------------------
# Per-model coordinate (point + spread)
# ---------------------------------------------------------------------------


def compute_per_model(rows: list[dict]) -> list[dict]:
    by_model: dict[str, list[np.ndarray]] = defaultdict(list)
    for row in rows:
        scores = row_scores(row)
        if scores is None or is_all_five(scores):
            continue
        by_model[row["MODEL"]].append(scores)

    out: list[dict] = []
    for model, score_list in sorted(by_model.items()):
        if not score_list:
            continue
        arr = np.vstack(score_list)  # shape: (n_questions, 8)

        # (a) Point estimate: trilaterate on mean scores.
        mean_scores = arr.mean(axis=0)
        point_x, point_y = trilaterate(mean_scores)

        # (b) Spread: trilaterate per question, then summarize.
        per_q = np.array([trilaterate(s) for s in arr])
        cloud_mean_x, cloud_mean_y = per_q.mean(axis=0)
        cloud_std_x, cloud_std_y = per_q.std(axis=0, ddof=1)

        row_out = {
            "model": model,
            "econ_x": round(point_x, 4),
            "social_y": round(point_y, 4),
            "cloud_mean_econ_x": round(cloud_mean_x, 4),
            "cloud_mean_social_y": round(cloud_mean_y, 4),
            "cloud_std_econ_x": round(cloud_std_x, 4),
            "cloud_std_social_y": round(cloud_std_y, 4),
            "n_questions": int(arr.shape[0]),
        }
        # Also include the mean similarity scores so the table is interpretable.
        for col, mean in zip(BOT_COLS, mean_scores):
            row_out[f"mean_{col}"] = round(float(mean), 3)
        out.append(row_out)

    return out


# ---------------------------------------------------------------------------
# Per-(model, category) coordinate
# ---------------------------------------------------------------------------


def compute_per_category(rows: list[dict]) -> list[dict]:
    bucket: dict[tuple[str, str], list[np.ndarray]] = defaultdict(list)
    for row in rows:
        scores = row_scores(row)
        if scores is None or is_all_five(scores):
            continue
        key = (row["MODEL"], row["CATEGORY"])
        bucket[key].append(scores)

    out: list[dict] = []
    for (model, category), score_list in sorted(bucket.items()):
        if not score_list:
            continue
        arr = np.vstack(score_list)
        mean_scores = arr.mean(axis=0)
        x, y = trilaterate(mean_scores)
        out.append(
            {
                "model": model,
                "category": category,
                "econ_x": round(x, 4),
                "social_y": round(y, 4),
                "n_questions": int(arr.shape[0]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Sanity check: trilaterate a synthetic "perfect Kim" score vector and confirm
# we land near Kim's actual coordinate. Useful to catch sign / axis mistakes.
# ---------------------------------------------------------------------------


def sanity_check() -> None:
    print("Sanity check: synthetic score vectors")
    for col, (name, coord) in IDEOLOGUES.items():
        # score 10 for this ideologue, score 0 for all others
        scores = np.zeros(len(BOT_COLS))
        scores[BOT_COLS.index(col)] = SIM_MAX
        x, y = trilaterate(scores)
        print(
            f"  perfect-{name:<26s} -> ({x:+6.2f}, {y:+6.2f})  "
            f"target ({coord[0]:+5.1f}, {coord[1]:+5.1f})"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    rows = load_rows(CSV_PATH)
    print(f"Loaded {len(rows)} rows from {CSV_PATH.name}")

    sanity_check()

    per_model = compute_per_model(rows)
    per_cat = compute_per_category(rows)

    write_csv(OUT_DIR / "model_coordinates.csv", per_model)
    write_csv(OUT_DIR / "model_coordinates_by_category.csv", per_cat)

    print("\nPer-model summary:")
    for r in per_model:
        print(
            f"  {r['model']:<8s}  point=({r['econ_x']:+6.2f}, {r['social_y']:+6.2f})  "
            f"cloud_mean=({r['cloud_mean_econ_x']:+6.2f}, {r['cloud_mean_social_y']:+6.2f})  "
            f"cloud_std=({r['cloud_std_econ_x']:.2f}, {r['cloud_std_social_y']:.2f})  "
            f"n={r['n_questions']}"
        )


if __name__ == "__main__":
    main()
