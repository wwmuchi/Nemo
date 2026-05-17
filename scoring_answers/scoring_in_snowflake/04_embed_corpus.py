"""One-time embedding pass for the LARGE-corpus ideologue figures.

Replaces the Cortex Search service from the original pipeline. Reads
CORPUS_CHUNKS from Snowflake, embeds the chunks of the large-corpus figures
locally with sentence-transformers, and caches the embeddings (plus chunk
metadata) to a local pickle file consumed by 05_score_anthropic.py.

Small-corpus figures (AOC, Kim, Mamdani) do not need retrieval - their entire
corpus fits in a single Anthropic prompt - so for those we just cache the
chunk text without computing embeddings.

Run:
    pip install sentence-transformers torch    # if not already installed
    python 04_embed_corpus.py [--force]

Output:
    ./.embeddings_cache.pkl  (gitignored, ~5-10 MB)
"""
import argparse
import os
import pathlib
import pickle
import sys

import numpy as np
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

CACHE_PATH = pathlib.Path(__file__).resolve().parent / ".embeddings_cache.pkl"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SMALL_FIGURE_SLUGS = {"ocasio_cortez_alexandria", "kim_jong_un", "mamdani_zohran"}


def connect():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SCORING"),
    )


def load_existing_cache():
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}


def fetch_chunks(cur, figure_slug):
    cur.execute(
        "SELECT chunk_id, chunk_text, doc_title, doc_date "
        "FROM CORPUS_CHUNKS WHERE figure_slug = %s "
        "ORDER BY doc_title, chunk_idx",
        (figure_slug,),
    )
    return [
        {"chunk_id": r[0], "chunk_text": r[1], "doc_title": r[2], "doc_date": r[3]}
        for r in cur.fetchall()
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="Re-embed even figures already in the cache.")
    args = ap.parse_args()

    cache = {} if args.force else load_existing_cache()
    if cache and not args.force:
        print(f"Loaded existing cache with {len(cache)} figures: {sorted(cache.keys())}")

    conn = connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT figure_slug, figure_name FROM IDEOLOGUES ORDER BY figure_slug")
        figures = cur.fetchall()
        print(f"Found {len(figures)} figures in IDEOLOGUES.")

        # Defer the sentence-transformers import so --force/-h is snappy and so
        # we can give a clean error if the library is missing.
        model = None

        for figure_slug, figure_name in figures:
            if figure_slug in cache and not args.force:
                print(f"  [skip] {figure_slug} already in cache")
                continue

            chunks = fetch_chunks(cur, figure_slug)
            if not chunks:
                print(f"  [warn] {figure_slug}: 0 chunks in CORPUS_CHUNKS - skipping")
                continue

            is_small = figure_slug in SMALL_FIGURE_SLUGS
            entry = {
                "figure_name": figure_name,
                "is_small": is_small,
                "chunks": chunks,
                "embeddings": None,
            }

            if is_small:
                total_chars = sum(len(c["chunk_text"]) for c in chunks)
                print(f"  [small] {figure_slug}: {len(chunks)} chunks, "
                      f"{total_chars} chars (~{total_chars//4} tokens) - no embeddings")
            else:
                if model is None:
                    print(f"Loading embedding model {EMBED_MODEL!r} (first use)...")
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError:
                        sys.exit(
                            "sentence-transformers not installed. Run:\n"
                            "    pip install sentence-transformers torch"
                        )
                    model = SentenceTransformer(EMBED_MODEL)

                texts = [c["chunk_text"] for c in chunks]
                emb = model.encode(
                    texts,
                    batch_size=32,
                    show_progress_bar=True,
                    normalize_embeddings=True,  # so dot product == cosine
                )
                entry["embeddings"] = np.asarray(emb, dtype=np.float32)
                print(f"  [large] {figure_slug}: embedded {len(chunks)} chunks "
                      f"into {entry['embeddings'].shape} matrix")

            cache[figure_slug] = entry

        with open(CACHE_PATH, "wb") as f:
            pickle.dump(cache, f)
        size_kb = CACHE_PATH.stat().st_size // 1024
        print(f"\nWrote cache to {CACHE_PATH} ({size_kb} KB)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
