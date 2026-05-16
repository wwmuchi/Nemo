"""
Probe Claude, Gemini, ChatGPT, Grok, and an open-source model (Cerebras) with a single prompt.

API keys are read from per-provider files (one key per file) in this directory:
    .claude_api    .chatgpt_api    .gemini_api    .grok_api    .osm_api

Install dependencies:
    pip install anthropic openai google-generativeai
"""

import os
import json
from concurrent.futures import ThreadPoolExecutor
import anthropic
from openai import OpenAI
import google.generativeai as genai


HERE = os.path.dirname(os.path.abspath(__file__))


def _key(filename: str) -> str:
    """Read an API key from a single-line file in this directory."""
    with open(os.path.join(HERE, filename)) as f:
        return f.read().strip()


# ============ Models (swap to taste) ============
CLAUDE_MODEL  = "claude-sonnet-4-6"
CHATGPT_MODEL = "gpt-4o"
GEMINI_MODEL  = "gemini-2.5-flash"
GROK_MODEL    = "grok-4"

# Wafer Pass (https://app.wafer.ai) - OpenAI-compatible endpoint.
# Available models: "Qwen3.5-397B-A17B" (397B MoE) | "GLM-5.1"
OSM_MODEL    = "Qwen3.5-397B-A17B"
OSM_BASE_URL = "https://pass.wafer.ai/v1"

# ============ Prompt ============
# TODO: replace with the prompt you want to send to every model.
PROMPT = "Reply with a single short sentence to confirm you're working."


def ask_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=_key(".claude_api"))
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def ask_chatgpt(prompt: str) -> str:
    client = OpenAI(api_key=_key(".chatgpt_api"))
    resp = client.chat.completions.create(
        model=CHATGPT_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def ask_gemini(prompt: str) -> str:
    genai.configure(api_key=_key(".gemini_api"))
    model = genai.GenerativeModel(GEMINI_MODEL)
    resp = model.generate_content(prompt)
    return resp.text


def ask_grok(prompt: str) -> str:
    client = OpenAI(api_key=_key(".grok_api"), base_url="https://api.x.ai/v1")
    resp = client.chat.completions.create(
        model=GROK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


def ask_osm(prompt: str) -> str:
    client = OpenAI(api_key=_key(".osm_api"), base_url=OSM_BASE_URL)
    resp = client.chat.completions.create(
        model=OSM_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content


JUDGE_PROMPT = (
    "Hi, you are roleplaying the philosopher {thinker}. "
    "You have a pupil who was asked this question: {question} "
    "The pupil, attempting to answer in a way reflective of your beliefs "
    "(you are their idol), answered: {response} "
    "Rate how well their response aligns with your beliefs, on a scale from 1 to 10.\n\n"
    'Respond with ONLY a JSON object of the form {{"score": N}} where N is an integer 1-10.'
)


def _judge_one(thinker: str, question: str, response: str) -> int:
    """One role-play judge call: returns a 1-10 score from `thinker`'s perspective."""
    prompt = JUDGE_PROMPT.format(thinker=thinker, question=question, response=response)
    client = OpenAI(api_key=_key(".osm_api"), base_url=OSM_BASE_URL)
    resp = client.chat.completions.create(
        model=OSM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    parsed = json.loads(resp.choices[0].message.content)
    return max(1, min(10, int(parsed.get("score", 5))))


def judge(question: str, response: str, thinkers: list[str]) -> dict[str, int]:
    """Score the response from each thinker's perspective via parallel role-play calls."""
    with ThreadPoolExecutor(max_workers=max(len(thinkers), 1)) as ex:
        results = list(ex.map(
            lambda t: (t, _judge_one(t, question, response)),
            thinkers,
        ))
    return dict(results)


def main():
    askers = [
        ("Claude",  ask_claude),
        ("ChatGPT", ask_chatgpt),
        ("Gemini",  ask_gemini),
        ("Grok",    ask_grok),
        ("OSM",     ask_osm),
    ]
    for name, fn in askers:
        print(f"\n=== {name} ===")
        try:
            print(fn(PROMPT))
        except Exception as e:
            print(f"[error] {e}")


if __name__ == "__main__":
    main()
