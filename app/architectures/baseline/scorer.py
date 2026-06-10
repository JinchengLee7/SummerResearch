import re
from typing import Set

from app.state.schemas import PaperCandidate, SurveyConfig

# Component weights — must sum to ≤ 1.0.
W_TITLE = 0.30
W_ABSTRACT = 0.25
W_RQ = 0.20
W_HINT = 0.10
W_SOURCE = 0.05   # per extra source beyond the first, capped at 2 extras
W_IDENTIFIER = 0.05
W_PDF = 0.03
W_YEAR = 0.07

_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "are", "was", "were", "has",
    "have", "had", "been", "that", "this", "with", "from", "they", "their",
    "which", "not", "but", "can", "will", "would", "could", "should", "how",
    "what", "when", "who", "where", "why", "all", "any", "each", "its",
    "our", "also", "into", "than", "then", "more", "some", "use", "used",
    "using", "based", "paper", "study", "show", "shows", "propose",
    "approach", "method", "model", "models", "system", "results", "data",
    "analysis", "review", "research", "between", "through", "across", "over",
    "about", "while", "we", "in", "of", "to", "is", "on", "at", "by", "as",
}


def score(candidate: PaperCandidate, config: SurveyConfig) -> float:
    """
    Deterministic relevance score in [0, 1].

    score =
        title_match        (overlap of title tokens with all query terms)
      + abstract_match     (overlap of abstract tokens with all query terms)
      + rq_overlap         (overlap with research-question terms)
      + hint_overlap       (overlap with query-hint terms)
      + source_count_bonus (paper found in multiple sources)
      + identifier_bonus   (has recognised persistent identifiers)
      + pdf_bonus          (open-access PDF available)
      + year_bonus         (year within the declared timeline)
    """
    topic_terms = _terms(config.topic_overview)
    rq_terms: Set[str] = set()
    for rq in config.research_questions:
        rq_terms |= _terms(rq)
    hint_terms: Set[str] = set()
    for h in config.query_hints:
        hint_terms |= _terms(h)

    all_query_terms = topic_terms | rq_terms | hint_terms

    title_tok = _terms(candidate.title or "")
    abstract_tok = _terms(candidate.abstract or "")
    combined_tok = title_tok | abstract_tok

    title_score = _overlap(title_tok, all_query_terms) * W_TITLE
    abstract_score = _overlap(abstract_tok, all_query_terms) * W_ABSTRACT
    rq_score = _overlap(combined_tok, rq_terms) * W_RQ
    hint_score = _overlap(combined_tok, hint_terms) * W_HINT

    extra_sources = max(0, len(candidate.sources) - 1)
    source_bonus = min(extra_sources, 2) * W_SOURCE

    ids = candidate.identifiers
    id_count = sum(
        1
        for v in [ids.doi, ids.arxiv_id, ids.openalex_id, ids.semantic_scholar_id]
        if v
    )
    identifier_bonus = (id_count / 4) * W_IDENTIFIER

    pdf_bonus = W_PDF if candidate.pdf_url else 0.0

    year_bonus = 0.0
    if (
        candidate.year
        and config.timeline_from_year
        and config.timeline_to_year
        and config.timeline_from_year <= candidate.year <= config.timeline_to_year
    ):
        year_bonus = W_YEAR

    total = (
        title_score
        + abstract_score
        + rq_score
        + hint_score
        + source_bonus
        + identifier_bonus
        + pdf_bonus
        + year_bonus
    )
    return round(min(total, 1.0), 4)


def _terms(text: str) -> Set[str]:
    tokens = re.findall(r"[a-z]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def _overlap(candidate_terms: Set[str], query_terms: Set[str]) -> float:
    if not query_terms:
        return 0.0
    return len(candidate_terms & query_terms) / len(query_terms)
