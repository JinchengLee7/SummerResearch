from typing import List, Tuple

from app.state.schemas import PaperCandidate, SurveyConfig


def apply_filters(
    candidates: List[PaperCandidate],
    config: SurveyConfig,
) -> Tuple[List[PaperCandidate], List[PaperCandidate]]:
    """
    Apply fixed rejection rules.  Returns (accepted, rejected).
    Every rejected candidate has a rejection_reason set.

    Rules (checked in this order):
      missing_title           — title is absent or blank
      year_out_of_range       — year outside timeline_from/to
      below_relevance_threshold — score < min_relevance_score
    """
    accepted: List[PaperCandidate] = []
    rejected: List[PaperCandidate] = []

    for c in candidates:
        reason = _reject_reason(c, config)
        if reason:
            c.rejection_reason = reason
            rejected.append(c)
        else:
            accepted.append(c)

    return accepted, rejected


def _reject_reason(c: PaperCandidate, config: SurveyConfig) -> str:
    if not (c.title or "").strip():
        return "missing_title"

    if c.year is not None:
        if config.timeline_from_year and c.year < config.timeline_from_year:
            return "year_out_of_range"
        if config.timeline_to_year and c.year > config.timeline_to_year:
            return "year_out_of_range"

    if c.score < config.min_relevance_score:
        return "below_relevance_threshold"

    return ""
