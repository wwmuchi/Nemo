"""
Render a political-compass plot showing:
  - The 8 ideologues at their known coordinates (red dots).
  - The 4 LLM models at their trilateration-derived coordinates (blue stars).
  - A translucent scatter cloud of per-question coordinates for each model,
    so the spread/consistency of a model is visible.

Reads from the source scored CSV and re-uses the trilateration logic in
compute_model_coordinates.py so the cloud points are exactly the per-question
coordinates that fed into the spread numbers in model_coordinates.csv.

Writes: model_compass_plot.png next to this script.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

from compute_model_coordinates import (
    CSV_PATH,
    IDEOLOGUES,
    compute_per_model,
    is_all_five,
    load_rows,
    row_scores,
    trilaterate,
)

OUT_PATH = Path(__file__).resolve().parent / "model_compass_plot.png"

MODEL_COLORS = {
    "chatgpt": "#10A37F",
    "claude":  "#C97B5C",
    "gemini":  "#4285F4",
    "grok":    "#1D1D1F",
}

# Per-model label offset (points) so the four near-clustered labels don't overlap.
MODEL_LABEL_OFFSET = {
    "chatgpt": (12, 10),
    "claude":  (12, -18),
    "gemini":  (-66, 10),
    "grok":    (-58, -18),
}

# Per-ideologue label offset (points) -- defaults to (8, 6) but we override
# for the Mamdani/AOC pair which sits on top of itself.
IDEOLOGUE_LABEL_OFFSET = {
    "Zohran Mamdani":            (8, 8),
    "Alexandria Ocasio-Cortez":  (8, -14),
}


def per_question_coords(rows: list[dict]) -> dict[str, np.ndarray]:
    """For each model, return an (n, 2) array of per-question coordinates."""
    out: dict[str, list[tuple[float, float]]] = {m: [] for m in MODEL_COLORS}
    for row in rows:
        s = row_scores(row)
        if s is None or is_all_five(s):
            continue
        model = row["MODEL"]
        if model not in out:
            continue
        out[model].append(trilaterate(s))
    return {m: np.array(pts) for m, pts in out.items()}


def draw_compass_background(ax: plt.Axes) -> None:
    # Light quadrant shading, traditional political-compass palette.
    ax.add_patch(Rectangle((-11, 0),  11, 11, facecolor="#F2C9C9", alpha=0.35, zorder=0))  # auth-left
    ax.add_patch(Rectangle((0, 0),    11, 11, facecolor="#C9D6F2", alpha=0.35, zorder=0))  # auth-right
    ax.add_patch(Rectangle((-11, -11), 11, 11, facecolor="#C9F2D6", alpha=0.35, zorder=0)) # lib-left
    ax.add_patch(Rectangle((0, -11),   11, 11, facecolor="#F2EDC9", alpha=0.35, zorder=0)) # lib-right

    # Axis crosshair.
    ax.axhline(0, color="#333", linewidth=1.0, zorder=1)
    ax.axvline(0, color="#333", linewidth=1.0, zorder=1)

    # Light grid every 2 units.
    ax.set_xticks(range(-10, 11, 2))
    ax.set_yticks(range(-10, 11, 2))
    ax.grid(True, linestyle=":", color="#999", alpha=0.5, zorder=1)

    # Quadrant corner labels.
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


def plot_models(ax: plt.Axes, per_model: list[dict],
                clouds: dict[str, np.ndarray]) -> None:
    for r in per_model:
        m = r["model"]
        color = MODEL_COLORS[m]
        cloud = clouds[m]

        # Per-question cloud (skip if degenerate -- e.g., Gemini's all-identical scores).
        if cloud.size and np.ptp(cloud, axis=0).sum() > 0.01:
            ax.scatter(cloud[:, 0], cloud[:, 1], s=24, c=color, alpha=0.18,
                       edgecolors="none", zorder=2)

        # Point estimate.
        ax.scatter([r["econ_x"]], [r["social_y"]], s=320, c=color, marker="*",
                   edgecolors="white", linewidths=1.5, zorder=6,
                   label=m)
        ox, oy = MODEL_LABEL_OFFSET.get(m, (10, -4))
        ax.annotate(m, (r["econ_x"], r["social_y"]),
                    xytext=(ox, oy), textcoords="offset points",
                    fontsize=11, color=color, fontweight="bold", zorder=7,
                    arrowprops=dict(arrowstyle="-", color=color, lw=0.8,
                                    shrinkA=0, shrinkB=4))


def main() -> None:
    rows = load_rows(CSV_PATH)
    per_model = compute_per_model(rows)
    clouds = per_question_coords(rows)

    fig, ax = plt.subplots(figsize=(11, 11))
    draw_compass_background(ax)
    plot_ideologues(ax)
    plot_models(ax, per_model, clouds)

    ax.set_title(
        "LLM Political-Compass Placement\n"
        "stars = trilaterated point estimate  ·  dots = per-question cloud  "
        "·  red circles = ideologue anchors",
        fontsize=12, pad=14,
    )
    ax.legend(loc="lower left", fontsize=10, framealpha=0.9, title="Models")

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=180, bbox_inches="tight")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
