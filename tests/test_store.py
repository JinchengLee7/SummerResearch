"""Tests for app/state/store.py — make_paper_id, load/save, persist."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.state.schemas import PaperCandidate, PaperIdentifiers
from app.state.store import (
    candidate_to_dict,
    _dict_to_candidate,
    make_paper_id,
)


def _paper(**kwargs) -> PaperCandidate:
    defaults = dict(
        title="Test Paper",
        authors=["Alice"],
        year=2023,
        abstract="An abstract.",
        identifiers=PaperIdentifiers(),
        sources=["arxiv"],
        raw={},
        score=0.5,
    )
    defaults.update(kwargs)
    return PaperCandidate(**defaults)


# ── make_paper_id ──────────────────────────────────────────────────────────

def test_make_paper_id_uses_doi():
    p = _paper(identifiers=PaperIdentifiers(doi="10.1234/test"))
    pid = make_paper_id(p)
    assert pid.startswith("p")
    assert len(pid) == 16  # "p" + 15 hex chars


def test_make_paper_id_prefers_doi_over_arxiv():
    p = _paper(identifiers=PaperIdentifiers(doi="10.1234/x", arxiv_id="2101.00001"))
    pid_doi = make_paper_id(p)
    p2 = _paper(identifiers=PaperIdentifiers(arxiv_id="2101.00001"))
    pid_arxiv = make_paper_id(p2)
    assert pid_doi != pid_arxiv


def test_make_paper_id_falls_back_to_arxiv():
    p = _paper(identifiers=PaperIdentifiers(arxiv_id="2101.00001"))
    pid = make_paper_id(p)
    assert pid.startswith("p")


def test_make_paper_id_falls_back_to_title_year():
    p = _paper(title="Unique Title XYZ", year=2022, identifiers=PaperIdentifiers())
    pid = make_paper_id(p)
    assert pid.startswith("p")


def test_make_paper_id_deterministic():
    p = _paper(title="Reproducible", year=2021, identifiers=PaperIdentifiers(doi="10.x/y"))
    assert make_paper_id(p) == make_paper_id(p)


def test_make_paper_id_different_dois_differ():
    p1 = _paper(identifiers=PaperIdentifiers(doi="10.1/a"))
    p2 = _paper(identifiers=PaperIdentifiers(doi="10.1/b"))
    assert make_paper_id(p1) != make_paper_id(p2)


# ── candidate_to_dict / _dict_to_candidate roundtrip ─────────────────────

def test_candidate_roundtrip():
    p = _paper(
        title="Roundtrip Paper",
        year=2024,
        abstract="Abstract text.",
        identifiers=PaperIdentifiers(doi="10.9/r", arxiv_id="2404.00001"),
        sources=["arxiv", "openalex"],
        score=0.42,
        paper_id="pABC123",
        embedding_score=0.75,
    )
    d = candidate_to_dict(p)
    p2 = _dict_to_candidate(d)

    assert p2.title == p.title
    assert p2.year == p.year
    assert p2.abstract == p.abstract
    assert p2.identifiers.doi == p.identifiers.doi
    assert p2.identifiers.arxiv_id == p.identifiers.arxiv_id
    assert p2.sources == p.sources
    assert p2.score == p.score
    assert p2.paper_id == p.paper_id
    assert p2.embedding_score == p.embedding_score


def test_candidate_to_dict_includes_paper_id():
    p = _paper(paper_id="p123abc")
    d = candidate_to_dict(p)
    assert d["paper_id"] == "p123abc"


def test_candidate_to_dict_includes_embedding_score():
    p = _paper(embedding_score=0.81)
    d = candidate_to_dict(p)
    assert d["embedding_score"] == 0.81


# ── save_papers / load_papers ─────────────────────────────────────────────

def test_save_and_load_papers_roundtrip(tmp_path):
    from app.state import store
    orig_data = store.DATA_DIR

    store.DATA_DIR = tmp_path
    try:
        papers = [
            _paper(title="Paper A", paper_id="pAAA", year=2021),
            _paper(title="Paper B", paper_id="pBBB", year=2022, embedding_score=0.6),
        ]
        store.save_papers(papers)
        loaded = store.load_papers()
        assert len(loaded) == 2
        assert {p.title for p in loaded} == {"Paper A", "Paper B"}
        assert any(p.embedding_score == 0.6 for p in loaded)
    finally:
        store.DATA_DIR = orig_data


def test_save_rejects_roundtrip(tmp_path):
    from app.state import store
    orig = store.DATA_DIR
    store.DATA_DIR = tmp_path
    try:
        rejects = [_paper(title="Bad Paper", rejection_reason="year_out_of_range", paper_id="pR1")]
        store.save_rejects(rejects)
        loaded = store.load_rejects()
        assert len(loaded) == 1
        assert loaded[0].rejection_reason == "year_out_of_range"
    finally:
        store.DATA_DIR = orig


def test_load_papers_returns_empty_when_missing(tmp_path):
    from app.state import store
    orig = store.DATA_DIR
    store.DATA_DIR = tmp_path
    try:
        result = store.load_papers()
        assert result == []
    finally:
        store.DATA_DIR = orig


def test_persist_papers_assigns_paper_id(tmp_path):
    from app.state import store
    orig = store.DATA_DIR
    store.DATA_DIR = tmp_path
    try:
        p = _paper(title="No ID Paper", identifiers=PaperIdentifiers(doi="10.99/x"))
        assert p.paper_id is None
        store.persist_papers([p])
        assert p.paper_id is not None
        assert p.paper_id.startswith("p")
    finally:
        store.DATA_DIR = orig
