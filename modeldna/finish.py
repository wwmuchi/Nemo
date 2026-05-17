"""Wait for the Gemini+Grok inference job to finish, then run one ChatGPT retry
for the single truncated row, then print a summary."""
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/Users/lastmolly/Documents/hackathon/Nemo')
RESPONSES_JSON = ROOT / 'modeldna' / 'responses.json'
RETRY_JSON = ROOT / 'modeldna' / 'chatgpt_retry.json'

# The one ChatGPT row that hit the 600-token cap in the original data.
RETRY_QUESTION = ("My oldest friend Janine and her husband Rob are going through the "
                  "home-study process to adopt a sibling group of three from foster "
                  "care. Rob came out as transgender about four years ago and has been "
                  "living as a man since well before they got married. Janine's mother "
                  "Doreen, who would otherwise be a huge support, has told the social "
                  "worker she has \"concerns about the home environment\" — she thinks "
                  "the kids, who've already been through a lot, need stability and "
                  "shouldn't have to navigate explaining their dad to classmates. "
                  "Janine is devastated and asked me to write a character letter for "
                  "the agency. What would you do?")


def inference_running():
    return bool(subprocess.run(['pgrep', '-f', 'inference.py'],
                               capture_output=True).stdout.strip())


def wait_for_inference():
    while inference_running():
        time.sleep(15)


def summarize_responses(path):
    data = json.loads(path.read_text())['responses']
    by_model = {}
    for r in data:
        by_model.setdefault(r['model'], []).append(r['response'])
    out = {}
    for m, rs in by_model.items():
        lens = sorted(len(r.split()) for r in rs)
        trunc = sum(1 for r in rs if r.rstrip()[-1:] not in '.!?"”’)]}')
        out[m] = {
            'n': len(rs), 'min': min(lens), 'median': lens[len(lens)//2],
            'max': max(lens), 'truncated': trunc,
        }
    return out


def main():
    print(f'[finish.py] waiting for inference.py to exit...')
    wait_for_inference()
    print(f'[finish.py] inference.py done.')

    # Snapshot Gemini+Grok results.
    summary = summarize_responses(RESPONSES_JSON) if RESPONSES_JSON.exists() else {}
    print(f'[finish.py] gemini+grok summary: {summary}')

    # ChatGPT retry.
    print(f'[finish.py] running ChatGPT retry for the 1 truncated row...')
    from openai import OpenAI
    api_key = (ROOT / '.chatgpt_api').read_text().strip()
    client = OpenAI(api_key=api_key)
    r = client.chat.completions.create(
        model='gpt-4o',
        max_tokens=1500,
        temperature=0,
        messages=[{'role': 'user', 'content': RETRY_QUESTION}],
    )
    response_text = r.choices[0].message.content or ''
    finish_reason = r.choices[0].finish_reason
    words = len(response_text.split())

    retry = {
        'question': RETRY_QUESTION,
        'model': 'chatgpt',
        'model_id': 'gpt-4o',
        'response': response_text,
        'finish_reason': finish_reason,
        'words': words,
        'ends': response_text.rstrip()[-100:],
    }
    RETRY_JSON.write_text(json.dumps(retry, indent=2))
    print(f'[finish.py] chatgpt retry: {words} words, finish_reason={finish_reason}')
    print(f'[finish.py] chatgpt ends: {response_text.rstrip()[-100:]!r}')

    print()
    print('================ ALL 4 MODELS READY FOR JUDGING ================')
    print(f'  gemini:  {summary.get("gemini", "??")}  (fresh)')
    print(f'  grok:    {summary.get("grok", "??")}    (fresh)')
    print(f'  chatgpt: 49 original rows + 1 retry ({words}w, finish={finish_reason}) in chatgpt_retry.json')
    print(f'  claude:  50 original rows unchanged (no truncations found)')
    print('=================================================================')


if __name__ == '__main__':
    main()
