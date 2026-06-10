import re
from typing import List

from app.state.schemas import SurveyConfig

MAX_QUERIES = 20


def build_queries(config: SurveyConfig) -> List[str]:
    """
    Build search queries from survey config using fixed, documented rules:
      1. topic_overview
      2. each research question
      3. each query hint
      4. topic_overview + each query hint (combined)
    Deduplicated and capped at MAX_QUERIES.
    """
    raw: List[str] = []

    if config.topic_overview:
        raw.append(config.topic_overview.strip())

    for q in config.research_questions:
        q = q.strip()
        if q:
            raw.append(q)

    for hint in config.query_hints:
        hint = hint.strip()
        if hint:
            raw.append(hint)

    if config.topic_overview:
        for hint in config.query_hints:
            hint = hint.strip()
            if hint:
                raw.append(f"{config.topic_overview.strip()} {hint}")

    seen: set = set()
    deduped: List[str] = []
    for q in raw:
        key = _normalize(q)
        if key and key not in seen:
            seen.add(key)
            deduped.append(q)

    return deduped[:MAX_QUERIES]


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())
