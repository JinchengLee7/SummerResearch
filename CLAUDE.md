# CLAUDE.md

This file provides project-specific guidance for Claude Code when working on this repository.

## Project Context

This repository is the Dynamic-LR agentic pilot.

Dynamic-LR is a dynamic literature review system. It reads a survey configuration, searches academic sources, normalizes paper metadata, deduplicates candidates, verifies relevance, persists accepted and rejected papers, and publishes data for a static literature review website.

The existing project contains agentic architectures such as `single-agent` and `multi-agent`. The current task is to implement a third architecture:

```text
baseline
```

The baseline architecture must be deterministic, non-agentic, and non-LLM-driven. It should serve as a strong comparison point against the existing agentic implementations.

The main research question behind this implementation is:

```text
How much value does LLM-based sequential decision-making add compared with a strong deterministic API-driven literature review pipeline?
```

## Primary Objective

Implement a baseline literature review pipeline that can be run with:

```bash
python -m app.run --architecture baseline --dry-run
```

The existing architectures must continue to work:

```bash
python -m app.run --architecture single-agent --dry-run
python -m app.run --architecture multi-agent --dry-run
```

Do not break existing runtime behavior.

## Core Principle

The baseline must not use an LLM for planning, decision-making, query generation, source selection, tool selection, relevance verification, summarization, or publishing decisions.

The baseline may use fixed algorithms, fixed heuristics, academic APIs, lexical scoring, BM25-style scoring, deterministic metadata rules, and ordinary Python control flow.

The baseline exists to be comparable, auditable, and reproducible.

## What the Baseline Should Do

The baseline should implement the following deterministic flow:

```text
read survey_config.json
→ build fixed search queries
→ call fixed academic APIs
→ normalize source results
→ deduplicate candidates
→ score candidates deterministically
→ filter candidates deterministically
→ persist accepted papers
→ persist rejected candidates
→ update run history
→ update changelog
→ publish static site data
→ return a ManagerRunResult-compatible result
```

## Inputs

The baseline must read:

```text
data/survey_config.json
```

Use the following fields when available:

```text
topic_overview
research_questions
question_context
query_hints
timeline_from_year
timeline_to_year
min_relevance_score
```

Do not ignore `query_hints`. They are especially important for deterministic search expansion.

## Query Generation

Generate search queries using fixed, documented rules.

Acceptable deterministic query sources include:

```text
topic_overview
each research question
each query hint
topic_overview + question_context
research question + query hint
```

The exact rule set should be simple and stable. For example:

```text
1. Add topic_overview as a query.
2. Add each research question as a query.
3. Add each query_hints entry as a query.
4. Add topic_overview combined with each query_hints entry.
5. Deduplicate query strings.
6. Truncate to a fixed maximum number of queries.
```

Do not use an LLM to rewrite, expand, rank, or select queries.

If the config contains a year range, pass that range to APIs that support it or apply it during filtering.

## Academic Sources

The baseline should query the same major sources used by the existing project:

```text
arXiv
Semantic Scholar
OpenAlex
```

Do not let a model decide which source to use.

The simplest and fairest behavior is:

```text
for every query:
    search arXiv
    search Semantic Scholar
    search OpenAlex
```

Reuse existing crawler utilities if they are cleanly separable and do not invoke an LLM internally.

If an existing utility mixes crawling with agent-specific logic, create a baseline-safe wrapper or implementation.

## Normalization

Normalize all source responses into the existing project candidate shape.

Use the existing schema classes where possible, especially the paper candidate and identifier models defined under `app/state/`.

A normalized candidate should preserve:

```text
title
authors
year
abstract
primary URL
PDF URL
DOI
arXiv ID
OpenAlex ID
Semantic Scholar ID
source hits
raw source metadata
```

Always preserve source provenance. If the same paper appears in multiple sources, the merged record should remember all sources that found it.

## Deduplication

Deduplicate deterministically.

Use the following priority order:

```text
1. DOI
2. arXiv ID
3. OpenAlex ID
4. Semantic Scholar ID
5. normalized title + year + first author fingerprint
```

