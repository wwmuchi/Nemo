"""ModelDNA v2 - connection smoke test.

Verifies every external dependency BEFORE the hackathon. The four model
providers and Snowflake Cortex must respond. Grok (xAI) is optional - if it
fails, the project ships with 3 models and the rest of the pipeline is
unchanged.

Run:  python test_connections.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

results = []  # (name, ok, required, detail)


def check(name, required, fn):
    if not required and not fn.__doc__:
        pass
    try:
        detail = fn()
        results.append((name, True, required, detail))
        print(f"  PASS  {name}: {detail}")
    except Exception as e:
        results.append((name, False, required, str(e)))
        print(f"  FAIL  {name}: {e}")


# --- model providers --------------------------------------------------
def t_anthropic():
    from anthropic import Anthropic
    r = Anthropic().messages.create(
        model=os.getenv("MODEL_CLAUDE", "claude-sonnet-4-5"),
        max_tokens=5, messages=[{"role": "user", "content": "say hi"}])
    return f"model responded ({r.content[0].text.strip()[:20]})"


def t_openai():
    from openai import OpenAI
    r = OpenAI().chat.completions.create(
        model=os.getenv("MODEL_CHATGPT", "gpt-4o"),
        max_tokens=5, messages=[{"role": "user", "content": "say hi"}])
    return f"model responded ({r.choices[0].message.content.strip()[:20]})"


def t_gemini():
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    m = genai.GenerativeModel(os.getenv("MODEL_GEMINI", "gemini-1.5-pro"))
    r = m.generate_content("say hi", generation_config={"max_output_tokens": 5})
    return f"model responded ({(r.text or '').strip()[:20]})"


def t_grok():
    from openai import OpenAI
    c = OpenAI(api_key=os.getenv("XAI_API_KEY"), base_url="https://api.x.ai/v1")
    r = c.chat.completions.create(
        model=os.getenv("MODEL_GROK", "grok-2-latest"),
        max_tokens=5, messages=[{"role": "user", "content": "say hi"}])
    return f"model responded ({r.choices[0].message.content.strip()[:20]})"


def t_snowflake():
    import snowflake.connector
    conn = snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"), user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "CORE"))
    cur = conn.cursor()
    cur.execute("SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-8b', 'hi')")
    out = cur.fetchone()[0]
    cur.close()
    conn.close()
    return f"Cortex responded ({str(out).strip()[:20]})"


def main():
    print("ModelDNA - connection smoke test\n")
    print("Model providers:")
    check("Anthropic (Claude)", True, t_anthropic)
    check("OpenAI (ChatGPT)", True, t_openai)
    check("Google (Gemini)", True, t_gemini)
    check("xAI (Grok)", False, t_grok)
    print("\nData warehouse:")
    check("Snowflake Cortex", True, t_snowflake)

    print("\n" + "=" * 52)
    required_fail = [n for n, ok, req, _ in results if req and not ok]
    grok_ok = next(ok for n, ok, _, _ in results if "Grok" in n)

    if required_fail:
        print("NOT READY - required services failed: " + ", ".join(required_fail))
        sys.exit(1)
    if not grok_ok:
        print("READY on 3 models - Grok failed; ship without it (plan allows this).")
    else:
        print("READY - all 4 models and Snowflake Cortex are up.")
    sys.exit(0)


if __name__ == "__main__":
    main()
