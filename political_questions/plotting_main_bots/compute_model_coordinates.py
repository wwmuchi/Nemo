"""
Compute political-compass coordinates for each LLM model (chatgpt, claude,
gemini, grok) by trilaterating its similarity scores against the 8 ideologue
"bots" whose compass coordinates are known.

Method:
  - For each row (question), the CSV gives 8 similarity scores measuring how
    closely the model's answer aligns with each ideologue.
  - We treat (sim_max - score) * scale as a target Euclidean distance from
    the model's location to that ideologue's known coordinate.
  - We solve a weighted nonlinear least-squares problem: find (x, y) that
    minimizes sum_i w_i * (||x - c_i|| - d_i)^2 across the 8 anchors.
  - sim_max and scale are JOINTLY CALIBRATED on the loaded data on every run.
    Weights down-weight anchors that crowd each other on the compass so that
    two near-identical ideologues (e.g. Mamdani and AOC) don't double-count.
  - We do this twice per model:
      (a) "Point" estimate: trilaterate on the model's MEAN score per
          ideologue across all questions -> one coordinate per model.
      (b) "Spread" estimate: trilaterate per question, then report mean
          and std-dev across questions. This gives a confidence cloud.
  - We also produce a per-(model, category) breakdown using approach (a).

Outputs (written next to this script):
  - model_coordinates.csv               one row per model
  - model_coordinates_by_category.csv   one row per (model, category)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares, minimize


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Starting points for the joint sim_max/scale optimizer. Final values are
# fit to the data on every run; these only seed the search.
SIM_MAX_INITIAL = 8.0
SCALE_INITIAL = 2.0

# Gaussian-kernel length scale (in compass units) for anchor down-weighting.
# Smaller -> only very close neighbors reduce an anchor's weight. Larger ->
# even moderately spaced neighbors share influence. 3.0 was picked because
# the tightest pair (Mamdani/AOC at 0.5 units) is well inside the kernel
# while the average inter-anchor distance (~12) is well outside.
ANCHOR_WEIGHT_LENGTH_SCALE = 3.0

# Hard bounds for the calibrator. sim_max is lower-bounded at runtime by
# the maximum observed score so no score implies negative distance.
SIM_MAX_UPPER = 10.0   # rubric ceiling
SCALE_LOWER = 0.01
SCALE_UPPER = 20.0

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


# ---------------------------------------------------------------------------
# Anchor weighting
# ---------------------------------------------------------------------------


def compute_anchor_weights(
    length_scale: float = ANCHOR_WEIGHT_LENGTH_SCALE,
) -> np.ndarray:
    """Each anchor's weight is the inverse of its local Gaussian-kernel
    density. Anchors with close neighbors share influence; isolated anchors
    keep a full unit. Total weight is normalized to len(anchors) so the
    overall residual scale stays comparable to the unweighted version."""
    diffs = ANCHOR_COORDS[:, None, :] - ANCHOR_COORDS[None, :, :]
    sq_dists = (diffs ** 2).sum(axis=2)
    density = np.exp(-sq_dists / (2 * length_scale ** 2)).sum(axis=1)
    raw = 1.0 / density
    return raw * (len(raw) / raw.sum())


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------


def trilaterate(
    scores: np.ndarray,
    sim_max: float,
    scale: float,
    weights: np.ndarray,
) -> tuple[float, float]:
    """Find (x, y) whose weighted distances to the 8 anchors best match the
    distances implied by `scores`. Each residual is multiplied by sqrt(w_i)
    so anchors with low weight contribute proportionally less."""
    distances = np.maximum((sim_max - scores) * scale, 0.0)
    sqrt_w = np.sqrt(weights)

    pull = scores + 1e-6
    x0 = (pull[:, None] * ANCHOR_COORDS).sum(axis=0) / pull.sum()

    def residuals(p: np.ndarray) -> np.ndarray:
        diffs = ANCHOR_COORDS - p
        dists = np.sqrt((diffs ** 2).sum(axis=1))
        return sqrt_w * (dists - distances)

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
    """True if every bot scored exactly 5 (no-signal). Dropped before any
    aggregation or trilateration."""
    return bool(np.all(scores == 5))


def per_model_means(rows: list[dict]) -> dict[str, np.ndarray]:
    by_model: dict[str, list[np.ndarray]] = defaultdict(list)
    for row in rows:
        s = row_scores(row)
        if s is None or is_all_five(s):
            continue
        by_model[row["MODEL"]].append(s)
    return {m: np.vstack(v).mean(axis=0) for m, v in by_model.items()}


# ---------------------------------------------------------------------------
# Joint sim_max + scale calibration
# ---------------------------------------------------------------------------


def calibrate_sim_max_and_scale(
    rows: list[dict],
    weights: np.ndarray,
) -> tuple[float, float, float]:
    """Jointly fit sim_max and scale to minimize weighted residual
    sum-of-squares across all model means. sim_max is bounded below by the
    maximum observed score (so no observed score implies negative distance)
    and above by SIM_MAX_UPPER (rubric ceiling)."""
    means = list(per_model_means(rows).values())
    observed_max = max(float(s.max()) for s in means)
    sim_max_lower = max(observed_max, 1.0)
    sqrt_w = np.sqrt(weights)
    n_obs = len(means) * len(BOT_COLS)

    def total_rss(params: np.ndarray) -> float:
        sim_max, scale = float(params[0]), float(params[1])
        total = 0.0
        for scores in means:
            distances = np.maximum((sim_max - scores) * scale, 0.0)
            pull = scores + 1e-6
            x0 = (pull[:, None] * ANCHOR_COORDS).sum(axis=0) / pull.sum()

            def residuals(p: np.ndarray, d: np.ndarray = distances) -> np.ndarray:
                diffs = ANCHOR_COORDS - p
                return sqrt_w * (np.sqrt((diffs ** 2).sum(axis=1)) - d)

            res = least_squares(
                residuals, x0=x0,
                bounds=([-15.0, -15.0], [15.0, 15.0]), method="trf",
            )
            total += float((res.fun ** 2).sum())
        return total

    result = minimize(
        total_rss,
        x0=np.array([max(SIM_MAX_INITIAL, sim_max_lower), SCALE_INITIAL]),
        method="Powell",
        bounds=[(sim_max_lower, SIM_MAX_UPPER), (SCALE_LOWER, SCALE_UPPER)],
        options={"xtol": 1e-4, "ftol": 1e-4, "maxiter": 500},
    )
    sim_max = float(result.x[0])
    scale = float(result.x[1])
    rmse = (float(result.fun) / n_obs) ** 0.5
    return sim_max, scale, rmse


# ---------------------------------------------------------------------------
# Per-model coordinate (point + spread)
# ---------------------------------------------------------------------------


def compute_per_model(
    rows: list[dict],
    sim_max: float,
    scale: float,
    weights: np.ndarray,
) -> list[dict]:
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
        arr = np.vstack(score_list)

        mean_scores = arr.mean(axis=0)
        point_x, point_y = trilaterate(mean_scores, sim_max, scale, weights)

        per_q = np.array([trilaterate(s, sim_max, scale, weights) for s in arr])
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
        for col, mean in zip(BOT_COLS, mean_scores):
            row_out[f"mean_{col}"] = round(float(mean), 3)
        out.append(row_out)
    return out


# ---------------------------------------------------------------------------
# Per-(model, category) coordinate
# ---------------------------------------------------------------------------


def compute_per_category(
    rows: list[dict],
    sim_max: float,
    scale: float,
    weights: np.ndarray,
) -> list[dict]:
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
        x, y = trilaterate(mean_scores, sim_max, scale, weights)
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
# Diagnostics
#
# Each function isolates ONE source of error so the output is interpretable:
#   [0] Anchor weights              -> how much each ideologue counts
#   [1] Solver-math check           -> is trilateration code correct?
#   [2] Score-representation check  -> does sim_max*scale span the geometry?
#   [3] Layout-ambiguity report     -> how much do close anchors blur?
# ---------------------------------------------------------------------------


def report_anchor_weights(weights: np.ndarray) -> None:
    print(
        f"[0] Anchor weights "
        f"(length scale={ANCHOR_WEIGHT_LENGTH_SCALE}, total weight={weights.sum():.2f}):"
    )
    for col, w in zip(BOT_COLS, weights):
        bar = "#" * int(round(w * 20))
        print(f"  {IDEOLOGUES[col][0]:<26s} weight={w:.3f}  {bar}")


def check_solver_math(weights: np.ndarray) -> bool:
    """Feed the solver raw inter-anchor distances. Each anchor must be
    recovered exactly. Any non-zero error here is a real code bug."""
    print("[1] Solver-math check (must be ~0.0000):")
    all_ok = True
    sqrt_w = np.sqrt(weights)
    for col, (name, coord) in IDEOLOGUES.items():
        cx, cy = coord
        distances = np.linalg.norm(ANCHOR_COORDS - np.array([cx, cy]), axis=1)

        def residuals(p: np.ndarray, d: np.ndarray = distances) -> np.ndarray:
            diffs = ANCHOR_COORDS - p
            return sqrt_w * (np.sqrt((diffs ** 2).sum(axis=1)) - d)

        res = least_squares(
            residuals,
            x0=np.array([0.0, 0.0]),
            bounds=([-15.0, -15.0], [15.0, 15.0]),
            method="trf",
        )
        err = float(np.linalg.norm(res.x - np.array([cx, cy])))
        ok = err < 1e-3
        all_ok &= ok
        flag = "OK  " if ok else "FAIL"
        print(f"  [{flag}] {name:<26s} err={err:.4f}")
    return all_ok


def check_score_representation(
    sim_max: float, scale: float, weights: np.ndarray
) -> None:
    """Feed scores derived by inverting the distance map for each anchor.
    Error here reveals score-representation clipping when sim_max*scale
    falls below the widest anchor-pair distance."""
    max_repr = sim_max * scale
    print(
        f"[2] Score-representation check "
        f"(sim_max={sim_max:.4f}, scale={scale:.4f}, max representable distance={max_repr:.2f}):"
    )
    for col, (name, coord) in IDEOLOGUES.items():
        cx, cy = coord
        scores = np.zeros(len(BOT_COLS))
        for j, other in enumerate(BOT_COLS):
            ox, oy = IDEOLOGUES[other][1]
            dist = float(np.hypot(cx - ox, cy - oy))
            scores[j] = max(0.0, sim_max - dist / scale)
        x, y = trilaterate(scores, sim_max, scale, weights)
        err = float(np.hypot(x - cx, y - cy))
        print(
            f"  {name:<26s} -> ({x:+6.2f}, {y:+6.2f})  "
            f"target ({cx:+5.1f}, {cy:+5.1f})  err={err:.2f}"
        )

    items = list(IDEOLOGUES.items())
    over = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (ax, ay), (bx, by) = items[i][1][1], items[j][1][1]
            d = float(np.hypot(ax - bx, ay - by))
            if d > max_repr:
                over.append((items[i][1][0], items[j][1][0], d))
    if over:
        print(f"  Anchor pairs exceeding the {max_repr:.2f}-unit ceiling:")
        for a, b, d in sorted(over, key=lambda t: -t[2]):
            print(f"    {a} <-> {b}: {d:.1f}")
    else:
        print(f"  All anchor pairs fit within the {max_repr:.2f}-unit ceiling.")


def report_layout_ambiguity(
    sim_max: float, scale: float, weights: np.ndarray
) -> None:
    """Feed the synthetic [0,...,sim_max,...,0] vector. Non-zero error is
    expected and reflects how close other anchors sit to the target."""
    print("[3] Layout-ambiguity report (non-zero error expected):")
    for col, (name, coord) in IDEOLOGUES.items():
        scores = np.zeros(len(BOT_COLS))
        scores[BOT_COLS.index(col)] = sim_max
        x, y = trilaterate(scores, sim_max, scale, weights)
        err = float(np.hypot(x - coord[0], y - coord[1]))
        print(
            f"  {name:<26s} -> ({x:+6.2f}, {y:+6.2f})  "
            f"target ({coord[0]:+5.1f}, {coord[1]:+5.1f})  err={err:.2f}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    rows = load_rows(CSV_PATH)
    print(f"Loaded {len(rows)} rows from {CSV_PATH.name}\n")

    weights = compute_anchor_weights()
    report_anchor_weights(weights)
    print()

    sim_max, scale, rmse = calibrate_sim_max_and_scale(rows, weights)
    print(
        f"Calibrated parameters (jointly fit on real data every run):\n"
        f"  sim_max = {sim_max:.4f}   (observed-max-bounded; rubric ceiling {SIM_MAX_UPPER})\n"
        f"  scale   = {scale:.4f}\n"
        f"  weighted per-anchor RMSE = {rmse:.3f} compass units\n"
    )

    if not check_solver_math(weights):
        print("\n*** Solver math check FAILED -- coordinates below are untrustworthy. ***")
    print()
    check_score_representation(sim_max, scale, weights)
    print()
    report_layout_ambiguity(sim_max, scale, weights)
    print()

    per_model = compute_per_model(rows, sim_max, scale, weights)
    per_cat = compute_per_category(rows, sim_max, scale, weights)

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
