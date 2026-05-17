"""Nemo backend — serves the UI and returns pre-recorded probe responses from CSV."""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

import numpy as np
from flask import Flask, request, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.join(HERE, "political_questions")
app = Flask(__name__, static_folder=None)

# Mirrors political_questions/plotting_main_bots/plot_compass.py — keep in sync.
IDEOLOGUES = {
    "FREEDMAN_BOT": ("Milton Friedman", (3.0, -8.0)),
    "KIM_BOT":      ("Kim Jong Un", (-9.5, 9.5)),
    "MACRON_BOT":   ("Emmanuel Macron", (7.0, 4.5)),
    "MAMDANI_BOT":  ("Zohran Mamdani", (-3.5, -3.5)),
    "MILEI_BOT":    ("Javier Milei", (10.0, -3.0)),
    "AOC_BOT":      ("Alexandria Ocasio-Cortez", (-4.0, -3.5)),
    "PUTIN_BOT":    ("Vladimir Putin", (-3.5, 9.0)),
    "TRUMP_BOT":    ("Donald Trump", (9.0, 9.0)),
}
BOT_COLS = list(IDEOLOGUES.keys())
ANCHOR_COORDS = np.array([IDEOLOGUES[b][1] for b in BOT_COLS], dtype=float)

# id → display name. Keep ids lowercase to match the CSV's `model` column.
KNOWN_MODELS = [
    ("claude",  "Claude"),
    ("chatgpt", "ChatGPT"),
    ("gemini",  "Gemini"),
    ("grok",    "Grok"),
]
KNOWN_MODEL_IDS = {mid for mid, _ in KNOWN_MODELS}
KNOWN_MODEL_NAMES = dict(KNOWN_MODELS)


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/compass")
@app.route("/compass/")
def compass():
    return send_from_directory(os.path.join(HERE, "compass"), "index.html")


@app.route("/compass/<path:filename>")
def compass_assets(filename):
    return send_from_directory(os.path.join(HERE, "compass"), filename)


@app.route("/scores")
@app.route("/scores/")
def scores():
    return send_from_directory(os.path.join(HERE, "scores"), "index.html")


@app.route("/scores/<path:filename>")
def scores_assets(filename):
    return send_from_directory(os.path.join(HERE, "scores"), filename)


@app.route("/images/<path:filename>")
def shared_images(filename):
    return send_from_directory(os.path.join(HERE, "images"), filename)


# ============ /api/* — read-only data endpoints sourced from political_questions/ ============

def _load_thinkers() -> list[dict]:
    with open(os.path.join(DATA_ROOT, "site_assets", "thinkers.json")) as f:
        return json.load(f)


@app.route("/api/thinkers")
def api_thinkers():
    return jsonify(_load_thinkers())


@app.route("/api/questions")
def api_questions():
    path = os.path.join(DATA_ROOT, "transforming_questions", "fifty_best_questions_transformed.json")
    with open(path) as f:
        raw = json.load(f)
    out = [
        {
            "id": i + 1,
            "text": q["text"],
            "source": q.get("first_seen_in"),
            "category": q.get("category"),
            "scenario": q.get("scenario"),
        }
        for i, q in enumerate(raw)
    ]
    return jsonify(out)


# ============ Pre-recorded probe responses (Probe page) ============
# Cache the CSV-backed responses + question/thinker maps once per process. Kept
# separate from `_load_clouds()` so compass code paths are untouched.

_PROBE_CACHE: dict | None = None


def _load_probe_cache() -> dict:
    """Build {(model_id, original_question) -> row} plus question_id and bot_col
    lookup tables. Memoized."""
    global _PROBE_CACHE
    if _PROBE_CACHE is not None:
        return _PROBE_CACHE

    questions_path = os.path.join(
        DATA_ROOT, "transforming_questions", "fifty_best_questions_transformed.json",
    )
    with open(questions_path) as f:
        questions = json.load(f)
    qid_to_text: dict[int, str] = {i + 1: q["text"] for i, q in enumerate(questions)}

    thinkers = _load_thinkers()
    bot_col_to_id: dict[str, str] = {t["bot_col"]: t["id"] for t in thinkers}

    csv_path = os.path.join(
        DATA_ROOT, "main_bots_answering_questions",
        "responses_export_enriched_scored.csv",
    )
    rows: dict[tuple[str, str], dict] = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            mid = (row.get("MODEL") or "").strip().lower()
            qtext = row.get("ORIGINAL_QUESTION") or ""
            if not mid or not qtext:
                continue
            rows[(mid, qtext)] = row

    _PROBE_CACHE = {
        "qid_to_text": qid_to_text,
        "bot_col_to_id": bot_col_to_id,
        "rows": rows,
    }
    return _PROBE_CACHE


def _parse_score_cell(v) -> int | float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


