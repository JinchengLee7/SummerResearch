from app.state.schemas import PaperCandidate, PaperIdentifiers
from app.architectures.baseline.dedupe import deduplicate


def _cand(
    title="Test Paper",
    year=2022,
    doi=None,
    arxiv_id=None,
    oa_id=None,
    s2_id=None,
    authors=None,
    source="arxiv",
    abstract="Abstract text.",
):
    return PaperCandidate(
        title=title,
        authors=authors or ["Smith, J"],
        year=year,
        abstract=abstract,
        identifiers=PaperIdentifiers(
            doi=doi, arxiv_id=arxiv_id, openalex_id=oa_id, semantic_scholar_id=s2_id
        ),
        sources=[source],
        raw={},
    )


def test_doi_deduplication():
    a = _cand(doi="10.1234/test", source="arxiv")
    b = _cand(doi="10.1234/test", source="semantic_scholar")
    unique, _ = deduplicate([a, b])
    assert len(unique) == 1
    assert "semantic_scholar" in unique[0].sources
    assert "arxiv" in unique[0].sources


def test_arxiv_id_deduplication():
    a = _cand(arxiv_id="2301.12345", source="arxiv")
    b = _cand(arxiv_id="2301.12345", source="openalex")
    unique, _ = deduplicate([a, b])
    assert len(unique) == 1


def test_openalex_id_deduplication():
    a = _cand(oa_id="W1234567", source="arxiv")
    b = _cand(oa_id="W1234567", source="openalex")
    unique, _ = deduplicate([a, b])
    assert len(unique) == 1


def test_fingerprint_deduplication():
    a = _cand(title="Neural Networks for Code", year=2022, authors=["Smith, John"])
    b = _cand(title="Neural Networks for Code", year=2022, authors=["Smith, John"])
    unique, _ = deduplicate([a, b])
    assert len(unique) == 1


def test_no_false_dedup_different_arxiv():
    a = _cand(arxiv_id="2301.00001")
    b = _cand(arxiv_id="2301.00002", title="Different Paper")
    unique, _ = deduplicate([a, b])
    assert len(unique) == 2


def test_merge_fills_missing_abstract():
    a = _cand(arxiv_id="2301.99999", abstract=None)
    b = _cand(arxiv_id="2301.99999", abstract="Filled abstract")
    unique, _ = deduplicate([a, b])
    assert unique[0].abstract == "Filled abstract"


def test_merge_fills_missing_doi():
    a = _cand(arxiv_id="2301.99998", doi=None)
    b = _cand(arxiv_id="2301.99998", doi="10.9999/x")
    unique, _ = deduplicate([a, b])
    assert unique[0].identifiers.doi == "10.9999/x"


def test_merge_preserves_pdf_url():
    a = _cand(arxiv_id="2301.99997")
    a.pdf_url = None
    b = _cand(arxiv_id="2301.99997")
    b.pdf_url = "https://example.com/paper.pdf"
    unique, _ = deduplicate([a, b])
    assert unique[0].pdf_url == "https://example.com/paper.pdf"


def test_empty_list():
    unique, _ = deduplicate([])
    assert unique == []


def test_single_candidate_passthrough():
    c = _cand(doi="10.x/y")
    unique, _ = deduplicate([c])
    assert len(unique) == 1
