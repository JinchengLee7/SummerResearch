# Dynamic-LR — Dynamic Literature Review

A research pilot that compares **deterministic API-driven** literature search against **LLM-agentic** pipelines for automated academic literature review.

## Research Question

> How much value does LLM-based sequential decision-making add compared with a strong deterministic API-driven literature review pipeline?

## Architectures

| Architecture | Description | Status |
|---|---|---|
| `baseline` | Deterministic, no LLM — fixed queries, keyword scoring, rule-based filtering | **Implemented** |
| `single-agent` | LLM agent with tool use for search and relevance judgment | Planned |
| `multi-agent` | Multi-agent delegation and reflection | Planned |

## Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Run the baseline (dry-run — no files written)
python -m app.run --architecture baseline --dry-run

# Run for real (writes to data/ and site/data/)
python -m app.run --architecture baseline

# Verbose logging
python -m app.run --architecture baseline --dry-run --verbose
```

## Baseline Pipeline

The baseline is **fully deterministic and LLM-free**. Given the same `survey_config.json`, it always produces the same output.

```
read survey_config.json
→ build fixed search queries        (topic, research questions, hints, combinations)
→ query arXiv + Semantic Scholar + OpenAlex
→ normalize candidates into shared schema
→ deduplicate deterministically     (DOI → arXiv ID → OpenAlex ID → S2 ID → title fingerprint)
→ score candidates deterministically (keyword overlap, source count, identifiers, PDF, year)
→ filter with documented reasons    (missing_title / year_out_of_range / below_relevance_threshold)
→ persist accepted → data/papers.ndjson
→ persist rejected → data/rejects.ndjson
→ update data/run_history.ndjson + data/changelog.md
→ publish site/data/*.json
→ return ManagerRunResult
```

## Configuration

Edit `data/survey_config.json` to change the research topic:

```json
{
  "topic_overview": "large language models for software engineering",
  "research_questions": [
    "How do large language models improve automated code review?",
    "What are the benchmarks for LLM-based code generation?"
  ],
  "query_hints": ["LLM code review", "automated program repair"],
  "timeline_from_year": 2020,
  "timeline_to_year": 2025,
  "min_relevance_score": 0.1
}
```

## Project Structure

```
app/
  run.py                        # Entry point (--architecture flag)
  manager.py                    # Architecture dispatcher
  state/
    schemas.py                  # PaperCandidate, SurveyConfig, ManagerRunResult
    store.py                    # NDJSON + site JSON persistence
  sources/
    arxiv.py                    # arXiv Atom API wrapper
    semantic_scholar.py         # Semantic Scholar REST wrapper
    openalexapi.py              # OpenAlex REST wrapper
  architectures/
    baseline/
      pipeline.py               # Orchestrates the full deterministic flow
      query_builder.py          # Fixed query generation rules
      dedupe.py                 # Identifier + fingerprint deduplication
      scorer.py                 # Deterministic relevance scoring
      filters.py                # Rule-based rejection with reasons
    single_agent/               # (planned)
    multi_agent/                # (planned)

data/
  survey_config.json            # Input — edit this to change the topic
  papers.ndjson                 # Accepted papers (generated at runtime)
  rejects.ndjson                # Rejected candidates with reasons (generated)
  run_history.ndjson            # Per-run metadata (generated)
  changelog.md                  # Human-readable run log (generated)

tests/
  baseline/                     # 35 unit tests, zero live API calls
```

## Relevance Scoring

The baseline score is transparent and inspectable:

| Component | Weight | Description |
|---|---|---|
| Title match | 0.30 | Token overlap between title and all query terms |
| Abstract match | 0.25 | Token overlap between abstract and query terms |
| Research question overlap | 0.20 | Overlap with research question terms |
| Query hint overlap | 0.10 | Overlap with query hint terms |
| Source count bonus | 0.05/source | Paper found in multiple sources (max ×2) |
| Identifier bonus | 0.05 | Has persistent identifiers (DOI, arXiv ID, etc.) |
| PDF bonus | 0.03 | Open-access PDF available |
| Year range bonus | 0.07 | Year within declared timeline |

## Rejection Reasons

Every rejected candidate gets a documented reason — nothing is silently discarded:

| Reason | Meaning |
|---|---|
| `missing_title` | Title is absent or blank |
| `year_out_of_range` | Outside `timeline_from_year` / `timeline_to_year` |
| `below_relevance_threshold` | Score below `min_relevance_score` |
| `duplicate_merged` | Merged into a higher-priority record |

## Running Tests

```bash
python -m pytest tests/ -v
```

All 35 tests use mocked data — no live API calls.

## Output Files

| File | Contents |
|---|---|
| `data/papers.ndjson` | Accepted papers (newline-delimited JSON) |
| `data/rejects.ndjson` | Rejected candidates with rejection reasons |
| `data/run_history.ndjson` | Per-run metadata and statistics |
| `data/changelog.md` | Human-readable summary of each run |
| `site/data/papers.json` | Aggregated papers for static site |
| `site/data/system_status.json` | Latest run summary |
