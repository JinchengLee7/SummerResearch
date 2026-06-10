# Dynamic-LR — Dynamic Literature Review

A research pilot comparing **deterministic API-driven** literature search against **LLM-agentic** pipelines for automated academic literature review.

## Research Question

> How much value does LLM-based sequential decision-making add compared with a strong deterministic API-driven literature review pipeline?

## Architectures

| Architecture | Description | Status |
|---|---|---|
| `baseline` | Deterministic, no LLM — fixed queries, keyword scoring, rule-based filtering | **Implemented** |
| `single-agent` | LLM agent with tool use for search and relevance judgment | Planned |
| `multi-agent` | Multi-agent delegation and reflection | Planned |

---

## Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Run the baseline (dry-run — no files written)
python -m app.run --architecture baseline --dry-run

# Run for real (writes to data/ and site/data/)
python -m app.run --architecture baseline

# Start the interactive server (embedding index + full CRUD)
python -m app.server

# Run tests
python -m pytest tests/ -v
```

---

## Baseline Pipeline

The baseline is **fully deterministic and LLM-free**. Given the same `survey_config.json` and the same API responses, it always produces the same output.

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

---

## Interactive Server

`app/server.py` is a Flask server that builds an **embedding index** at startup and then serves a read/write API alongside the static frontend.

### Startup sequence

```
1. Load fastembed model (BAAI/bge-small-en-v1.5, ~130 MB, downloaded once)
2. Load survey config → embed topic + research questions + hints as query vectors
3. Load papers.ndjson + rejects.ndjson into memory
4. Assign stable paper_id to any record missing one
5. Batch-embed all paper segments (title + abstract sentences)
6. Compute embedding_score for every paper via MaxSim
7. Persist updated records + refresh site/data/
```

First startup downloads the model (~130 MB) and takes 30–60 seconds. Subsequent starts take 15–40 seconds depending on corpus size.

### Run the server

```bash
python -m app.server              # defaults: http://127.0.0.1:8000
python -m app.server --port 9000  # custom port
python -m app.server --verbose    # debug logging
```

### REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/status` | Index state: `index_ready`, `papers`, `rejects` |
| `GET` | `/api/papers` | All accepted papers (in-memory, includes `embedding_score`) |
| `GET` | `/api/rejects` | All rejected candidates |
| `GET` | `/api/search?q=…` | Live search: DB similarity + external API calls |
| `PUT` | `/api/papers/:id` | Edit title / year / abstract; triggers re-embedding |
| `POST` | `/api/papers/:id/reject` | Move paper to rejects with a reason |
| `POST` | `/api/rejects/:id/approve` | Move reject back to accepted |
| `DELETE` | `/api/papers/:id` | Permanently delete a paper |
| `POST` | `/api/candidates/add` | Add a candidate from live search to the database |

---

## Embedding Scoring

When the server runs, each paper is scored by two methods simultaneously:

| Score | Field | Description |
|---|---|---|
| Keyword (`score`) | `score` | Token overlap with survey config terms (see weights below) |
| Embedding (`embedding_score`) | `embedding_score` | MaxSim cosine similarity via fastembed |

**MaxSim**: for each paper, the abstract is split into sentences. Each sentence and the title are embedded separately. The score is `max(cosine(paper_segment_i, query_j))` across all pairs, normalised to `[0, 1]`.

**Model**: `BAAI/bge-small-en-v1.5` (384-dim, ONNX runtime, ~130 MB). No GPU required.

---

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

---

## Keyword Relevance Scoring

The baseline `score` field is transparent and inspectable:

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

---

## Rejection Reasons

Every rejected candidate has a documented reason — nothing is silently discarded:

| Reason | Meaning |
|---|---|
| `missing_title` | Title is absent or blank |
| `year_out_of_range` | Outside `timeline_from_year` / `timeline_to_year` |
| `below_relevance_threshold` | Score below `min_relevance_score` |
| `duplicate_merged` | Merged into a higher-priority record |
| `manually_rejected` | Rejected via the server UI |

---

## Project Structure

