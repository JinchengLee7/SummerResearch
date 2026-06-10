"""Tests for app/embeddings/segmenter.py."""
import pytest

from app.embeddings.segmenter import segment_paper
from app.state.schemas import PaperCandidate, PaperIdentifiers


def _paper(title="", abstract=None) -> PaperCandidate:
    return PaperCandidate(
        title=title,
        abstract=abstract,
        identifiers=PaperIdentifiers(),
        sources=[],
        raw={},
    )


def test_title_always_included():
    p = _paper(title="Large Language Models for Code Review")
    segs = segment_paper(p)
    assert segs[0] == "Large Language Models for Code Review"


def test_abstract_split_into_sentences():
    p = _paper(
        title="Intro",
        abstract=(
            "This is the first long sentence in the abstract. "
            "This is the second long sentence in the abstract. "
            "This is the third long sentence in the abstract."
        ),
    )
    segs = segment_paper(p)
    assert len(segs) >= 3  # title + at least 2 sentences (each >25 chars)


def test_short_segments_excluded():
    p = _paper(title="T", abstract="Short. This is a long enough sentence to pass the filter.")
    segs = segment_paper(p)
    assert not any(s == "Short." for s in segs)
    assert any("long enough" in s for s in segs)


def test_empty_abstract_returns_title_only():
    p = _paper(title="Only Title Here")
    segs = segment_paper(p)
    assert segs == ["Only Title Here"]


def test_no_title_no_abstract_returns_empty():
    p = _paper(title="", abstract=None)
    segs = segment_paper(p)
    assert segs == []


def test_whitespace_title_excluded():
    p = _paper(title="   ", abstract="This is a valid abstract sentence that passes.")
    segs = segment_paper(p)
    assert not any(s.strip() == "" for s in segs)


def test_segments_are_strings():
    p = _paper(title="Test", abstract="First sentence here. Second sentence here.")
    segs = segment_paper(p)
    assert all(isinstance(s, str) for s in segs)
