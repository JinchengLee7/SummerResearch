import pytest
from app.state.schemas import SurveyConfig
from app.architectures.baseline.query_builder import build_queries, MAX_QUERIES


def _cfg(**kw):
    defaults = dict(
        topic_overview="machine learning for code review",
        research_questions=["How does LLM help code review?"],
        question_context="",
        query_hints=["automated review", "neural networks"],
        timeline_from_year=2020,
        timeline_to_year=2024,
        min_relevance_score=0.1,
    )
    defaults.update(kw)
    return SurveyConfig(**defaults)


def test_topic_overview_in_queries():
    queries = build_queries(_cfg(topic_overview="neural networks"))
    assert "neural networks" in queries


def test_research_questions_in_queries():
    queries = build_queries(_cfg(research_questions=["What is transfer learning?"]))
    assert "What is transfer learning?" in queries


def test_query_hints_in_queries():
    queries = build_queries(_cfg(query_hints=["transformers", "BERT"]))
    assert "transformers" in queries
    assert "BERT" in queries


def test_combined_queries_generated():
    cfg = _cfg(topic_overview="topic", query_hints=["hint"])
    queries = build_queries(cfg)
    assert "topic hint" in queries


def test_no_duplicates():
    cfg = _cfg(
        topic_overview="code review",
        research_questions=["code review"],
        query_hints=[],
    )
    queries = build_queries(cfg)
    assert queries.count("code review") == 1


def test_empty_config_returns_empty():
    cfg = SurveyConfig(topic_overview="", research_questions=[], query_hints=[])
    assert build_queries(cfg) == []


def test_max_queries_enforced():
    cfg = SurveyConfig(
        topic_overview="topic",
        research_questions=[f"question {i}" for i in range(100)],
        query_hints=[],
    )
    assert len(build_queries(cfg)) <= MAX_QUERIES


def test_whitespace_only_entries_ignored():
    cfg = _cfg(research_questions=["  ", "\t"], query_hints=["  "])
    queries = build_queries(cfg)
    assert all(q.strip() for q in queries)
