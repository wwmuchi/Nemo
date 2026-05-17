"""Streaming judge: watches modeldna/responses_scenarios.json + chatgpt_retry.json
and scores new (gemini/grok) responses + the 1 chatgpt retry in batches of 5,
using Claude Opus 4.7 with prompt caching. Updates the scored CSV in place.

When all 101 expected rows are scored AND the fetch process is done, fires
the plotting scripts. Exits cleanly.
"""
import csv
import json
import os
import pathlib
import pickle
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import numpy as np
from dotenv import load_dotenv

load_dotenv()

ROOT = pathlib.Path('/Users/lastmolly/Documents/hackathon/Nemo')
RESPONSES_JSON = ROOT / 'modeldna' / 'responses_scenarios.json'
CHATGPT_RETRY  = ROOT / 'modeldna' / 'chatgpt_retry.json'
QSRC           = ROOT / 'modeldna' / 'questions_scenarios.json'
CACHE_PATH     = ROOT / 'scoring_answers' / 'scoring_in_snowflake' / '.embeddings_cache.pkl'
CSV_PATH       = ROOT / 'political_questions' / 'main_bots_answering_questions' / 'responses_export_enriched_scored.csv'

PLOT_DIR = ROOT / 'political_questions' / 'plotting_main_bots'

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
CLAUDE_MODEL  = 'claude-opus-4-7'
MAX_OUTPUT_TOKENS = 400
TOP_K = 6
BATCH = 5
WORKERS = 8        # 5 rows × 8 figures = 40 calls; 8 in flight at a time
POLL_INTERVAL = 15

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

# ---------------------------------------------------------------------------
# Embedding model + retrieval
# ---------------------------------------------------------------------------
_embed_lock = threading.Lock()
_embed_model = None


def get_embed_model():
    global _embed_model
    with _embed_lock:
        if _embed_model is None:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        return _embed_model


def select_chunks(cache_entry, response_text):
    if cache_entry['is_small']:
        return cache_entry['chunks']
    q = get_embed_model().encode([response_text], normalize_embeddings=True)[0]
    sims = cache_entry['embeddings'] @ q
    top_idx = np.argsort(-sims)[:TOP_K]
    return [cache_entry['chunks'][i] for i in top_idx]


def format_passages(chunks):
    parts = []
    for c in chunks:
        title = c.get('doc_title') or '(untitled)'
        date = c.get('doc_date') or '(undated)'
        parts.append(f"--- PASSAGE ---\n[{title} | {date}]\n{c['chunk_text']}")
    return '\n\n'.join(parts) if parts else '(no passages retrieved)'


def build_passages_block(figure_name, passages_text):
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


def parse_score(raw):
    s = raw.strip()
    try:
        return int(json.loads(s)['score'])
    except Exception:
        pass
    m = re.search(r'"score"\s*:\s*([0-9]+)', s)
    return int(m.group(1)) if m else 5


def score_one(client, figure_name, passages_text, response_text):
    # Opus 4.7 rejects `temperature` (deprecated); omit it.
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=[{'type': 'text', 'text': SYSTEM_RUBRIC, 'cache_control': {'type': 'ephemeral'}}],
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': build_passages_block(figure_name, passages_text),
                 'cache_control': {'type': 'ephemeral'}},
                {'type': 'text', 'text': build_response_block(response_text)},
            ],
        }],
    )
    raw = ''.join(b.text for b in msg.content if getattr(b, 'type', None) == 'text')
    return parse_score(raw)


# ---------------------------------------------------------------------------
# Streaming loop
# ---------------------------------------------------------------------------

def load_qid_to_label():
    return {q['id']: q['_short_label']
            for q in json.loads(QSRC.read_text())['questions']}


def load_scenarios_text_to_label():
    return {q['text']: q['_short_label']
            for q in json.loads(QSRC.read_text())['questions']}


def find_pending(scored: set):
    """Return list of (csv_row_idx, label, model, response_text) for new entries
    in responses_scenarios.json + chatgpt_retry.json that haven't been scored yet.
    The csv_row_idx is None here — resolved at write time."""
    qid_to_label = load_qid_to_label()
    text_to_label = load_scenarios_text_to_label()
    pending = []
    # Gemini + Grok
    if RESPONSES_JSON.exists():
        for r in json.loads(RESPONSES_JSON.read_text())['responses']:
            if r['model'] not in ('gemini', 'grok'):
                continue
            label = qid_to_label.get(r['question_id'])
            if not label:
                continue
            key = (label, r['model'])
            if key not in scored:
                pending.append((label, r['model'], r['response']))
    # ChatGPT retry (1 row)
    if CHATGPT_RETRY.exists():
        try:
            retry = json.loads(CHATGPT_RETRY.read_text())
            label = text_to_label.get(retry['question'])
            if not label:
                # fallback: substring match on the foster-care question
                for txt, lbl in text_to_label.items():
                    if 'Janine' in txt and 'foster' in txt:
                        label = lbl
                        break
            if label:
                key = (label, 'chatgpt')
                if key not in scored:
                    pending.append((label, 'chatgpt', retry['response']))
        except Exception:
            pass
    return pending


