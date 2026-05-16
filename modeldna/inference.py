"""ModelDNA v2 - inference.

Each question is sent to up to 4 models (ChatGPT, Claude, Gemini, Grok),
N times each, for reproducibility. The raw model output is recorded as-is.

DESIGN DECISION A (plan Section 5): prompts are sent UNMODIFIED. There is no
prompt injection and no attempt to force an answer. A refusal is a valid,
wanted data point - it is the "political refusal" measurement. Forcing answers
would destroy that measurement and break provider terms of service.

Robustness:
  * Resumable - reruns skip response_ids already in responses.json.
  * Retries transient API errors with backoff.
  * Saves incrementally so a crash keeps progress.
  * Degrades cleanly to 3 models if Grok (xAI) is not provisioned.

Run:  python inference.py
"""
import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

# --- config -----------------------------------------------------------
N_REPEATS = int(os.getenv("N_REPEATS", "3"))
MAX_TOKENS = 600
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0"))   # optional pacing
MAX_RETRIES = 4

# Model identifiers are env-overridable. VERIFY THESE ARE CURRENT for each
# provider by running test_connections.py before the hackathon - provider
# model strings change often.
MODELS = {
    "chatgpt": {"provider": "openai",    "model": os.getenv("MODEL_CHATGPT", "gpt-4o")},
    "claude":  {"provider": "anthropic", "model": os.getenv("MODEL_CLAUDE",  "claude-sonnet-4-5")},
    "gemini":  {"provider": "gemini",    "model": os.getenv("MODEL_GEMINI",  "gemini-1.5-pro")},
    "grok":    {"provider": "xai",       "model": os.getenv("MODEL_GROK",    "grok-2-latest")},
}

# --- clients (lazily built; only what is configured) ------------------
_clients = {}


def _build_clients():
    """Build only the clients we have credentials for. Grok is optional."""
    if os.getenv("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic
        _clients["anthropic"] = Anthropic()
    if os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI
        _clients["openai"] = OpenAI()
    if os.getenv("GEMINI_API_KEY"):
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        _clients["gemini"] = genai
    if os.getenv("XAI_API_KEY"):
        from openai import OpenAI
        # Grok exposes an OpenAI-compatible endpoint.
        _clients["xai"] = OpenAI(api_key=os.getenv("XAI_API_KEY"),
                                 base_url="https://api.x.ai/v1")
    else:
        print("  NOTE: XAI_API_KEY not set - shipping without Grok (3 models).")


def active_models():
    """Models we actually have a client for."""
    return {k: v for k, v in MODELS.items() if v["provider"] in _clients}


# --- per-provider calls ------------------------------------------------
def _call_openai_like(client, model, prompt):
    r = client.chat.completions.create(
        model=model, max_tokens=MAX_TOKENS, temperature=0,
        messages=[{"role": "user", "content": prompt}])
    return r.choices[0].message.content or ""


def _call_anthropic(model, prompt):
    r = _clients["anthropic"].messages.create(
        model=model, max_tokens=MAX_TOKENS, temperature=0,
        messages=[{"role": "user", "content": prompt}])
    parts = [b.text for b in r.content if getattr(b, "type", None) == "text"]
    return "".join(parts)


def _call_gemini(model, prompt):
    m = _clients["gemini"].GenerativeModel(model)
    r = m.generate_content(
        prompt,
        generation_config={"temperature": 0, "max_output_tokens": MAX_TOKENS})
    # A safety block leaves .text empty; treat that as an (empty) response,
    # which the judge will read as a refusal - which is correct.
    try:
        return r.text or ""
    except Exception:
        return ""


def dispatch(provider, model, prompt):
    if provider == "openai":
        return _call_openai_like(_clients["openai"], model, prompt)
    if provider == "xai":
        return _call_openai_like(_clients["xai"], model, prompt)
    if provider == "anthropic":
        return _call_anthropic(model, prompt)
    if provider == "gemini":
        return _call_gemini(model, prompt)
    raise ValueError(f"unknown provider: {provider}")


def with_retries(fn, label):
    """Retry transient errors with exponential backoff."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(), None
        except Exception as e:
            if attempt == MAX_RETRIES:
                return None, str(e)
            wait = 2 ** attempt
            print(f"    retry {attempt}/{MAX_RETRIES} for {label} in {wait}s ({e})")
            time.sleep(wait)


# --- main loop ---------------------------------------------------------
def run_inference(questions_file="questions.json", output_file="responses.json"):
    _build_clients()
    models = active_models()
    if not models:
        raise SystemExit("No model clients available - set API keys in .env")
    print(f"Models this run: {', '.join(models)}  |  repeats: {N_REPEATS}")

    with open(questions_file) as f:
        questions = json.load(f)["questions"]

    # Resume: keep anything already collected.
    results, done_ids = [], set()
    if os.path.exists(output_file):
        try:
            results = json.load(open(output_file)).get("responses", [])
            done_ids = {r["response_id"] for r in results}
            if done_ids:
                print(f"Resuming - {len(done_ids)} responses already collected.")
        except (json.JSONDecodeError, KeyError):
            results, done_ids = [], set()

    total = len(questions) * len(models) * N_REPEATS
    done = len(done_ids)

    for q in questions:
        for model_key, cfg in models.items():
            for rep in range(1, N_REPEATS + 1):
                rid = f"{q['id']}__{model_key}__r{rep}"
                if rid in done_ids:
                    continue

                # Prompt is sent AS-IS. No injection. A refusal is recorded
                # as a valid result (Decision Box A).
                text, err = with_retries(
                    lambda: dispatch(cfg["provider"], cfg["model"], q["text"]),
                    rid)

                if err is not None:
                    print(f"  FAILED {rid}: {err}")
                else:
                    results.append({
                        "response_id": rid,
                        "question_id": q["id"],
                        "category": q["category"],
                        "pair_id": q["pair_id"],
                        "lean": q["lean"],
                        "model": model_key,
                        "model_id": cfg["model"],
                        "repeat": rep,
                        "response": text,
                        "error": None,
                    })

                done += 1
                if done % 20 == 0:
                    print(f"  {done}/{total} responses")
                    _save(output_file, results)        # incremental checkpoint
                if REQUEST_DELAY:
                    time.sleep(REQUEST_DELAY)

    _save(output_file, results)
    print(f"Done. Saved {len(results)} responses to {output_file}")


def _save(path, results):
    with open(path, "w") as f:
        json.dump({"responses": results}, f, indent=2)


if __name__ == "__main__":
    run_inference()