```
app/
  run.py                        # Entry point (--architecture flag)
  manager.py                    # Architecture dispatcher
  server.py                     # Flask API server + embedding index
  state/
    schemas.py                  # PaperCandidate, SurveyConfig, ManagerRunResult
    store.py                    # NDJSON persistence, make_paper_id, load/save
  sources/
    arxiv.py                    # arXiv Atom API wrapper (stdlib only)
    semantic_scholar.py         # Semantic Scholar REST wrapper
    openalexapi.py              # OpenAlex REST wrapper
  architectures/
    baseline/
      pipeline.py               # Orchestrates the full deterministic flow
      query_builder.py          # Fixed query generation rules
      dedupe.py                 # Identifier + fingerprint deduplication
      scorer.py                 # Deterministic relevance scoring
      filters.py                # Rule-based rejection with reasons
      README.md                 # Baseline architecture documentation
    single_agent/               # (planned)
    multi_agent/                # (planned)
  embeddings/
    segmenter.py                # Regex sentence splitter for paper text
    embedder.py                 # fastembed wrapper + MaxSim scoring
    index.py                    # In-memory EmbeddingIndex with batch build

data/
  survey_config.json            # Input — edit this to change the topic
  papers.ndjson                 # Accepted papers (generated at runtime)
  rejects.ndjson                # Rejected candidates with reasons (generated)
  run_history.ndjson            # Per-run metadata (generated)
  changelog.md                  # Human-readable run log (generated)

site/
  index.html                    # Single-file frontend (no build step)
  data/                         # JSON exports read by the frontend

tests/
  baseline/                     # Baseline pipeline unit tests (35 tests)
  test_store.py                 # Store + make_paper_id tests (11 tests)
  test_embedder.py              # MaxSim scoring tests (8 tests)
  baseline/test_segmenter.py    # Sentence segmentation tests (7 tests)
```

---

## Output Files

| File | Contents |
|---|---|
| `data/papers.ndjson` | Accepted papers (newline-delimited JSON, append-only by pipeline) |
| `data/rejects.ndjson` | Rejected candidates with rejection reasons |
| `data/run_history.ndjson` | Per-run metadata and statistics |
| `data/changelog.md` | Human-readable summary of each run |
| `site/data/papers.json` | Aggregated papers for static site |
| `site/data/system_status.json` | Latest run summary |

---

## Paper Identity

Each paper gets a stable `paper_id` assigned at write time in `persist_papers()`. The ID is a SHA-256 hash of the highest-priority available identifier:

```
Priority: DOI → arXiv ID → OpenAlex ID → Semantic Scholar ID → title:year
Format:   "p" + sha256(key).hexdigest()[:15]
Example:  "p3a8f2c9d1e4b7a"
```

IDs are consistent regardless of which source found the paper first.

---

## Known Limitations

**Semantic Scholar rate limiting**: The free tier allows ~1 request/second. Under sustained load, queries return HTTP 429. The pipeline handles this gracefully (continues without S2 results) but S2 coverage will be incomplete without an API key. To add a key, set `X-API-Key` in `app/sources/semantic_scholar.py`.

**OpenAlex question-form queries**: OpenAlex search returns HTTP 400 for queries containing `?`. The pipeline strips `?` characters before sending to OpenAlex.

**Embedding cold start**: The fastembed model (~130 MB) is downloaded on first server startup. Subsequent startups load from disk cache.

**NDJSON append behavior**: The pipeline appends to `papers.ndjson` and `rejects.ndjson`. Running the pipeline multiple times without clearing these files will accumulate duplicates in the NDJSON. The site data (`site/data/papers.json`) always reflects the full accumulated file. The server's `save_papers` / `save_rejects` functions do atomic overwrites and will not accumulate duplicates when using the CRUD API.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

**63 tests** covering:
- Baseline query generation, deduplication, scoring, filtering
- Store: `make_paper_id`, `load/save` roundtrip, persistence
- Embedding: `MaxSim` scoring, edge cases (empty vectors, non-unit vectors)
- Segmenter: sentence splitting, length filtering

All tests use mocked or in-process data — no live API calls.
