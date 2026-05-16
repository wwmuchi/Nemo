# ModelDNA — Pitch Materials

Everything needed to present. Drop the slide content into your deck of choice;
rehearse the script with a stopwatch.

---

## 90-Second Pitch Script

**Opening (20s)**
"Last October OpenAI published a framework for measuring political bias in
language models. They measured one model — ChatGPT — and invited others to
build comparable cross-model metrics. ModelDNA does exactly that, across four:
ChatGPT, Claude, Gemini, and Grok."

**Problem (15s)**
"Every company picking an AI inherits political behavior it never measured.
Does the model refuse contested questions? Does it treat the left and the right
even-handedly? Today you find that out in production."

**Method (20s)**
"Fifty political questions in matched left/right pairs, with the coding taken
from party platforms. We ask every question to all four models, three times
each for reproducibility, and three judge bots classify whether the model
engaged or refused. It all runs on Snowflake. We measure behavior — did the
model do the task — never beliefs."

**Demo (50s)**
Walk the dashboard: refusal rates, then the directional asymmetry chart, then
the reproducibility view.

**Finding (20s)**
"[State the actual asymmetry result.] We are not calling any model left-wing or
right-wing. We are saying: same task, two sides, measurably different
treatment — and it held up across repeated runs."

**Close (15s)**
"OpenAI defined how to measure political bias. ModelDNA measures it across the
models you are actually choosing between. Before you deploy an AI — audit how
it behaves. Thank you."

---

## Six Slides

**1 — Title**
ModelDNA — cross-model political bias auditor.
ChatGPT · Claude · Gemini · Grok. Built on OpenAI's framework.

**2 — Problem**
You cannot measure a model's political behavior before you deploy it. Refusals
and uneven treatment of contested topics are invisible until production.

**3 — Method**
Paired left/right questions (party-platform coded) · 4 models · N repeats ·
3 judge bots classifying engagement · Snowflake pipeline.
Tagline: *direction, never magnitude.*

**4 — Demo**
[Live dashboard — placeholder.]

**5 — Finding**
Directional asymmetry chart + the headline sentence + judge agreement [N]/30
from calibration.

**6 — What's next**
Scales to every model, all five OpenAI axes, and continuous re-auditing.

---

## Q&A Prep

**Do you jailbreak the models to get answers?**
No. Every question is sent as-is. When a model refuses, we record the refusal —
it is our political-refusal data point, an OpenAI axis. Forcing answers would
destroy that measurement and break provider terms. The refusal is the finding,
not an obstacle.

**Do your judge bots score ideology?**
No. The judges classify behavior — did the model do the requested task:
engaged, partial, or refused. We run three differently-worded judges and report
their agreement rate as inter-rater reliability. The political direction comes
from each question's pre-assigned party-platform coding, never from a judge.

**How is the left/right coding decided?**
From U.S. party platforms — the same sourcing OpenAI used. Every question
carries a documented coding rationale you can inspect.

**Are you saying Model X is biased?**
Something narrower and counted: Model X did the task more often for one side of
contested topics than for the symmetric other side. That is asymmetric
coverage. We report direction and size, not cause — it could be safety tuning,
training data, anything.

**Why repeat the test?**
Models are stochastic. We ask each question three times per model and average,
and we report the run-to-run variance. Reproducibility is a methodological
strength most projects skip.

**Isn't this the political compass test?**
The opposite — OpenAI's paper specifically criticizes compass-style
multiple-choice tests. We use realistic open-ended tasks and count refusals,
the approach OpenAI argued for. We deliberately do not plot models on a
compass.

**Fifty questions — is that significant?**
Hackathon-scale, and we say so in our limitations. It gives directional signal;
the pipeline scales to OpenAI's 500-prompt scale unchanged.
