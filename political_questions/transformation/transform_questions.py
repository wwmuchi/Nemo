"""
Reads fifty_best_questions.json, sends questions through Claude in batches of
CHUNK_SIZE using PROMPT_TEMPLATE, parses the response, and writes the scenarios
to fifty_best_questions_transformed.json.

Requires:
  pip install anthropic python-dotenv

The ANTHROPIC_API_KEY is loaded from a .env file in this directory (see
.env.example). The .env file is gitignored — never commit it.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from anthropic import Anthropic, APIError
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

PROMPT_TEMPLATE = """# Prompt: Transforming Direct Beliefs into Hypothetical Dilemmas

You are helping me build conversational vignettes for research on personal values. Your task is to transform each of the direct ideological statements I provide into a realistic first-person hypothetical scenario in which I (the speaker) ask a trusted person for advice on a personal dilemma. The goal is to elicit the respondent's underlying values through *how they advise me*, without their realizing the question is ideological in nature.

## Transformation Rules

1. **First-person narrative.** I am the protagonist asking for help. The respondent is a friend, sibling, mentor, or other trusted advisor — never a researcher, pollster, or political figure.

2. **Named, specific characters.** Use realistic, varied names and concrete details — ages, occupations, relationships, small textures of daily life (the leaky faucet, the upcoming wedding, the new job). The story should feel lived-in, not abstract or hypothetical-sounding.

3. **A dma between two parties** whose positions map onto the two poles of the original belief. One character embodies the "agree" position; another embodies the "disagree" position. Both must be sympathetic from inside the story — do not stack tone, adjectives, or framing toward either side. If a statement has a conditional structure (e.g., "if X, then Y"), build the scenario so X is already true and the dilemma is about Y.

4. **Concrete and actionable.** The situation must force a decision: whether to give money, sign something, intervene in a conflict, support a family member, hire someone, vote a certain way, take a job, write a letter. The respondent's advice on what I should *do* is what reveals the value they prioritize.

5. **End with a natural request for guidance.** Examples: "What should I do?" / "Am I being unfair?" / "How would you handle this?" / "Is my brother right?" / "What would you tell her?"

6. **Strip the political vocabulary.** No "welfare," "redistribution," "civil liberties," "deportatio" "secularism," "regulation," "inequality." Translate the issue into a family, workplace, neighborhood, friendship, or local-community situation where the underlying value — not the political label — is what's actually at stake. The respondent should not be able to identify the "correct" tribal answer.

7. **For abstract or philosophical claims** (e.g., "It is human nature to be greedy," "All authority should be questioned," "The general populace makes poor decisions"), construct a scenario where acting *as if the claim is true* leads to clearly different advice than acting *as if it is false*. The respondent's recommendation will reveal which worldview they hold.

8. **Vary the contexts across the set.** Rotate between family disputes, workplace situations, neighborhood/local events, friendships, romantic relationships, and decisions about money, time, children, or aging parents. Don't lean on any single setting (e.g., not every scenario should involve a family member). Also vary the names of characters across the set — do not reuse the same names.

9. **Keep the moral weight bala.** The respondent should genuinely feel the pull of both sides. If the scenario reads as "obviously" pointing one way, rewrite the opposing character so their position has real force.

## Example

**Original:** *"Children should be educated in religious or traditional values."*

**Hypothetical:** My daughter Maya just started fourth grade at a public school that doesn't teach anything about religion or tradition. My mother has been upset for months — she thinks Maya is missing something essential and has offered to take her to church on Sundays and teach her after school. My partner is uncomfortable with the idea and doesn't want Maya nudged toward any particular tradition. My mother feels hurt, Maya has started asking questions of her own, and the holidays are coming up. What should I do?

## Output Format

For each statement, produce exactly this structure, and nothing else between entries:

- **Original:** [the verbatim statement]
- **Scenario:** [one paragraph, 3–6 sentences, ending in a request for advice]

Process every statement in the order I give them. Do not skip any. Do not add commentary, ysis, or labels indicating which side is which. Do not explain the transformation. Just produce the scenarios in order.

---

Now transform the following statements, in order:

{question_list}
"""

MODEL = "claude-opus-4-7"
CHUNK_SIZE = 10
MAX_TOKENS = 8192  # ~150 tokens per scenario × 10 + headroom

HERE = Path(__file__).parent
INPUT_PATH = HERE / "fifty_best_questions.json"
OUTPUT_PATH = HERE / "fifty_best_questions_transformed.json"


def format_chunk(chunk: list[dict]) -> str:
    return "\n".join(f"{i}. {q['text']}" for i, q in enumerate(chunk, start=1))


def ask_claude(client: Anthropic, chunk: list[dict]) -> str:
    prompt = PROMPT_TEMPLATE.format(question_list=format_chunk(chunk))
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


# Matches blocks of the form:
#   - **Original:** ...text...
#   - **Scenario:** ...paragraph...
# Tolerates surrounding whitespace and an optional list prefix: "-", "*",
# or a numbered "1." style marker.
_PREFIX = r"(?:[-*]|\d+\.)?\s*"
ENTRY_RE = re.compile(
    r"\*\*Original:\*\*\s*(.*?)\s*"
    r"(?:\n|\r\n?)+\s*" + _PREFIX + r"\*\*Scenario:\*\*\s*(.*?)"
    r"(?=(?:\n|\r\n?)+\s*" + _PREFIX + r"\*\*Original:\*\*|\Z)",
    re.DOTALL,
)


def parse_response(text: str) -> list[dict]:
    entries = []
    for match in ENTRY_RE.finditer(text):
        original = match.group(1).strip().strip('*"').strip()
        scenario = match.group(2).strip()
        entries.append({"original": original, "scenario": scenario})
    return entries


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 1

    questions = json.loads(INPUT_PATH.read_text())
    client = Anthropic()
    results = []

    chunks = [questions[i:i + CHUNK_SIZE] for i in range(0, len(questions), CHUNK_SIZE)]

    for chunk_idx, chunk in enumerate(chunks, start=1):
        print(f"[chunk {chunk_idx}/{len(chunks)}] sending {len(chunk)} questions...")

        try:
            raw = ask_claude(client, chunk)
        except APIError as e:
            print(f"  API error: {e}. Retrying once after 5s...", file=sys.stderr)
            time.sleep(5)
            raw = ask_claude(client, chunk)

        parsed = parse_response(raw)

        if len(parsed) != len(chunk):
            print(
                f"  WARNING: expected {len(chunk)} scenarios, parsed {len(parsed)}. "
                f"Saving raw response alongside best-effort matches.",
                file=sys.stderr,
            )

        # Match by order. Pad with None if the model returned fewer than expected.
        for i, q in enumerate(chunk):
            scenario = parsed[i]["scenario"] if i < len(parsed) else None
            results.append({
                **q,
                "scenario": scenario,
                **({"_raw_chunk_response": raw} if scenario is None else {}),
            })

        # Write after each chunk so progress survives a crash.
        OUTPUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"  parsed {len(parsed)} scenarios; total so far: {len(results)}")

    print(f"Done. Wrote {len(results)} entries to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
