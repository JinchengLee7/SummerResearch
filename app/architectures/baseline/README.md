# Baseline Architecture

The baseline is a **deterministic, LLM-free** literature review pipeline. It exists to serve as a strong comparison point for the agentic architectures.

## What it does

Given a `survey_config.json`, the baseline:

1. Builds fixed search queries using documented rules (no LLM)
2. Calls arXiv, Semantic Scholar, and OpenAlex for every query
3. Normalises all results into a shared `PaperCandidate` schema
4. Deduplicates by identifier priority (DOI → arXiv → OpenAlex → S2 → title fingerprint)
5. Scores each candidate using keyword token overlap (8 weighted components)
6. Filters candidates by fixed rules, assigning a `rejection_reason` to each reject
7. Persists accepted and rejected records to NDJSON
8. Exports data for the static site

## What it deliberately does not do

- Use an LLM for any decision (planning, query expansion, relevance judgment, summarisation)
- Use vector embeddings during the pipeline run (those live in `app/server.py`)
- Make probabilistic or stochastic decisions
- Skip silently — every rejected candidate has a documented reason

## Query generation rules

```
1. topic_overview                           → 1 query
2. each research_question                   → N queries
3. each query_hint                          → M queries
4. topic_overview + each query_hint         → M queries
5. Deduplicate
6. Truncate to MAX_QUERIES = 20
```

Queries are never rewritten or ranked by an LLM.

## Source querying

For every query: search arXiv, then Semantic Scholar, then OpenAlex. Source selection is fixed — no model chooses which API to call.

**arXiv**: Atom XML feed, stdlib `urllib` only, 3 retries.  
**Semantic Scholar**: REST JSON, free-tier rate limit (~1 req/s), exponential backoff (5s, 15s) on 429.  
**OpenAlex**: REST JSON, `?` stripped from query strings to avoid 400 errors.

## Deduplication priority

```
1. DOI  (canonical, most reliable)
2. arXiv ID
3. OpenAlex ID
4. Semantic Scholar ID
5. normalised_title|year|first_author_last_name  (fingerprint fallback)
```

When merging duplicates: prefer non-empty abstract, merge source lists, keep all identifiers.

## Relevance scoring

| Component | Weight |
|---|---|
| Title token overlap with all query terms | 0.30 |
| Abstract token overlap | 0.25 |
| Research question term overlap | 0.20 |
| Query hint term overlap | 0.10 |
| Extra source bonus (per additional source, max ×2) | 0.05 |
| Identifier availability | 0.05 |
| Open-access PDF available | 0.03 |
| Year within declared timeline | 0.07 |

Score is `round(min(total, 1.0), 4)`. Stop words are excluded. The same input always produces the same score.

## Filtering rules (applied in order)

1. `missing_title` — title is absent or blank
2. `year_out_of_range` — outside `timeline_from_year` / `timeline_to_year`
3. `below_relevance_threshold` — score < `min_relevance_score`

## How to run

```bash
python -m app.run --architecture baseline --dry-run   # no files written
python -m app.run --architecture baseline              # writes data/
python -m app.run --architecture baseline --verbose    # debug logging
```

## Module responsibilities

| File | Responsibility |
|---|---|
| `pipeline.py` | Orchestrates the full flow, returns `ManagerRunResult` |
| `query_builder.py` | Builds fixed queries from `SurveyConfig` |
| `dedupe.py` | Identifier + fingerprint deduplication with merge |
| `scorer.py` | Deterministic keyword-overlap scoring |
| `filters.py` | Rule-based rejection with documented reasons |
