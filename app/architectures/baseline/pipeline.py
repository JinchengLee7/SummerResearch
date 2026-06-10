import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.state.schemas import ManagerRunResult, PaperCandidate, SurveyConfig
from app.state import store
from app.architectures.baseline.query_builder import build_queries
from app.architectures.baseline.dedupe import deduplicate
from app.architectures.baseline.scorer import score as compute_score
from app.architectures.baseline.filters import apply_filters
from app.sources import arxiv, semantic_scholar, openalexapi

logger = logging.getLogger(__name__)

SOURCES = ["arxiv", "semantic_scholar", "openalex"]
RESULTS_PER_SOURCE = 25


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
    all_candidates = _search_all(queries, config, errors)
    logger.info("Source search completed: %d raw candidates", len(all_candidates))
    candidates_found = len(all_candidates)

    unique, _ = deduplicate(all_candidates)
    logger.info("Deduplication completed: %d unique", len(unique))
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
) -> List[PaperCandidate]:
    candidates: List[PaperCandidate] = []
    source_map = [
        ("arxiv", arxiv),
        ("semantic_scholar", semantic_scholar),
        ("openalex", openalexapi),
    ]
    for query in queries:
        for src_name, src_module in source_map:
            try:
                results = src_module.search(
                    query,
                    max_results=RESULTS_PER_SOURCE,
                    year_from=config.timeline_from_year,
                    year_to=config.timeline_to_year,
                )
                candidates.extend(results)
                logger.debug("  %s → %d for: %.40s", src_name, len(results), query)
            except Exception as exc:
                msg = f"{src_name} error on {query!r:.40}: {exc}"
                logger.error(msg)
                errors.append(msg)
    return candidates


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
