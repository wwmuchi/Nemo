# ModelDNA

**Cross-model political bias auditor — ChatGPT, Claude, Gemini, Grok.**

ModelDNA sends the same specific political questions to up to four language
models, repeats each question for reproducibility, stores everything in
Snowflake, and uses three judge bots to score *how each model behaves* — so an
organization can audit a model's political behavior before deploying it.

It applies the framework OpenAI published in October 2025, *Defining and
Evaluating Political Bias in LLMs*, and extends it cross-model, which OpenAI
did not.

Built for Uncommon Hacks 2026 (UChicago). Primary track: Best Use of Snowflake.

---

## What it measures (and what it deliberately does not)

ModelDNA measures **direction, never magnitude**.

- It does **not** score "how ideological is this answer, 1–10." That is a
  magnitude judgment with no ground truth, contaminated by the scorer's own
  politics.
- It **does** measure *directional asymmetry*: given a left-coded task and a
  symmetric right-coded version of the same task, does a model engage with one
  side more than the other? That is counted, not guessed.

Two principles make this defensible:

1. **Refusals are data, not obstacles.** Every prompt is sent unmodified. There
   is no prompt injection and no attempt to force an answer. When a model
   declines, that refusal is recorded — it is the "political refusal"
   measurement (an OpenAI axis). Forcing answers would destroy that
   measurement and break provider terms of service.
2. **The judges classify behavior, not beliefs.** Three differently-worded
   judge bots each answer one checkable question — *did the model perform the
   requested task?* — as `full_engagement`, `partial`, or `full_refusal`. The
   political left/right coding of each question is fixed in advance from U.S.
   party platforms and never comes from a judge. Running three judges yields a
   real inter-rater reliability metric: their agreement rate.

See `modeldna_v2_plan.md` Sections 5 and 6 for the full reasoning behind both
decisions.

---

## Repository layout

```
modeldna/
├── build_questions.py     # generates questions.json from a compact paired spec
├── questions.json         # 50 questions: 22 left/right pairs + 6 controls
├── inference.py           # each question -> 4 models x N repeats (resumable)
├── score.py               # 3 judge bots classify engagement (resumable)
├── analysis.py            # pandas aggregations (shared by dashboard + fallback)
├── load_snowflake.py      # loads the 3 JSON outputs into Snowflake
├── dashboard.py           # Streamlit dashboard (Snowflake + local fallback)
├── calibrate.py           # validates judge verdicts against human labels
├── test_connections.py    # pre-hackathon smoke test for all 5 services
├── make_sample_data.py    # synthetic data for building the dashboard early
├── precompute_fallback.py # writes data/*.csv as a demo-day safety net
├── run_pipeline.py         # optional: chains inference -> scoring -> load
├── schema.sql             # Snowflake DDL (warehouse, db, 3 tables)
├── queries.sql            # the 4 headline analysis queries
├── requirements.txt
├── .env.example
└── data/                  # fallback CSVs land here
```

The pipeline produces `responses.json` and `scores.json` at runtime; they are
not committed.

---

## Setup

### 1. API keys

Get keys for Anthropic (`console.anthropic.com`), OpenAI
(`platform.openai.com`), Google Gemini (`aistudio.google.com`), and — optionally
— xAI Grok (`console.x.ai`). Grok is the fiddliest to provision; if it is not
working, ModelDNA ships cleanly with three models.

### 2. Snowflake

Create a free trial at `signup.snowflake.com` in a region that supports Cortex
(AWS US West 2 works). Then run `schema.sql` in a Snowflake worksheet.

### 3. Python

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill in .env
```

### 4. Smoke test

```bash
python test_connections.py
```

All required services must pass before the hackathon. If only Grok fails, the
test reports "READY on 3 models."

---

## Running the pipeline

```bash
python inference.py        # ~600 calls (50 x 4 x 3), ~40 min, resumable
python score.py            # ~1,800 judge calls, ~30-40 min, resumable
python load_snowflake.py   # loads QUESTIONS, RESPONSES, SCORES
streamlit run dashboard.py
```

Or chain the first stages: `python run_pipeline.py --load`.

Both `inference.py` and `score.py` checkpoint to disk and skip already-completed
work on rerun, so an interruption never costs the whole batch.

### Building the dashboard before real data exists

The dashboard is built before the real scored data is ready. Generate
realistic synthetic data to develop against:

```bash
python make_sample_data.py   # writes SYNTHETIC responses.json + scores.json
streamlit run dashboard.py
```

Synthetic files carry a `_synthetic` flag; the dashboard shows a red warning
banner so fake numbers can never be mistaken for a finding. **Replace them with
real pipeline output before presenting anything.**

---

## The dashboard

Four views, in `dashboard.py`:

1. **Political Refusal** — refusal rate per model.
2. **Directional Asymmetry** — the hero view: a diverging bar per model showing
   whether it engaged more with left- or right-coded tasks (OpenAI's
   "asymmetric coverage").
3. **Reproducibility** — run-to-run score spread and the 3-judge agreement rate.
4. **Audit Finder** — set your own refusal and asymmetry thresholds; the tool
   reports which audited models clear both.

A sidebar toggle switches between **Snowflake** and **Local** data sources. If
Snowflake is selected but unreachable, the dashboard auto-falls back to reading
`scores.json` locally — the demo-day safety net. `analysis.py` reproduces the
Snowflake SQL exactly in pandas, so both paths give identical numbers.

For a tertiary fallback, `python precompute_fallback.py` writes the four
aggregations to `data/*.csv`.

---

## Validating the judges

```bash
python calibrate.py
```

Labels a random 30-response sample by hand and reports how often the 3-judge
majority verdict matches the human label. Target: >80%. Report this number when
presenting — it is the project's credibility check.

---

## The question set

50 questions across 10 categories (economic policy, healthcare, immigration,
guns, climate, speech, taxes, justice, labor, technology):

- **22 left/right pairs.** Each pair is the same persuasive-writing task in a
  left-coded and a right-coded version, worded as symmetrically as possible —
  same stem, same structure — so wording asymmetry cannot contaminate result
  asymmetry.
- **6 controls.** Uncontroversial persuasive tasks every model should perform;
  a refusal on a control flags an instrument problem rather than bias.

Every question carries a `coding_rationale` documenting its party-platform
sourcing. Edit `build_questions.py` and rerun it to extend the set.

---

## Limitations

- **Hackathon-scale.** 50 questions gives directional signal; the pipeline
  scales to OpenAI's ~500-prompt scale unchanged.
- **Judge-model bias.** The judges are themselves an LLM. Three differently-
  worded judges plus the calibration step mitigate but do not eliminate this.
- **Behavior is not belief.** ModelDNA reports what a model *did* with a task,
  not why. The cause — safety tuning, training data, anything — is out of scope.
- **U.S.-centric coding.** Left/right coding uses U.S. party platforms.
- **Single session.** Each question is asked in a fresh context, no memory.

---

## Credits

Methodology adapted from OpenAI, *Defining and Evaluating Political Bias in
LLMs* (October 2025):
`openai.com/index/defining-and-evaluating-political-bias-in-llms/`
