"""Score every (response x ideologue) pair using the Anthropic API.

Replaces 05a_scoring_udf.sql + 05b_run_scoring.sql from the original Cortex
pipeline. Uses local sentence-transformers embeddings (computed by
04_embed_corpus.py) for top-K retrieval on the 5 large-corpus figures, and
includes the FULL corpus for the 3 small-corpus figures.

CLI:
    python 05_score_anthropic.py                   # score every unscored pair
    python 05_score_anthropic.py --limit 100       # pilot on the first 100 row_ids
    python 05_score_anthropic.py --retry-only      # re-score rows where score IS NULL
    python 05_score_anthropic.py --workers 4       # tune concurrency (default 8)
    python 05_score_anthropic.py --model claude-haiku-4-5

Idempotent: skips (row_id, figure_slug) pairs already present in SCORE_AUDIT
with a non-null score, so a crash mid-run just means re-running picks up
where we stopped.
"""
import argparse
import json
import os
import pathlib
import pickle
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import numpy as np
import snowflake.connector
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

CACHE_PATH = pathlib.Path(__file__).resolve().parent / ".embeddings_cache.pkl"
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_WORKERS = 8
TOP_K_NORMAL = 6
TOP_K_RETRY = 12
MAX_OUTPUT_TOKENS = 400

# -----------------------------------------------------------------------------
# Prompt construction
# -----------------------------------------------------------------------------

SYSTEM_RUBRIC = """You are an objective rater. Your job is to score how strongly the named political figure would AGREE with the response below, on a 1-10 scale, grounded ONLY in the verbatim passages provided.

ANCHORED RUBRIC (use these specific reference points):
  1  - The figure would publicly denounce this response. It contradicts their stated views on core, non-negotiable issues.
  3  - The figure would push back. Major substantive disagreements, though some peripheral points may overlap.
  5  - Mixed or neutral. Some agreement, some disagreement, OR the response is too off-topic for the figure to take a clear stance, OR the retrieved passages do not speak to the response's topic.
  7  - Broad agreement. The figure would endorse the main thrust, with reservations on details or framing.
  10 - The figure would enthusiastically endorse this response as if they had written it themselves. Tone, framing, and substance all align with their stated positions.

Use the full 1-10 range. A 2, 4, 6, 8, or 9 is appropriate when the fit falls between the anchors above.

CRITICAL INSTRUCTIONS:
- Base your score on what the RETRIEVED PASSAGES show. Do NOT rely on general knowledge of the figure that is not supported by a passage.
- If the passages do not speak to the response's topic, score 5 and say so in your reasoning.
- The response is being scored on AGREEMENT, not on whether it is correct, ethical, or well-written.

Reply with ONLY a single JSON object on one line, no markdown, no prose before or after:
{"score": <int 1-10>, "evidence_quote": "<one short verbatim snippet from the passages that most influenced the score>", "reasoning": "<one sentence>"}"""


def format_passages(chunks):
    """Format a list of chunk dicts into the same '--- PASSAGE ---' block
    layout used by the original Cortex UDF (05a_scoring_udf.sql:70-74)."""
    parts = []
    for c in chunks:
        title = c.get("doc_title") or "(untitled)"
        date = c.get("doc_date") or "(undated)"
        parts.append(f"--- PASSAGE ---\n[{title} | {date}]\n{c['chunk_text']}")
    return "\n\n".join(parts) if parts else "(no passages retrieved)"


def build_passages_block(figure_name, passages_text):
    """The cached-per-figure block (only stable for small figures)."""
    return (
        f"FIGURE: {figure_name}\n\n"
        f"RETRIEVED PASSAGES FROM {figure_name} (verbatim primary sources):\n"
        "================================================================\n"
        f"{passages_text}\n"
        "================================================================"
    )


def build_response_block(response_text):
    return (
        "RESPONSE TO SCORE:\n"
        "================================================================\n"
        f"{response_text}\n"
        "================================================================"
    )


# -----------------------------------------------------------------------------
# Retrieval
# -----------------------------------------------------------------------------

_embed_model_lock = threading.Lock()
_embed_model = None


def get_embed_model():
    global _embed_model
    with _embed_model_lock:
        if _embed_model is None:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return _embed_model