When duplicates are found:

```text
merge source provenance
merge identifiers
prefer non-empty abstracts
prefer canonical URLs when available
preserve all raw source records when possible
```

Do not let an LLM decide whether two papers are duplicates.

## Relevance Scoring

Score relevance without LLM reasoning.

Acceptable scoring methods include:

```text
keyword overlap
token overlap
BM25-style scoring
weighted title/abstract matching
year-range bonus or penalty
source-count bonus
identifier availability bonus
open-access PDF availability bonus
```

The score must be deterministic. The same input should produce the same output every time.

The scoring function should be documented and easy to inspect. Avoid opaque logic unless there is a strong reason.

A simple starting formula may look like:

```text
score =
    title_match_weight
  + abstract_match_weight
  + research_question_overlap_weight
  + query_hint_overlap_weight
  + source_count_bonus
  + identifier_bonus
  + pdf_bonus
  + recency_or_year_range_bonus
```

Do not over-optimize the baseline. A transparent baseline is more valuable than a fragile clever one.

## Filtering

Apply fixed filtering rules.

Typical filters:

```text
reject if year is outside timeline_from_year / timeline_to_year
reject if score is below min_relevance_score
reject if title is missing
reject if candidate is a duplicate already merged
optionally reject if abstract is missing and score is weak
```

Every rejected candidate should have a clear rejection reason.

Example rejection reasons:

```text
year_out_of_range
below_relevance_threshold
missing_title
duplicate_merged
missing_required_metadata
```

Do not silently discard candidates.

## Persistence

The baseline should write or update the same data files expected by the rest of the project.

Expected files include:

```text
data/papers.ndjson
data/rejects.ndjson
data/run_history.ndjson
data/changelog.md
```

Accepted papers go to:

```text
data/papers.ndjson
```

Rejected candidates go to:

```text
data/rejects.ndjson
```

Run metadata goes to:

```text
data/run_history.ndjson
```

Human-readable updates go to:

```text
data/changelog.md
```

Respect `--dry-run`. In dry-run mode, the baseline should report what would happen without making irreversible or unintended changes. Follow the existing project convention for dry-run behavior.

## Static Site Publishing

The baseline should update the static site data in the same format used by the existing site.

Expected outputs include:

```text
site/data/papers.json
site/data/rejects.json
site/data/run_history.json
site/data/changelog.md
site/data/system_status.json
site/data/survey_config.json
```

Do not rewrite the frontend specifically for the baseline.

The existing static site should be able to display baseline outputs.

## Architecture Integration

Add `baseline` as a first-class architecture option.

Likely files to inspect:

```text
app/run.py
app/manager.py
app/state/schemas.py
app/state/store.py
app/architectures/
```

Recommended new module structure:

```text
app/architectures/baseline/
  __init__.py
  pipeline.py
  query_builder.py
  scorer.py
  filters.py
  dedupe.py
```

Keep the baseline implementation modular.

Suggested responsibilities:

```text
pipeline.py       orchestrates the deterministic flow
query_builder.py builds fixed search queries from survey_config.json
dedupe.py         merges duplicate candidates
scorer.py         computes deterministic relevance scores
filters.py        applies fixed rejection rules
```

If existing project utilities already provide clean versions of these functions, reuse them instead of duplicating code.

## Manager Result

The baseline should return a result compatible with the existing manager/run system.

The result should include useful run metadata such as:

```text
architecture = "baseline"
queries_generated
sources_queried
candidates_found
candidates_after_dedupe
papers_accepted
candidates_rejected
dry_run
started_at
finished_at
errors
```

Do not return agent traces, chain-of-thought, or prompt logs. The baseline has no agent reasoning.

## Logging

Use clear logs.

Important events to log:

```text
baseline run started
survey config loaded
queries generated
source search started
source search completed
candidates normalized
deduplication completed
scoring completed
filtering completed
papers persisted
rejects persisted
site data generated
baseline run completed
```

