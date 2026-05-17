"""
Render a grid of small political-compass plots, one per question category.
Each subplot shows the 4 LLM models' coordinates for that category, with the
8 ideologue anchors drawn faintly for reference.

Reads model_coordinates_by_category.csv (produced by
compute_model_coordinates.py). Run that first if you've changed the source
data or the algorithm.

Writes: model_compass_by_category.png next to this script.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from math import ceil
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from compute_model_coordinates import IDEOLOGUES
from plot_compass import MODEL_COLORS

THIS_DIR = Path(__file__).resolve().parent
INPUT_CSV = THIS_DIR / "model_coordinates_by_category.csv"
OUT_PATH = THIS_DIR / "model_compass_by_category.png"


def load_category_rows() -> dict[str, list[dict]]:
    """Group rows from model_coordinates_by_category.csv by category."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    with INPUT_CSV.open() as f:
        for row in csv.DictReader(f):
            by_cat[row["category"]].append(
                {
                    "model": row["model"],
                    "x": float(row["econ_x"]),
                    "y": float(row["social_y"]),
                    "n": int(row["n_questions"]),
                }
            )
    return by_cat


def draw_mini_compass(ax: plt.Axes) -> None:
    ax.add_patch(Rectangle((-11, 0),  11, 11, facecolor="#F2C9C9", alpha=0.30, zorder=0))
    ax.add_patch(Rectangle((0, 0),    11, 11, facecolor="#C9D6F2", alpha=0.30, zorder=0))
    ax.add_patch(Rectangle((-11, -11), 11, 11, facecolor="#C9F2D6", alpha=0.30, zorder=0))
    ax.add_patch(Rectangle((0, -11),   11, 11, facecolor="#F2EDC9", alpha=0.30, zorder=0))

    ax.axhline(0, color="#444", linewidth=0.6, zorder=1)
    ax.axvline(0, color="#444", linewidth=0.6, zorder=1)
    ax.set_xticks([-10, -5, 0, 5, 10])
    ax.set_yticks([-10, -5, 0, 5, 10])
    ax.tick_params(axis="both", labelsize=7)
    ax.grid(True, linestyle=":", color="#aaa", alpha=0.35, zorder=1)
    ax.set_xlim(-11, 11)
    ax.set_ylim(-11, 11)
    ax.set_aspect("equal")


def draw_faded_ideologues(ax: plt.Axes) -> None:
    for _col, (_name, (x, y)) in IDEOLOGUES.items():
        ax.scatter([x], [y], s=22, c="#B00020", marker="o",
                   alpha=0.35, edgecolors="none", zorder=2)


def draw_models(ax: plt.Axes, rows: list[dict]) -> None:
    """Draw the 4 model stars. When two models coincide (e.g. both at (0,0)),
    nudge their positions in a small ring so all 4 remain visible."""
    rows = sorted(rows, key=lambda r: r["model"])

    # Group rows by rounded coordinate to detect overlaps.
    pos_groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in rows:
        key = (round(r["x"], 1), round(r["y"], 1))
        pos_groups[key].append(r)

    nudge_radius = 0.55
    from math import cos, sin, pi
    for group in pos_groups.values():
        k = len(group)
        for i, r in enumerate(group):
            if k > 1:
                angle = 2 * pi * i / k
                dx = nudge_radius * cos(angle)
                dy = nudge_radius * sin(angle)
            else:
                dx = dy = 0.0
            color = MODEL_COLORS.get(r["model"], "#000")
            ax.scatter([r["x"] + dx], [r["y"] + dy], s=180, c=color,
                       marker="*", edgecolors="white", linewidths=1.2,
                       zorder=4)


def main() -> None:
    by_cat = load_category_rows()
    # Order categories by total question count (most-data first).
    categories = sorted(
        by_cat.keys(),
        key=lambda c: -sum(r["n"] for r in by_cat[c]),
    )

    n = len(categories)
    cols = 5
    rows_g = ceil(n / cols)
    fig, axes = plt.subplots(rows_g, cols, figsize=(cols * 3.2, rows_g * 3.4))
    axes_flat = axes.flatten()

    for i, cat in enumerate(categories):
        ax = axes_flat[i]
        draw_mini_compass(ax)
        draw_faded_ideologues(ax)
        draw_models(ax, by_cat[cat])
        # n is per-model in the category; they're equal across models so take one.
        n_per_model = by_cat[cat][0]["n"] if by_cat[cat] else 0
        ax.set_title(f"{cat}\n(n={n_per_model} per model)", fontsize=9, pad=4)

    # Hide any unused subplots.
    for j in range(n, len(axes_flat)):
        axes_flat[j].axis("off")

    # One shared legend in a corner.
    legend_handles = [
        plt.Line2D([0], [0], marker="*", color="w",
                   markerfacecolor=c, markeredgecolor="white",
                   markersize=13, label=m)
        for m, c in MODEL_COLORS.items()
    ]
    legend_handles.append(
        plt.Line2D([0], [0], marker="o", color="w",
                   markerfacecolor="#B00020", alpha=0.5,
                   markersize=8, label="ideologue anchors")
    )
    fig.legend(handles=legend_handles, loc="lower right",
               bbox_to_anchor=(0.99, 0.01), ncol=5, fontsize=10,
               frameon=True, framealpha=0.9)

    fig.suptitle("LLM Compass Placement by Question Category",
                 fontsize=14, y=0.995)
    plt.tight_layout(rect=[0, 0.02, 1, 0.985])
    plt.savefig(OUT_PATH, dpi=170, bbox_inches="tight")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
