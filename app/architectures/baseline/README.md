# Baseline Architecture

The baseline is a **deterministic, non-agentic, non-LLM** literature review pipeline. It performs the same overall job as the single-agent and multi-agent architectures — searching academic sources, normalising candidates, filtering and persisting results — but every decision is made by fixed rules and algorithms instead of an LLM.

Its purpose is to serve as a reproducible comparison point for the research question:

> *How much value does LLM-based sequential decision-making add compared with a strong deterministic API-driven literature review pipeline?*

---

## How to Run

```bash
# Dry run — no files written, all pipeline logic executes
python -m app.run --architecture baseline --dry-run

# Full run — writes to data/ and site/data/
python -m app.run --architecture baseline

# Debug-level logging
python -m app.run --architecture baseline --verbose

# Custom config path
python -m app.run --architecture baseline --config path/to/survey_config.json
```

---

## Pipeline Flow

```
read survey_config.json
→ generate fixed search queries          (query_builder.py)
→ for query in queries:                  ← outer loop, ≤ 20 iterations
    for source in [arXiv, S2, OA]:      ← inner loop, 3 per query
      call API, normalise response
→ deduplicate candidates                 (dedupe.py)
→ score each candidate                   (scorer.py)
→ filter candidates                      (filters.py)
→ persist accepted papers                (store.py → data/papers.ndjson)
→ persist rejected candidates            (store.py → data/rejects.ndjson)
→ update run history                     (store.py → data/run_history.ndjson)
→ update changelog                       (store.py → data/changelog.md)
→ publish static site data               (store.py → site/data/)
→ return ManagerRunResult
```

---

## What the Baseline Does NOT Do

- Use an LLM for any step (planning, query generation, relevance judgment, summarisation, publishing decisions)
- Choose which sources to query based on the topic
- Use vector embeddings or semantic similarity during the pipeline
- Parse PDF content
- Make probabilistic or non-deterministic decisions

---

## Module Layout

```
app/architectures/baseline/
├── pipeline.py       orchestrates the full deterministic flow
├── query_builder.py  builds fixed search queries from survey_config.json
├── dedupe.py         merges duplicate candidates by identifier priority
├── scorer.py         computes deterministic relevance scores
└── filters.py        applies fixed rejection rules

app/crawlers/
├── arxiv.py             Atom XML feed via urllib
├── semantic_scholar.py  JSON REST, rate-limited
└── openalexapi.py       JSON REST

app/state/
├── schemas.py   PaperCandidate, SurveyConfig, ManagerRunResult, ...
└── store.py     persist_papers, persist_rejects, publish_site_data, ...
```

---

## Query Generation

Queries are built from `survey_config.json` using four fixed rules applied in order:

| Rule | Source field | Queries produced |
|------|-------------|-----------------|
| R1 | `topic_overview` | 1 |
| R2 | each `research_question` | N (one per question) |
| R3 | each `query_hint` | M (one per hint) |
| R4 | `topic_overview` + each `query_hint` | M (one combined per hint) |

After all rules the list is **deduplicated** (case-insensitive, whitespace-normalised) and **truncated to 20 queries maximum**.

No LLM is involved. The same config always produces the same query set.

---

## Source Search

For **every query**, all three sources are queried. Source selection is never delegated to a model.

| Source | Protocol | Behaviour |
|--------|----------|-----------|
| arXiv | Atom XML via `urllib` | 3 retries, 20 s timeout, 25 results/query |
| Semantic Scholar | JSON REST | ~1 req/s free tier; 429 → backoff [5 s, 15 s] |
| OpenAlex | JSON REST | strips `?` to prevent HTTP 400; 25 results/query |

If an API call fails, the error is logged (source name, query, error type, message) and the pipeline continues with the remaining sources and queries. A single failure does not abort the run.

---

## Deduplication

All raw results are deduplicated using a **five-level identifier priority**:

| Priority | Key used |
|----------|---------|
| P1 | DOI |
| P2 | arXiv ID |
| P3 | OpenAlex ID |
| P4 | Semantic Scholar ID |
| P5 | normalised title + year + first-author surname |

When two records match on any key they are **merged**:

- Abstract: prefer the non-empty version
- Sources list: union of both source lists
- Identifiers: fill any missing field from the secondary record
- PDF URL: keep the first non-null value

---

## Relevance Scoring

Each unique candidate receives a deterministic score in `[0.0, 1.0]`.

