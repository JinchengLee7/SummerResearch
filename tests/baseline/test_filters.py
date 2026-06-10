from app.state.schemas import PaperCandidate, PaperIdentifiers, SurveyConfig
from app.architectures.baseline.filters import apply_filters


def _cfg(year_from=2020, year_to=2024, min_score=0.1):
    return SurveyConfig(
        topic_overview="test topic",
        timeline_from_year=year_from,
        timeline_to_year=year_to,
        min_relevance_score=min_score,
    )


def _cand(title="Test Paper", year=2022, s=0.5):
    c = PaperCandidate(
        title=title,
        authors=["Author"],
        year=year,
        identifiers=PaperIdentifiers(),
        sources=["arxiv"],
        raw={},
    )
    c.score = s
    return c


def test_valid_candidate_accepted():
    accepted, rejected = apply_filters([_cand()], _cfg())
    assert len(accepted) == 1 and len(rejected) == 0


def test_year_too_early_rejected():
    _, rejected = apply_filters([_cand(year=2015)], _cfg(year_from=2020))
    assert len(rejected) == 1
    assert rejected[0].rejection_reason == "year_out_of_range"


def test_year_too_late_rejected():
    _, rejected = apply_filters([_cand(year=2030)], _cfg(year_to=2024))
    assert len(rejected) == 1
    assert rejected[0].rejection_reason == "year_out_of_range"


def test_below_threshold_rejected():
    _, rejected = apply_filters([_cand(s=0.01)], _cfg(min_score=0.1))
    assert len(rejected) == 1
    assert rejected[0].rejection_reason == "below_relevance_threshold"


def test_missing_title_rejected():
    _, rejected = apply_filters([_cand(title="")], _cfg())
    assert len(rejected) == 1
    assert rejected[0].rejection_reason == "missing_title"


def test_whitespace_title_rejected():
    _, rejected = apply_filters([_cand(title="   ")], _cfg())
    assert rejected[0].rejection_reason == "missing_title"


def test_missing_title_checked_first():
    # Even if year is out of range, missing_title takes priority
    _, rejected = apply_filters([_cand(title="", year=2015)], _cfg())
    assert rejected[0].rejection_reason == "missing_title"


def test_mixed_batch():
    candidates = [
        _cand(year=2015, s=0.5),   # year_out_of_range
        _cand(s=0.01),             # below_relevance_threshold
        _cand(title=""),           # missing_title
        _cand(year=2022, s=0.5),   # accepted
    ]
    accepted, rejected = apply_filters(candidates, _cfg())
    assert len(accepted) == 1
    assert len(rejected) == 3
    reasons = {r.rejection_reason for r in rejected}
    assert reasons == {"year_out_of_range", "below_relevance_threshold", "missing_title"}


def test_no_year_limits_accepts_any_year():
    cfg = SurveyConfig(topic_overview="t", min_relevance_score=0.0)
    accepted, _ = apply_filters([_cand(year=1990), _cand(year=2050)], cfg)
    assert len(accepted) == 2
