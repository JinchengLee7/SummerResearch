from app.state.schemas import PaperCandidate, PaperIdentifiers, SurveyConfig
from app.architectures.baseline.scorer import score


def _cfg():
    return SurveyConfig(
        topic_overview="machine learning code review",
        research_questions=["How does machine learning improve code review?"],
        query_hints=["automated review", "neural networks"],
        timeline_from_year=2020,
        timeline_to_year=2024,
    )


def _cand(title="", abstract="", year=2022, sources=None, doi=None, pdf_url=None):
    c = PaperCandidate(
        title=title,
        authors=["Author A"],
        year=year,
        abstract=abstract,
        pdf_url=pdf_url,
        identifiers=PaperIdentifiers(doi=doi),
        sources=sources or ["arxiv"],
        raw={},
    )
    return c


def test_relevant_paper_scores_higher():
    high = _cand(
        title="Machine Learning for Code Review",
        abstract="We study how machine learning helps automated code review with neural networks",
    )
    low = _cand(title="Photosynthesis in Plants", abstract="Chlorophyll absorbs light.")
    assert score(high, _cfg()) > score(low, _cfg())


def test_low_relevance_near_zero():
    c = _cand(title="Biology and Plants", abstract="Photosynthesis and chlorophyll.")
    assert score(c, _cfg()) < 0.15


def test_deterministic():
    c = _cand(title="Machine Learning for Code Review", abstract="abstract text")
    cfg = _cfg()
    assert score(c, cfg) == score(c, cfg)


def test_pdf_bonus_applied():
    c1 = _cand(title="machine learning review", pdf_url=None)
    c2 = _cand(title="machine learning review", pdf_url="https://example.com/p.pdf")
    assert score(c2, _cfg()) > score(c1, _cfg())


def test_multi_source_bonus():
    c1 = _cand(title="machine learning review", sources=["arxiv"])
    c2 = _cand(title="machine learning review", sources=["arxiv", "semantic_scholar"])
    assert score(c2, _cfg()) > score(c1, _cfg())


def test_in_range_year_bonus():
    c_in = _cand(title="machine learning code", year=2022)
    c_out = _cand(title="machine learning code", year=2010)
    assert score(c_in, _cfg()) > score(c_out, _cfg())


def test_score_capped_at_one():
    c = _cand(
        title="machine learning code review neural networks automated",
        abstract="machine learning code review neural networks automated review",
        year=2022,
        sources=["arxiv", "semantic_scholar", "openalex"],
        doi="10.x/y",
        pdf_url="https://example.com/p.pdf",
    )
    c.identifiers.arxiv_id = "2301.00001"
    c.identifiers.openalex_id = "W999"
    c.identifiers.semantic_scholar_id = "abc"
    assert score(c, _cfg()) <= 1.0


def test_empty_candidate_scores_low():
    c = _cand(title="", abstract="")
    assert score(c, _cfg()) < 0.1