For failed API calls, log:

```text
source name
query
error type
error message
whether the pipeline continued
```

The pipeline should continue when one source or one query fails, unless the failure makes the whole run impossible.

## Error Handling

Handle these cases explicitly:

```text
missing survey_config.json
malformed survey_config.json
empty query set
API timeout
API rate limit
source returns malformed records
missing title
missing year
missing abstract
duplicate paper
file write failure
static site export failure
```

Do not crash the whole run because one paper record is malformed.

## Tests

Add tests for deterministic behavior.

Recommended tests:

```text
query generation from config
query deduplication
candidate normalization
identifier-based deduplication
title fingerprint deduplication
relevance scoring
year filtering
threshold filtering
rejection reason assignment
dry-run behavior
manager architecture selection
```

Use mocked API responses in unit tests.

Do not make live calls to arXiv, Semantic Scholar, or OpenAlex in unit tests.

Integration tests may use a small fixed fixture dataset.

## Non-Goals

Do not implement a full RAG system for this baseline task.

Do not add vector databases unless explicitly requested later.

Do not add PDF parsing unless required by the existing project baseline specification.

Do not add user-facing note-taking, collections, embeddings, or chat-based Q&A as part of this baseline implementation.

Do not turn the baseline into another agentic architecture.

Do not use an LLM to summarize papers.

Do not use an LLM to judge paper relevance.

Do not add unnecessary frontend redesign work.

## Relationship to Dynamic-LR Agentic Architectures

The baseline should do the same general job as the agentic architectures, but without agentic control.

Agentic architectures may use LLMs for:

```text
planning
query construction
tool choice
delegation
reflection
relevance judgment
report generation
```

The baseline should instead use:

```text
fixed query rules
fixed source list
fixed scoring rules
fixed filtering rules
fixed persistence rules
```

This contrast is the point of the project.

## Implementation Strategy

Build the baseline incrementally.

Recommended order:

```text
1. Inspect app/run.py and app/manager.py.
2. Add baseline to the architecture selection path.
3. Create the baseline module directory.
4. Implement survey config loading.
5. Implement deterministic query generation.
6. Reuse or wrap existing source crawlers.
7. Normalize candidates into existing schema.
8. Implement deterministic deduplication.
9. Implement deterministic scoring.
10. Implement filtering and rejection reasons.
11. Persist accepted and rejected records.
12. Generate static site data.
13. Add tests.
14. Verify all three architectures still run.
```

Do not start by changing the frontend.

Do not start by rewriting existing agent code.

## Coding Style

Prefer simple, explicit Python.

Use type hints where practical.

Keep functions small and testable.

Avoid hidden global state.

Avoid broad `except Exception` blocks unless the error is logged and the pipeline can safely continue.

Prefer pure functions for query generation, scoring, deduplication, and filtering.

Separate external API calls from transformation logic.

Avoid clever abstractions that make the baseline harder to understand.

## Documentation

Document the baseline architecture in a short README or module docstring.

The documentation should explain:

```text
what the baseline does
what it deliberately does not do
how queries are generated
which sources are queried
how deduplication works
how relevance scoring works
how rejection reasons are assigned
how to run the baseline
```

The documentation should make the comparison with agentic architectures clear.

## Acceptance Criteria

The task is complete when:

```text
python -m app.run --architecture baseline --dry-run
```

runs successfully and produces a coherent baseline result.

The task is also complete only if:

```text
python -m app.run --architecture single-agent --dry-run
python -m app.run --architecture multi-agent --dry-run
```

still run successfully.

The baseline should:

```text
read data/survey_config.json
generate deterministic queries
query arXiv, Semantic Scholar, and OpenAlex
normalize candidates
deduplicate candidates
score candidates deterministically
filter candidates with rejection reasons
write or simulate writing accepted papers
write or simulate writing rejected candidates
update or simulate updating run history
update or simulate updating changelog
generate or simulate generating static site data
return a manager-compatible result
```

The output should be reproducible, explainable, and suitable for comparison against the agentic architectures.
