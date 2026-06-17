import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.state.schemas import ManagerRunResult, PaperCandidate, SurveyConfig
from app.state import store
from app.architectures.baseline.query_builder import build_queries
from app.architectures.baseline.dedupe import IncrementalDeduplicator
from app.architectures.baseline.scorer import score as compute_score
from app.architectures.baseline.filters import apply_filters
from app.sources import arxiv, semantic_scholar, openalexapi

logger = logging.getLogger(__name__)

SOURCES = ["arxiv", "semantic_scholar", "openalex"]
RESULTS_PER_SOURCE = 25

# ── Loop-control constants ────────────────────────────────────────────────────
# Saturation detection: if the rolling average new-paper yield over the last
# SATURATION_WINDOW queries drops below SATURATION_THRESHOLD, the outer loop
# exits early.  A yield of 0.05 means fewer than 5 % of the raw API results
# were papers not already seen — a strong signal that more queries add little.
SATURATION_WINDOW = 3
SATURATION_THRESHOLD = 0.05

# Source failure tracking: if the same source raises exceptions on
# MAX_SOURCE_FAILURES consecutive queries it is skipped for all remaining
# queries in this run.  A transient network blip resets the counter.
MAX_SOURCE_FAILURES = 3

_SOURCE_MAP = [
    ("arxiv", arxiv),
    ("semantic_scholar", semantic_scholar),
    ("openalex", openalexapi),
]


def run(
    config_path: str = "data/survey_config.json",
    dry_run: bool = False,
) -> ManagerRunResult:
    started_at = datetime.now(timezone.utc).isoformat()
    errors: List[str] = []

    logger.info("Baseline run started (dry_run=%s)", dry_run)

    config, config_raw = _load_config(config_path, errors)
    if config is None:
        return _make_result(0, 0, 0, 0, 0, dry_run, started_at, errors)

    logger.info("Survey config loaded: %.60s", config.topic_overview)

    queries = build_queries(config)
    logger.info("Queries generated: %d", len(queries))
    for i, q in enumerate(queries, 1):
        logger.debug("  [%d] %s", i, q[:80])

    if not queries:
        errors.append("No queries generated from survey config")
        return _make_result(0, 0, 0, 0, 0, dry_run, started_at, errors)

    logger.info("Source search started")
    unique, candidates_found = _search_all(queries, config, errors)
    logger.info(
        "Source search completed: %d raw candidates, %d unique",
        candidates_found,
        len(unique),
    )
    after_dedupe = len(unique)

    for c in unique:
        c.score = compute_score(c, config)
    logger.info("Scoring completed")

    accepted, rejected = apply_filters(unique, config)
    logger.info("Filtering: %d accepted, %d rejected", len(accepted), len(rejected))

    if not dry_run:
        store.persist_papers(accepted)
        store.persist_rejects(rejected)
        logger.info("Papers persisted")

    finished_at = datetime.now(timezone.utc).isoformat()

    result = ManagerRunResult(
        architecture="baseline",
        queries_generated=len(queries),
        sources_queried=SOURCES,
        candidates_found=candidates_found,
        candidates_after_dedupe=after_dedupe,
        papers_accepted=len(accepted),
        candidates_rejected=len(rejected),
        dry_run=dry_run,
        started_at=started_at,
        finished_at=finished_at,
        errors=errors,
    )

    if not dry_run:
        store.persist_run_history(result)
        store.update_changelog(result, accepted)
        store.publish_site_data(accepted, rejected, result, config_raw or {})
        logger.info("Run history, changelog, and site data updated")

    logger.info(
        "Baseline run completed: %d accepted, %d rejected, %d errors",
        len(accepted),
        len(rejected),
        len(errors),
    )
    return result


