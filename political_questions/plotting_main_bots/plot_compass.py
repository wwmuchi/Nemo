"""
Render a political-compass plot showing:
  - The 8 ideologues at their known coordinates (red dots).
  - A translucent scatter cloud of per-question coordinates for each model,
    placed via score-weighted centroid (no trilateration, no calibration).
  - A 1-sigma confidence ellipse per model fit from the cloud's covariance.

No central marker per model -- the cloud and its ellipse ARE the placement.

For each row in the responses CSV (one bot answering one question), the
bot's 2-D position is the centroid of the 8 ideologue coordinates, weighted
by the bot's similarity score to each ideologue:

    position_q = sum_i (score_q_i * c_i) / sum_i (score_q_i)

Every row with a parseable 8-score vector is kept. No "all 5s" filter, no
mean-aggregation, no row exclusion beyond what the math requires.

Writes: model_compass_plot.png next to this script.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Ellipse, Rectangle


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = (
    REPO_ROOT
    / "political_questions"
    / "main_bots_answering_questions"
    / "responses_export_enriched_scored.csv"
)
OUT_PATH = Path(__file__).resolve().parent / "model_compass_plot.png"

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

MODEL_COLORS = {
    "chatgpt": "#10A37F",
    "claude":  "#C97B5C",
    "gemini":  "#4285F4",
    "grok":    "#1D1D1F",
}

MODEL_LABEL_OFFSET = {
    "chatgpt": (12, 10),
    "claude":  (12, -18),
    "gemini":  (-66, 10),
    "grok":    (-58, -18),
}

IDEOLOGUE_LABEL_OFFSET = {
    "Zohran Mamdani":            (8, 8),
    "Alexandria Ocasio-Cortez":  (8, -14),
}


# ---------------------------------------------------------------------------
# Centroid placement
# ---------------------------------------------------------------------------


def parse_scores(row: dict) -> np.ndarray | None:
    """Return the 8 scores or None if any is missing / non-numeric."""
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


def weighted_centroid(scores: np.ndarray) -> tuple[float, float]:
    """Score-weighted average of the 8 ideologue coordinates. Falls back to
    the plain centroid of the anchors if the score sum is non-positive."""
    total = float(scores.sum())
    if total <= 0:
        return float(ANCHOR_COORDS[:, 0].mean()), float(ANCHOR_COORDS[:, 1].mean())
    x = float((scores * ANCHOR_COORDS[:, 0]).sum() / total)
    y = float((scores * ANCHOR_COORDS[:, 1]).sum() / total)
    return x, y


def clouds_by_model(rows: list[dict]) -> dict[str, np.ndarray]:
    out: dict[str, list[tuple[float, float]]] = defaultdict(list)
    skipped = 0
    for row in rows:
        scores = parse_scores(row)
        if scores is None:
            skipped += 1
            continue
        out[row["MODEL"]].append(weighted_centroid(scores))
    if skipped:
        print(f"Skipped {skipped} rows with missing/non-numeric scores.")
    return {m: np.asarray(pts) for m, pts in out.items() if pts}


# ---------------------------------------------------------------------------
# Confidence ellipse
# ---------------------------------------------------------------------------


def confidence_ellipse_params(points: np.ndarray, n_std: float):
    """(center, width, height, angle_deg) for the n-sigma covariance ellipse
    of an (N, 2) point set. Returns None if the input is degenerate."""
    if len(points) < 2:
        return None
    cov = np.cov(points, rowvar=False)
    if not np.all(np.isfinite(cov)):
        return None
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = eigvals.argsort()[::-1]
    eigvals, eigvecs = eigvals[order], eigvecs[:, order]
    if eigvals[0] <= 0:
        return None
    angle = float(np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0])))
    width = 2.0 * n_std * float(np.sqrt(max(eigvals[0], 0.0)))
    height = 2.0 * n_std * float(np.sqrt(max(eigvals[1], 0.0)))
    center = (float(points[:, 0].mean()), float(points[:, 1].mean()))
    return center, width, height, angle


# ---------------------------------------------------------------------------
# Plot scaffolding (same aesthetic as the previous version)
# ---------------------------------------------------------------------------


def draw_compass_background(ax: plt.Axes) -> None:
    ax.add_patch(Rectangle((-11, 0),  11, 11, facecolor="#F2C9C9", alpha=0.35, zorder=0))
    ax.add_patch(Rectangle((0, 0),    11, 11, facecolor="#C9D6F2", alpha=0.35, zorder=0))
    ax.add_patch(Rectangle((-11, -11), 11, 11, facecolor="#C9F2D6", alpha=0.35, zorder=0))
    ax.add_patch(Rectangle((0, -11),   11, 11, facecolor="#F2EDC9", alpha=0.35, zorder=0))

    ax.axhline(0, color="#333", linewidth=1.0, zorder=1)
    ax.axvline(0, color="#333", linewidth=1.0, zorder=1)

    ax.set_xticks(range(-10, 11, 2))
    ax.set_yticks(range(-10, 11, 2))
    ax.grid(True, linestyle=":", color="#999", alpha=0.5, zorder=1)

    label_kwargs = dict(fontsize=10, color="#555", alpha=0.7,
                        ha="center", va="center", style="italic", zorder=1)
    ax.text(-7, 10.3, "Authoritarian Left",  **label_kwargs)
    ax.text( 7, 10.3, "Authoritarian Right", **label_kwargs)
    ax.text(-7, -10.5, "Libertarian Left",   **label_kwargs)
    ax.text( 7, -10.5, "Libertarian Right",  **label_kwargs)

    ax.set_xlim(-11, 11)
    ax.set_ylim(-11.2, 11.2)
    ax.set_aspect("equal")
    ax.set_xlabel("Economic axis  (Left  ←  →  Right)", fontsize=11)
    ax.set_ylabel("Social axis  (Libertarian  ←  →  Authoritarian)", fontsize=11)


def plot_ideologues(ax: plt.Axes) -> None:
    for _col, (name, (x, y)) in IDEOLOGUES.items():
        ax.scatter([x], [y], s=110, c="#B00020", marker="o",
                   edgecolors="white", linewidths=1.2, zorder=4)
        offset = IDEOLOGUE_LABEL_OFFSET.get(name, (8, 6))
        ax.annotate(name, (x, y), xytext=offset, textcoords="offset points",
                    fontsize=9, color="#B00020", fontweight="bold", zorder=5)


def plot_model_clouds(ax: plt.Axes, clouds: dict[str, np.ndarray]) -> None:
    for model, points in sorted(clouds.items()):
        color = MODEL_COLORS.get(model, "#7A1FA2")

        ax.scatter(points[:, 0], points[:, 1], s=26, c=color, alpha=0.30,
                   edgecolors="none", zorder=2,
                   label=f"{model} (n={len(points)})")

        params = confidence_ellipse_params(points, n_std=1.0)
        if params is None:
            continue
        center, w, h, angle = params
        ax.add_patch(Ellipse(xy=center, width=w, height=h, angle=angle,
                             edgecolor=color, facecolor="none",
                             linewidth=2.0, zorder=5))

        ox, oy = MODEL_LABEL_OFFSET.get(model, (10, -4))
        ax.annotate(model, xy=center, xytext=(ox, oy),
                    textcoords="offset points",
                    fontsize=11, color=color, fontweight="bold", zorder=7)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    with CSV_PATH.open() as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} rows from {CSV_PATH.name}")

    clouds = clouds_by_model(rows)
    for m, pts in sorted(clouds.items()):
        print(f"  {m}: {len(pts)} points")

    fig, ax = plt.subplots(figsize=(11, 11))
    draw_compass_background(ax)
    plot_ideologues(ax)
    plot_model_clouds(ax, clouds)

    ax.set_title(
        "LLM Political-Compass Placement\n"
        "dots = per-question score-weighted centroids  ·  outlines = "
        "1σ confidence ellipses  ·  red circles = ideologue anchors",
        fontsize=12, pad=14,
    )
    ax.legend(loc="lower left", fontsize=10, framealpha=0.9, title="Models")

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=180, bbox_inches="tight")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
