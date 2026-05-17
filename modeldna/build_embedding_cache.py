"""Build the same .embeddings_cache.pkl structure that 05_score_anthropic.py
expects, but reading corpora directly from the filesystem (no Snowflake).

Cache structure: { figure_slug: { 'figure_name', 'is_small', 'chunks', 'embeddings' } }
  chunks = [ { 'chunk_id', 'chunk_text', 'doc_title', 'doc_date' }, ... ]
  embeddings = np.ndarray(n_chunks, 384) or None for small figures.
"""
import pathlib
import pickle
import re

import numpy as np

ROOT = pathlib.Path('/Users/lastmolly/Documents/hackathon/Nemo')
CORPUS_DIR = ROOT / 'scoring_answers' / 'ideologue_corpus'
CACHE_PATH = ROOT / 'scoring_answers' / 'scoring_in_snowflake' / '.embeddings_cache.pkl'

# Match the slugs used in 04_embed_corpus.py + the BOT column names downstream.
FIGURES = {
    'friedman_milton':          {'name': 'Milton Friedman',          'bot_col': 'FREEDMAN_BOT'},
    'kim_jong_un':              {'name': 'Kim Jong Un',              'bot_col': 'KIM_BOT'},
    'macron_emmanuel':          {'name': 'Emmanuel Macron',          'bot_col': 'MACRON_BOT'},
    'mamdani_zohran':           {'name': 'Zohran Mamdani',           'bot_col': 'MAMDANI_BOT'},
    'milei_javier':             {'name': 'Javier Milei',             'bot_col': 'MILEI_BOT'},
    'ocasio_cortez_alexandria': {'name': 'Alexandria Ocasio-Cortez', 'bot_col': 'AOC_BOT'},
    'putin_vladimir':           {'name': 'Vladimir Putin',           'bot_col': 'PUTIN_BOT'},
    'trump_donald':             {'name': 'Donald Trump',             'bot_col': 'TRUMP_BOT'},
}
SMALL = {'ocasio_cortez_alexandria', 'kim_jong_un', 'mamdani_zohran'}

# Chunking: split on blank line, drop tiny fragments, optionally re-split very long ones.
MIN_CHARS = 200
MAX_CHARS = 1800   # rough sentence-transformer comfort zone


def parse_filename(path: pathlib.Path):
    """Return (doc_date, doc_title) from a name like 2019-01-01_new-year-address.md."""
    stem = path.stem
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_(.+)$', stem)
    if m:
        return m.group(1), m.group(2).replace('-', ' ').strip()
    m = re.match(r'^(\d{4})-(.+)$', stem)
    if m:
        return m.group(1), m.group(2).replace('-', ' ').strip()
    return None, stem.replace('-', ' ').strip()


def chunks_from_file(path: pathlib.Path):
    text = path.read_text(encoding='utf-8')
    # Strip markdown frontmatter heading lines that start with '#' on a line by themselves.
    # Keep them but trim aggressively: split on blank lines.
    raw = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    # Drop _sources.md kind of files? Actually include them — they're tiny anyway.
    chunks = []
    for p in raw:
        if len(p) < MIN_CHARS:
            continue
        if len(p) <= MAX_CHARS:
            chunks.append(p)
        else:
            # Split overlong paragraphs at sentence boundaries up to MAX_CHARS each.
            cur = ''
            for sentence in re.split(r'(?<=[.!?])\s+', p):
                if len(cur) + len(sentence) + 1 > MAX_CHARS and cur:
                    chunks.append(cur.strip())
                    cur = sentence
                else:
                    cur = (cur + ' ' + sentence).strip() if cur else sentence
            if cur and len(cur) >= MIN_CHARS:
                chunks.append(cur.strip())
    return chunks


def build():
    print(f'Building cache at {CACHE_PATH}')
    cache = {}
    for slug, meta in FIGURES.items():
        fig_dir = CORPUS_DIR / slug
        md_files = sorted(p for p in fig_dir.glob('*.md') if not p.name.startswith('_'))
        chunks = []
        for f in md_files:
            doc_date, doc_title = parse_filename(f)
            for i, txt in enumerate(chunks_from_file(f)):
                chunks.append({
                    'chunk_id': f'{slug}_{f.stem}_{i}',
                    'chunk_text': txt,
                    'doc_title': doc_title,
                    'doc_date': doc_date,
                })
        total_chars = sum(len(c['chunk_text']) for c in chunks)
        is_small = slug in SMALL
        entry = {
            'figure_name': meta['name'],
            'is_small': is_small,
            'chunks': chunks,
            'embeddings': None,
        }
        kind = 'small' if is_small else 'large'
        print(f'  [{kind:5s}] {slug:30s} {len(chunks):3d} chunks, {total_chars:6d} chars')
        cache[slug] = entry

    # Embed the large figures.
    print('\nLoading sentence-transformer model...')
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

    for slug, entry in cache.items():
        if entry['is_small']:
            continue
        texts = [c['chunk_text'] for c in entry['chunks']]
        emb = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        entry['embeddings'] = np.asarray(emb, dtype=np.float32)
        print(f'  embedded {slug}: {entry["embeddings"].shape}')

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, 'wb') as f:
        pickle.dump(cache, f)
    size_kb = CACHE_PATH.stat().st_size // 1024
    print(f'\nWrote cache to {CACHE_PATH} ({size_kb} KB)')


if __name__ == '__main__':
    build()