def _search_all(
    queries: List[str],
    config: SurveyConfig,
    errors: List[str],
) -> Tuple[List[PaperCandidate], int]:
    """
    Search all sources for every query using three loop-control mechanisms:

    1. Query pre-sorting (specificity order)
       Queries are sorted shortest-first before the outer loop begins.
       Shorter strings are typically the most targeted keyword phrases (R3
       hints), so the outer loop exhausts precise queries before broader ones.
       This maximises utility when saturation triggers an early exit.

    2. Incremental deduplication + saturation detection (outer loop)
       Deduplication runs *inside* the outer loop rather than in a single
       batch after all searches finish.  After each query the new-paper yield
       rate (new unique / total raw) is measured.  When the rolling average
       over SATURATION_WINDOW queries drops below SATURATION_THRESHOLD the
       outer loop exits: further queries are unlikely to contribute new papers.

    3. Source failure tracking (inner loop)
       Each source keeps a consecutive-failure counter.  If a source raises
       exceptions on MAX_SOURCE_FAILURES queries in a row it is skipped for
       all remaining queries in this run.  A successful response resets the
       counter, so a transient failure does not permanently disable a source.

    Returns (unique_candidates, total_raw_count).
    """
    deduplicator = IncrementalDeduplicator()
    total_raw = 0
    source_failures = {name: 0 for name, _ in _SOURCE_MAP}
    recent_yields: List[float] = []

    # ── Pre-sort: shortest queries first (most targeted keyword phrases) ──────
    sorted_queries = sorted(queries, key=len)

    for qi, query in enumerate(sorted_queries):
        raw_this_query = 0
        new_this_query = 0

        # ── Inner loop with failure tracking ─────────────────────────────────
        for src_name, src_module in _SOURCE_MAP:
            if source_failures[src_name] >= MAX_SOURCE_FAILURES:
                logger.warning(
                    "Skipping %s: %d consecutive failures", src_name, MAX_SOURCE_FAILURES
                )
                continue
            try:
                results = src_module.search(
                    query,
                    max_results=RESULTS_PER_SOURCE,
                    year_from=config.timeline_from_year,
                    year_to=config.timeline_to_year,
                )
                n_new = deduplicator.add_batch(results)
                raw_this_query += len(results)
                new_this_query += n_new
                source_failures[src_name] = 0
                logger.debug(
                    "  %s → %d raw, %d new  query: %.40s",
                    src_name, len(results), n_new, query,
                )
            except Exception as exc:
                source_failures[src_name] += 1
                msg = f"{src_name} error on {query!r:.40}: {exc}"
                logger.error(msg)
                errors.append(msg)

        total_raw += raw_this_query

        # ── Saturation detection ──────────────────────────────────────────────
        yield_rate = new_this_query / max(raw_this_query, 1)
        recent_yields.append(yield_rate)
        logger.debug(
            "  Query %d/%d: %d new / %d raw = %.0f%% yield  (unique so far: %d)",
            qi + 1, len(sorted_queries),
            new_this_query, raw_this_query,
            yield_rate * 100,
            len(deduplicator),
        )

        if len(recent_yields) >= SATURATION_WINDOW:
            window_yield = (
                sum(recent_yields[-SATURATION_WINDOW:]) / SATURATION_WINDOW
            )
            if window_yield < SATURATION_THRESHOLD:
                logger.info(
                    "Saturation: %.1f%% avg yield over last %d queries — "
                    "stopping after query %d/%d (%d unique papers so far)",
                    window_yield * 100, SATURATION_WINDOW,
                    qi + 1, len(sorted_queries),
                    len(deduplicator),
                )
                break

    return deduplicator.unique, total_raw


def _load_config(
    path: str, errors: List[str]
) -> Tuple[Optional[SurveyConfig], Optional[dict]]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return (
            SurveyConfig(
                topic_overview=raw.get("topic_overview", ""),
                research_questions=raw.get("research_questions", []),
                question_context=raw.get("question_context", ""),
                query_hints=raw.get("query_hints", []),
                timeline_from_year=raw.get("timeline_from_year"),
                timeline_to_year=raw.get("timeline_to_year"),
                min_relevance_score=float(raw.get("min_relevance_score", 0.0)),
            ),
            raw,
        )
    except FileNotFoundError:
        errors.append(f"survey_config.json not found: {path}")
        return None, None
    except json.JSONDecodeError as exc:
        errors.append(f"Malformed survey_config.json: {exc}")
        return None, None


def _make_result(
    queries: int,
    found: int,
    after_dedupe: int,
    accepted: int,
    rejected: int,
    dry_run: bool,
    started_at: str,
    errors: List[str],
) -> ManagerRunResult:
    return ManagerRunResult(
        architecture="baseline",
        queries_generated=queries,
        sources_queried=SOURCES,
        candidates_found=found,
        candidates_after_dedupe=after_dedupe,
        papers_accepted=accepted,
        candidates_rejected=rejected,
        dry_run=dry_run,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        errors=errors,
    )