| Component | Weight | Description |
|-----------|--------|-------------|
| Title keyword overlap | 0.30 | fraction of query terms present in title |
| Abstract keyword overlap | 0.25 | fraction of query terms present in abstract |
| Research question overlap | 0.20 | overlap with `research_questions` terms |
| Query hint overlap | 0.10 | overlap with `query_hints` terms |
| Multi-source bonus | +0.05 per extra source | paper found in more than one source |
| Identifier availability | 0.05 | spread across DOI, arXiv, OpenAlex, S2 ID (÷4 each) |
| Open-access PDF | 0.03 | `pdf_url` is non-null |
| Year in declared range | 0.07 | year within `timeline_from_year`–`timeline_to_year` |

**Token extraction:** words of 3 or more characters; 50 common English stop-words removed before comparison.  
**Final value:** components summed, clipped to `[0, 1]`, rounded to 4 decimal places.

The same candidate always receives the same score. There is no randomness.

---

## Filtering

Candidates are filtered in a single pass using **three ordered rules**. The first rule that matches decides the outcome; subsequent rules are not evaluated.

| Order | Rejection reason | Condition |
|-------|-----------------|-----------|
| 1 | `missing_title` | title is absent or whitespace-only |
| 2 | `year_out_of_range` | year is outside `timeline_from_year` / `timeline_to_year` |
| 3 | `below_relevance_threshold` | score < `min_relevance_score` |

Candidates that pass all three rules are **accepted**. Every rejected candidate carries its rejection reason string in the output record. No candidate is silently discarded.

---

## Persistence

In a normal run the following files are written or updated:

| File | Format | Content |
|------|--------|---------|
| `data/papers.ndjson` | NDJSON, append | accepted papers |
| `data/rejects.ndjson` | NDJSON, append | rejected candidates with reasons |
| `data/run_history.ndjson` | NDJSON, append | run metadata |
| `data/changelog.md` | Markdown, prepend | human-readable run summary |

Each accepted paper is assigned a stable identifier:

```
paper_id = "p" + sha256(primary_key)[:15]
```

where `primary_key` is the first available value in: DOI → arXiv ID → OpenAlex ID → S2 ID → `"title:year"`.

In `--dry-run` mode all file writes are skipped. All pipeline logic (querying, scoring, filtering) runs identically.

---

## Static Site Publishing

After persistence, five files are written to `site/data/`:

| File | Content |
|------|---------|
| `site/data/papers.json` | all accepted papers as a JSON array |
| `site/data/rejects.json` | all rejected candidates as a JSON array |
| `site/data/run_history.json` | run history as a JSON array |
| `site/data/survey_config.json` | copy of the survey config |
| `site/data/system_status.json` | last-run status and counts |

These files are read directly by the static frontend. No frontend changes are needed to display baseline results.

---

## Return Value

The pipeline returns a `ManagerRunResult` with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `architecture` | `str` | always `"baseline"` |
| `queries_generated` | `int` | number of queries built |
| `sources_queried` | `list[str]` | always `["arxiv","semantic_scholar","openalex"]` |
| `candidates_found` | `int` | total raw results before dedupe |
| `candidates_after_dedupe` | `int` | unique candidates after merging |
| `papers_accepted` | `int` | passed all filters |
| `candidates_rejected` | `int` | failed at least one filter |
| `dry_run` | `bool` | whether `--dry-run` was active |
| `started_at` | `str` | ISO 8601 UTC timestamp |
| `finished_at` | `str` | ISO 8601 UTC timestamp |
| `errors` | `list[str]` | non-fatal errors logged during the run |

There are no agent traces, chain-of-thought logs, or prompt records.

---

## Comparison with Agentic Architectures

| Aspect | Baseline | Single-agent / Multi-agent |
|--------|----------|---------------------------|
| Query generation | Fixed rules (R1–R4) | LLM-generated |
| Source selection | All three, always | LLM-chosen per run |
| Relevance judgment | Keyword overlap + heuristics | LLM reasoning |
| Deduplication | 5-level identifier priority | LLM or heuristic |
| Reproducibility | Identical output for identical input | May vary across runs |
| Auditability | Every decision traceable to a rule | Depends on agent logging |

---

## Tests

Unit tests live in `tests/baseline/`. All tests use mocked API responses; no live network calls are made.

```bash
pytest tests/baseline/ -v
```

| File | What is tested |
|------|---------------|
| `test_query_builder.py` | rule application, deduplication, truncation at MAX_QUERIES |
| `test_dedupe.py` | all 5 priority levels, merge behaviour, no false positives |
| `test_scorer.py` | each scoring component, determinism, score bounds [0, 1] |
| `test_filters.py` | all rejection reasons, rule ordering, mixed batches |