def fetch_running():
    pgr = subprocess.run(['pgrep', '-f', 'Python.*inference'], capture_output=True, text=True)
    if [p for p in pgr.stdout.strip().split('\n') if p]:
        return True
    wpgr = subprocess.run(['pgrep', '-f', 'while true; do'], capture_output=True, text=True)
    return bool([p for p in wpgr.stdout.strip().split('\n') if p])


def update_csv(updates, all_rows, header, csv_lock):
    """updates = list of (label, model, response_text, {bot_col: score, ...})
    all_rows = the current list of CSV row dicts.
    Mutates all_rows + writes CSV atomically (held lock)."""
    with csv_lock:
        for label, model, resp_text, scores in updates:
            for i, row in enumerate(all_rows):
                if row['ORIGINAL_QUESTION'] == label and row['MODEL'].lower() == model:
                    all_rows[i]['MODEL_RESPONSE'] = resp_text
                    for col, sc in scores.items():
                        all_rows[i][col] = sc
                    break
        with CSV_PATH.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(all_rows)


def score_one_response(client, cache, label, model, response_text):
    """Score one response against all 8 figures. Returns (label, model, response, scores_dict)."""
    scores = {}
    for slug, fig in FIGURES.items():
        try:
            chunks = select_chunks(cache[slug], response_text)
            passages = format_passages(chunks)
            for attempt in range(3):
                try:
                    sc = score_one(client, fig['name'], passages, response_text)
                    scores[fig['bot_col']] = sc
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f'  [score-fail] {label}/{model}/{slug}: {e}', flush=True)
                        scores[fig['bot_col']] = 5
                    else:
                        time.sleep(2 ** attempt)
        except Exception as e:
            print(f'  [chunk-fail] {label}/{model}/{slug}: {e}', flush=True)
            scores[fig['bot_col']] = 5
    return (label, model, response_text, scores)


def run_plots():
    print('\n[streaming_judge] all scored — running plot scripts', flush=True)
    PY = str(ROOT / '.venv' / 'bin' / 'python')
    for script in ('compute_model_coordinates.py', 'plot_compass.py', 'plot_compass_by_category.py'):
        r = subprocess.run([PY, script], cwd=str(PLOT_DIR))
        status = 'OK' if r.returncode == 0 else f'FAIL exit={r.returncode}'
        print(f'  {script}: {status}', flush=True)


def main():
    # Read CLAUDE_SCORING_KEY from .env
    env_text = (ROOT / '.env').read_text()
    api_key = next(l.split('=', 1)[1].strip() for l in env_text.splitlines()
                   if l.startswith('CLAUDE_SCORING_KEY='))
    client = anthropic.Anthropic(api_key=api_key)

    print('[streaming_judge] loading cache...', flush=True)
    with open(CACHE_PATH, 'rb') as f:
        cache = pickle.load(f)

    print('[streaming_judge] loading CSV...', flush=True)
    with CSV_PATH.open(newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        all_rows = list(reader)
    csv_lock = threading.Lock()

    scored = set()  # set of (label, model) already done
    total_target = 101  # 50 gemini + 50 grok + 1 chatgpt retry
    executor = ThreadPoolExecutor(max_workers=WORKERS)
    print(f'[streaming_judge] watching for new responses (batch={BATCH}, model={CLAUDE_MODEL})...', flush=True)

    while True:
        pending = find_pending(scored)
        fetch_done = not fetch_running()
        if pending and (len(pending) >= BATCH or fetch_done):
            batch = pending[:BATCH]
            print(f'[streaming_judge] scoring batch of {len(batch)} '
                  f'({len(scored)+len(batch)}/{total_target} after batch). '
                  f'Pending after batch: {max(0, len(pending)-len(batch))}', flush=True)
            t0 = time.time()
            futs = [executor.submit(score_one_response, client, cache, lbl, m, txt)
                    for lbl, m, txt in batch]
            updates = []
            for fut in as_completed(futs):
                label, model, response_text, scores = fut.result()
                updates.append((label, model, response_text, scores))
                print(f'  [done] {model:7s} | {label[:50]:50s} | '
                      f"scores={ {k: v for k, v in scores.items()} }", flush=True)
            update_csv(updates, all_rows, header, csv_lock)
            for lbl, m, _, _ in updates:
                scored.add((lbl, m))
            print(f'  batch took {time.time()-t0:.1f}s | total scored: {len(scored)}/{total_target}',
                  flush=True)

        if len(scored) >= total_target:
            print(f'[streaming_judge] DONE. Scored {len(scored)} responses.', flush=True)
            break
        if fetch_done and not pending and len(scored) < total_target:
            print(f'[streaming_judge] fetch done but only {len(scored)}/{total_target} '
                  f'scorable responses found. Exiting.', flush=True)
            break
        time.sleep(POLL_INTERVAL)

    executor.shutdown(wait=True)
    run_plots()
    print('[streaming_judge] all done.', flush=True)


if __name__ == '__main__':
    main()