@app.route("/api/probe_response")
def api_probe_response():
    try:
        qid = int(request.args.get("question_id", ""))
    except ValueError:
        return jsonify({"error": "question_id must be an integer"}), 400
    model_id = (request.args.get("model") or "").strip().lower()

    if model_id not in KNOWN_MODEL_IDS:
        return jsonify({"error": f"Unknown model: {model_id}"}), 400

    cache = _load_probe_cache()
    qtext = cache["qid_to_text"].get(qid)
    if qtext is None:
        return jsonify({"error": f"Unknown question_id: {qid}"}), 404

    row = cache["rows"].get((model_id, qtext))
    if row is None:
        return jsonify({"error": "No recorded response for this (question, model)"}), 404

    scores = {
        thinker_id: _parse_score_cell(row.get(bot_col))
        for bot_col, thinker_id in cache["bot_col_to_id"].items()
    }

    return jsonify({
        "question_id": qid,
        "question": qtext,
        "model": model_id,
        "model_name": KNOWN_MODEL_NAMES[model_id],
        "prompt_given": row.get("PROMPT_GIVEN_TO_MODEL", ""),
        "response": row.get("MODEL_RESPONSE", ""),
        "scores": scores,
    })


def _parse_scores(row: dict) -> np.ndarray | None:
    """Return the 8 ideologue similarity scores, or None if any cell is
    missing/non-numeric. Mirrors plot_compass.py:parse_scores."""
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


def _weighted_centroid(scores: np.ndarray) -> tuple[float, float]:
    """Score-weighted average of the 8 ideologue coordinates. Falls back to
    the plain centroid if the score sum is non-positive. Mirrors
    plot_compass.py:weighted_centroid."""
    total = float(scores.sum())
    if total <= 0:
        return float(ANCHOR_COORDS[:, 0].mean()), float(ANCHOR_COORDS[:, 1].mean())
    x = float((scores * ANCHOR_COORDS[:, 0]).sum() / total)
    y = float((scores * ANCHOR_COORDS[:, 1]).sum() / total)
    return x, y


def _ellipse_params(points: np.ndarray) -> dict | None:
    """1-sigma covariance ellipse for an (N, 2) point set, expressed as
    SVG-friendly semi-axes. Returns None if degenerate. Mirrors
    plot_compass.py:confidence_ellipse_params with n_std=1."""
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
    angle_deg = float(np.degrees(np.arctan2(eigvecs[1, 0], eigvecs[0, 0])))
    rx = float(np.sqrt(max(eigvals[0], 0.0)))
    ry = float(np.sqrt(max(eigvals[1], 0.0)))
    return {
        "cx": float(points[:, 0].mean()),
        "cy": float(points[:, 1].mean()),
        "rx": rx,
        "ry": ry,
        "angle_deg": angle_deg,
    }


_CLOUDS_CACHE: dict[str, np.ndarray] | None = None


def _load_clouds() -> dict[str, np.ndarray]:
    """Per-model array of (x, y) weighted-centroid points, one row per probe
    answer. Cached for the lifetime of the process — restart the server
    after re-running the scoring pipeline."""
    global _CLOUDS_CACHE
    if _CLOUDS_CACHE is not None:
        return _CLOUDS_CACHE
    path = os.path.join(
        DATA_ROOT, "main_bots_answering_questions",
        "responses_export_enriched_scored.csv",
    )
    buckets: dict[str, list[tuple[float, float]]] = defaultdict(list)
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                scores = _parse_scores(row)
                if scores is None:
                    continue
                mid = (row.get("MODEL") or "").strip().lower()
                if not mid:
                    continue
                buckets[mid].append(_weighted_centroid(scores))
    except FileNotFoundError:
        _CLOUDS_CACHE = {}
        return _CLOUDS_CACHE
    _CLOUDS_CACHE = {m: np.asarray(pts) for m, pts in buckets.items() if pts}
    return _CLOUDS_CACHE


@app.route("/api/models")
def api_models():
    thinkers = _load_thinkers()
    csv_path = os.path.join(DATA_ROOT, "plotting_main_bots", "model_coordinates.csv")
    rows_by_id: dict[str, dict] = {}
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            rows_by_id[row["model"].strip().lower()] = row

    clouds = _load_clouds()

    out = []
    for mid, name in KNOWN_MODELS:
        row = rows_by_id.get(mid)
        cloud = clouds.get(mid)
        has_signal = row is not None
        scores: dict[str, float | None] = {}
        if row is not None:
            for t in thinkers:
                col = f"mean_{t['bot_col']}"
                v = row.get(col, "")
                scores[t["id"]] = float(v) if v != "" else None
        else:
            scores = {t["id"]: None for t in thinkers}

        if cloud is not None and len(cloud) > 0:
            points = [[round(float(x), 4), round(float(y), 4)] for x, y in cloud]
            ellipse = _ellipse_params(cloud)
            mean_x = float(cloud[:, 0].mean())
            mean_y = float(cloud[:, 1].mean())
        else:
            points = []
            ellipse = None
            mean_x = float(row["econ_x"]) if row is not None else 0.0
            mean_y = float(row["social_y"]) if row is not None else 0.0

        out.append({
            "id": mid,
            "name": name,
            "econ_x": mean_x,
            "social_y": mean_y,
            "points": points,
            "ellipse": ellipse,
            "scores": scores,
            "has_signal": has_signal,
        })
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
