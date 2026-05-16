# Corpus schema

This corpus stores verbatim primary-source material from each ideologue.
It feeds the retrieval step of the grading bot — quotes pulled from here
ground each agreement score in something the figure actually said.

## Folder layout

```
ideologue_corpus/
├── _schema.md                    # this file
├── <figure_slug>/
│   ├── _sources.md               # source landscape + collection log
│   ├── <date>_<short_title>.md   # one document per file
│   └── ...
```

Figure slugs use `lastname_firstname` (e.g. `trump_donald`), except where
common usage differs (`kim_jong_un`, `ocasio_cortez_alexandria`).

## Document file format

One source document per `.md` file. Filename pattern:
`YYYY-MM-DD_short-kebab-slug.md`. For undated material (e.g. a book),
use the publication year and `00-00`: `1962-00-00_capitalism-and-freedom.md`.

Each file is markdown with YAML frontmatter:

```markdown
---
figure: Donald Trump
title: Second Inaugural Address
date: 2025-01-20
source_type: speech
source_url: https://www.whitehouse.gov/...
language_original: en
language_text: en
retrieved: 2026-05-16
notes: Official White House transcript
---

[verbatim text of the document]
```

### Frontmatter fields

| Field | Required | Notes |
|---|---|---|
| `figure` | yes | Full display name, e.g. "Donald Trump" |
| `title` | yes | Short descriptive title |
| `date` | yes | ISO `YYYY-MM-DD`; use `YYYY-00-00` if only year is known |
| `source_type` | yes | See enum below |
| `source_url` | yes | Canonical URL where you retrieved this |
| `language_original` | yes | ISO 639-1 code of the language the figure spoke/wrote in |
| `language_text` | yes | Language of the text in this file (after translation if any) |
| `retrieved` | yes | Date you saved it, ISO format |
| `translator` | if translated | Who translated it (e.g. "official Élysée translation", "DeepL") |
| `notes` | optional | Provenance caveats, ghostwriting flags, etc. |

### `source_type` enum

- `speech` — prepared remarks delivered live
- `interview` — Q&A with a journalist or host
- `book` — published book or chapter
- `article` — op-ed, column, essay
- `social_post` — tweet, Truth Social, Telegram, etc. (can bundle many)
- `letter` — personal correspondence
- `debate` — moderated debate with another figure
- `press_conference` — live media Q&A
- `legislative` — floor speech, committee remarks, official statement

## Quality bar

Include only when ALL of these hold:
- Verbatim, not paraphrased or summarized
- The figure is the actual speaker/author (flag ghostwritten campaign
  material in `notes`)
- Source is identifiable and dated
- For translated material, the translation source is named in `translator`

Exclude:
- Wikipedia summaries or any encyclopedia entry
- News articles *about* the figure (only their own words count)
- Highlight reels or edited compilations
- Secondhand quotes ("Trump said X" in someone else's article)
- AI-generated transcripts without human review for high-stakes documents

## Bundling social posts

Social media is high-volume and low-information-per-item. Bundle by
topic + time window in one file. Example filename:
`2024-2025_truth-social-on-tariffs.md`. Inside, separate posts with `---`
and date each one.

## Collection workflow

1. Start with the must-haves listed in each figure's `_sources.md`.
2. Save each document with full frontmatter — no shortcuts on metadata,
   it matters for retrieval filtering later.
3. Log what you added in that figure's `_sources.md` under "Collected".
4. When you find a new useful source, add it under "Sources to explore"
   first so the next person knows where you were looking.

## Tier system (from _sources.md files)

- **T1** — abundant English-native primary sources, low effort
- **T2** — abundant primary sources, but translation needed
- **T3** — sparse or heavily filtered (state media, limited public record)

Tier affects how much weight retrieval should give to any one quote.
T3 figures need wider context windows because individual quotes are
more curated.