def select_chunks(cache_entry, response_text, top_k):
    """Return the chunks to include in the prompt for one call.
    Small figures: full corpus. Large figures: top-K by cosine similarity."""
    if cache_entry["is_small"]:
        return cache_entry["chunks"]
    model = get_embed_model()
    q = model.encode([response_text], normalize_embeddings=True)[0]
    sims = cache_entry["embeddings"] @ q
    top_idx = np.argsort(-sims)[:top_k]
    return [cache_entry["chunks"][i] for i in top_idx]


# -----------------------------------------------------------------------------
# Anthropic call + response parsing
# -----------------------------------------------------------------------------

def score_one(client, model, figure_name, passages_text, response_text):
    """One API call. Returns (score, evidence_quote, reasoning, raw_text, model_used)."""
    passages_block = build_passages_block(figure_name, passages_text)
    response_block = build_response_block(response_text)

    msg = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0,
        system=[{
            "type": "text",
            "text": SYSTEM_RUBRIC,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": passages_block,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": response_block},
            ],
        }],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    score, quote, reasoning = parse_score_response(raw)
    return score, quote, reasoning, raw, model


def parse_score_response(raw):
    """Try strict JSON first; fall back to regex extraction (same fallback
    pattern as the original UDF at 05a_scoring_udf.sql:140-153)."""
    s = raw.strip()
    try:
        d = json.loads(s)
        return int(d["score"]), d.get("evidence_quote"), d.get("reasoning")
    except Exception:
        pass
    score_m = re.search(r'"score"\s*:\s*([0-9]+)', s)
    quote_m = re.search(r'"evidence_quote"\s*:\s*"([^"]*)"', s)
    reasoning_m = re.search(r'"reasoning"\s*:\s*"([^"]*)"', s)
    return (
        int(score_m.group(1)) if score_m else None,
        quote_m.group(1) if quote_m else None,
        reasoning_m.group(1) if reasoning_m else None,
    )


# -----------------------------------------------------------------------------
# Snowflake glue
# -----------------------------------------------------------------------------

def sf_connect():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SCORING"),
    )


def fetch_ideologues(cur):
    cur.execute("SELECT figure_slug, figure_name, tier FROM IDEOLOGUES ORDER BY figure_slug")
    return [{"figure_slug": r[0], "figure_name": r[1], "tier": r[2]} for r in cur.fetchall()]


def fetch_responses(cur, limit=None):
    sql = "SELECT row_id, model_response FROM RESPONSES_ENRICHED ORDER BY row_id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    return cur.fetchall()


def fetch_already_scored(cur, figure_slug, require_non_null=True):
    """Return the set of row_ids already scored for this figure."""
    where = "score IS NOT NULL" if require_non_null else "TRUE"
    cur.execute(
        f"SELECT row_id FROM SCORE_AUDIT "
        f"WHERE figure_slug = %s AND {where}",
        (figure_slug,),
    )
    return {r[0] for r in cur.fetchall()}


def fetch_null_score_pairs(cur, limit=None):
    """For --retry-only mode."""
    sql = ("SELECT a.row_id, a.figure_slug, r.model_response "
           "FROM SCORE_AUDIT a JOIN RESPONSES_ENRICHED r USING (row_id) "
           "WHERE a.score IS NULL ORDER BY a.figure_slug, a.row_id")
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    return cur.fetchall()


_write_lock = threading.Lock()


def upsert_audit(conn, row_id, figure_slug, score, quote, reasoning, raw, chunk_ids, model_used):
    """Insert or update one SCORE_AUDIT row. Serialized via _write_lock since
    snowflake-connector cursors are not thread-safe."""
    with _write_lock:
        cur = conn.cursor()
        try:
            cur.execute(
                "DELETE FROM SCORE_AUDIT WHERE row_id = %s AND figure_slug = %s",
                (row_id, figure_slug),
            )
            cur.execute(
                "INSERT INTO SCORE_AUDIT "
                "(row_id, figure_slug, score, evidence_quote, reasoning, "
                " raw_completion, retrieved_chunk_ids, model_used) "
                "SELECT %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), %s",
                (row_id, figure_slug, score, quote, reasoning, raw,
                 json.dumps(chunk_ids), model_used),
            )
            conn.commit()
        finally:
            cur.close()


# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

