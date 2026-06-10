"""Tests for Embedder.max_sim (static method — no real model loaded)."""
import numpy as np
import pytest

from app.embeddings.embedder import Embedder


def _vec(*values) -> np.ndarray:
    return np.array([values], dtype=np.float32)


def test_max_sim_identical_unit_vectors():
    v = _vec(1.0, 0.0, 0.0)
    score = Embedder.max_sim(v, v)
    assert abs(score - 1.0) < 1e-4  # cosine=1 → (1+1)/2 = 1.0


def test_max_sim_orthogonal_vectors():
    a = _vec(1.0, 0.0, 0.0)
    b = _vec(0.0, 1.0, 0.0)
    score = Embedder.max_sim(a, b)
    assert abs(score - 0.5) < 1e-4  # cosine=0 → (0+1)/2 = 0.5


def test_max_sim_opposite_vectors():
    a = _vec(1.0, 0.0, 0.0)
    b = _vec(-1.0, 0.0, 0.0)
    score = Embedder.max_sim(a, b)
    assert abs(score - 0.0) < 1e-4  # cosine=-1 → (-1+1)/2 = 0.0


def test_max_sim_takes_max_over_segments():
    paper_vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    query_vecs = np.array([[1.0, 0.0]], dtype=np.float32)  # matches first seg only
    score = Embedder.max_sim(paper_vecs, query_vecs)
    assert score > 0.9  # best cosine is 1.0 → score ≈ 1.0


def test_max_sim_empty_paper_vecs():
    empty = np.zeros((0, 3), dtype=np.float32)
    query = _vec(1.0, 0.0, 0.0)
    assert Embedder.max_sim(empty, query) == 0.0


def test_max_sim_empty_query_vecs():
    paper = _vec(1.0, 0.0, 0.0)
    empty = np.zeros((0, 3), dtype=np.float32)
    assert Embedder.max_sim(paper, empty) == 0.0


def test_max_sim_output_in_range():
    rng = np.random.default_rng(42)
    a = rng.standard_normal((5, 16)).astype(np.float32)
    b = rng.standard_normal((3, 16)).astype(np.float32)
    score = Embedder.max_sim(a, b)
    assert 0.0 <= score <= 1.0


def test_max_sim_non_unit_vectors_normalised():
    a = _vec(3.0, 0.0, 0.0)  # not unit length
    b = _vec(5.0, 0.0, 0.0)
    score = Embedder.max_sim(a, b)
    assert abs(score - 1.0) < 1e-4  # same direction → cosine=1