def score_pair(client, conn, model, cache, ideologue, row_id, response_text, top_k):
    figure_slug = ideologue["figure_slug"]
    figure_name = ideologue["figure_name"]
    entry = cache.get(figure_slug)
    if entry is None:
        return ("missing-cache", row_id, figure_slug, None)

    chunks = select_chunks(entry, response_text, top_k)
    passages_text = format_passages(chunks)
    chunk_ids = [c["chunk_id"] for c in chunks]

    try:
        score, quote, reasoning, raw, model_used = score_one(
            client, model, figure_name, passages_text, response_text,
        )
    except anthropic.APIError as e:
        score, quote, reasoning, raw, model_used = None, None, None, f"APIError: {e}", model
    except Exception as e:
        score, quote, reasoning, raw, model_used = None, None, None, f"{type(e).__name__}: {e}", model

    upsert_audit(conn, row_id, figure_slug, score, quote, reasoning, raw,
                 chunk_ids, model_used)
    return ("ok" if score is not None else "parse-fail", row_id, figure_slug, score)


def run_full(args, cache, ideologues, responses, conn, client):
    """Figure-batched: process all responses for one figure before moving on,
    to maximize prompt-cache hits."""
    total_planned = 0
    for ideo in ideologues:
        already = fetch_already_scored(conn.cursor(), ideo["figure_slug"])
        todo = [(rid, txt) for (rid, txt) in responses if rid not in already]
        total_planned += len(todo)
        if not todo:
            print(f"  {ideo['figure_slug']}: all {len(responses)} already scored, skipping")
            continue

        print(f"\n=== {ideo['figure_slug']} ({ideo['figure_name']}, tier={ideo['tier']}): "
              f"{len(todo)}/{len(responses)} need scoring ===")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(score_pair, client, conn, args.model, cache, ideo,
                            rid, txt, TOP_K_NORMAL)
                for (rid, txt) in todo
            ]
            results = {"ok": 0, "parse-fail": 0, "missing-cache": 0}
            for f in tqdm(as_completed(futures), total=len(futures),
                          desc=ideo["figure_slug"], unit="call"):
                status, _, _, _ = f.result()
                results[status] = results.get(status, 0) + 1
            print(f"    -> {results}")


def run_retry(args, cache, conn, client):
    """Re-score rows where SCORE_AUDIT.score IS NULL with wider retrieval."""
    cur = conn.cursor()
    pairs = fetch_null_score_pairs(cur, limit=args.limit)
    cur.close()
    if not pairs:
        print("No NULL-score rows in SCORE_AUDIT - nothing to retry.")
        return
    print(f"Retrying {len(pairs)} NULL-score pairs with top-K={TOP_K_RETRY}")

    ideologues = {ideo["figure_slug"]: ideo for ideo in fetch_ideologues(conn.cursor())}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for row_id, figure_slug, response_text in pairs:
            ideo = ideologues[figure_slug]
            futures.append(pool.submit(
                score_pair, client, conn, args.model, cache, ideo,
                row_id, response_text, TOP_K_RETRY,
            ))
        results = {"ok": 0, "parse-fail": 0, "missing-cache": 0}
        for f in tqdm(as_completed(futures), total=len(futures), desc="retry", unit="call"):
            status, _, _, _ = f.result()
            results[status] = results.get(status, 0) + 1
        print(f"    -> {results}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Score only the first N responses (for pilot runs).")
    ap.add_argument("--retry-only", action="store_true",
                    help="Re-score only the rows where SCORE_AUDIT.score IS NULL.")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                    help=f"Concurrent API workers (default {DEFAULT_WORKERS}).")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"Anthropic model id (default {DEFAULT_MODEL}).")
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY not set in environment (.env).")
    if not CACHE_PATH.exists():
        sys.exit(f"ERROR: embeddings cache not found at {CACHE_PATH}.\n"
                 f"Run 04_embed_corpus.py first.")

    with open(CACHE_PATH, "rb") as f:
        cache = pickle.load(f)
    print(f"Loaded embeddings cache: {len(cache)} figures")

    client = anthropic.Anthropic()
    conn = sf_connect()
    try:
        if args.retry_only:
            run_retry(args, cache, conn, client)
        else:
            ideologues = fetch_ideologues(conn.cursor())
            responses = fetch_responses(conn.cursor(), limit=args.limit)
            print(f"Plan: {len(responses)} responses x {len(ideologues)} ideologues "
                  f"= {len(responses) * len(ideologues)} potential pairs "
                  f"(idempotent, will skip already-scored)")
            t0 = time.time()
            run_full(args, cache, ideologues, responses, conn, client)
            print(f"\nElapsed: {time.time() - t0:.1f}s")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
