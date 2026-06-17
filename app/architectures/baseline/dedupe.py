import re
from typing import Dict, List, Optional, Tuple

from app.state.schemas import PaperCandidate


class IncrementalDeduplicator:
    """
    Stateful deduplicator for use across multiple search batches.

    Unlike the batch ``deduplicate()`` function, this class maintains its
    index across calls to ``add_batch()``, so the outer search loop can
    measure the new-paper yield rate after each query and detect saturation
    without waiting until all queries have finished.
    """

    def __init__(self) -> None:
        self._by_doi: Dict[str, int] = {}
        self._by_arxiv: Dict[str, int] = {}
        self._by_openalex: Dict[str, int] = {}
        self._by_s2: Dict[str, int] = {}
        self._by_fp: Dict[str, int] = {}
        self._unique: List[PaperCandidate] = []

    @property
    def unique(self) -> List[PaperCandidate]:
        return list(self._unique)

    def __len__(self) -> int:
        return len(self._unique)

    def add_batch(self, candidates: List[PaperCandidate]) -> int:
        """
        Add a batch of candidates.  Duplicates are merged into the existing
        record in place.  Returns the count of *genuinely new* papers added.
        """
        new = 0
        for c in candidates:
            new += self._add_one(c)
        return new

    def _add_one(self, candidate: PaperCandidate) -> int:
        ids = candidate.identifiers
        existing: Optional[int] = None

        if ids.doi:
            existing = self._by_doi.get(ids.doi)
        if existing is None and ids.arxiv_id:
            existing = self._by_arxiv.get(ids.arxiv_id)
        if existing is None and ids.openalex_id:
            existing = self._by_openalex.get(ids.openalex_id)
        if existing is None and ids.semantic_scholar_id:
            existing = self._by_s2.get(ids.semantic_scholar_id)

        fp = _fingerprint(candidate)
        if existing is None and fp:
            existing = self._by_fp.get(fp)

        if existing is not None:
            _merge(self._unique[existing], candidate)
            return 0

        idx = len(self._unique)
        self._unique.append(candidate)
        if ids.doi:
            self._by_doi[ids.doi] = idx
        if ids.arxiv_id:
            self._by_arxiv[ids.arxiv_id] = idx
        if ids.openalex_id:
            self._by_openalex[ids.openalex_id] = idx
        if ids.semantic_scholar_id:
            self._by_s2[ids.semantic_scholar_id] = idx
        if fp:
            self._by_fp[fp] = idx
        return 1


def deduplicate(
    candidates: List[PaperCandidate],
) -> Tuple[List[PaperCandidate], List[PaperCandidate]]:
    """
    Merge duplicates using priority order:
      1. DOI
      2. arXiv ID
      3. OpenAlex ID
      4. Semantic Scholar ID
      5. normalized title + year + first-author fingerprint

    Returns (unique_candidates, []) — duplicates are merged into the primary
    record and not sent to the reject list (they are not bad papers, just
    the same paper seen twice).
    """
    by_doi: Dict[str, int] = {}
    by_arxiv: Dict[str, int] = {}
    by_openalex: Dict[str, int] = {}
    by_s2: Dict[str, int] = {}
    by_fingerprint: Dict[str, int] = {}

    unique: List[PaperCandidate] = []

    for candidate in candidates:
        ids = candidate.identifiers
        existing: Optional[int] = None

        if ids.doi:
            existing = by_doi.get(ids.doi)
        if existing is None and ids.arxiv_id:
            existing = by_arxiv.get(ids.arxiv_id)
        if existing is None and ids.openalex_id:
            existing = by_openalex.get(ids.openalex_id)
        if existing is None and ids.semantic_scholar_id:
            existing = by_s2.get(ids.semantic_scholar_id)

        fp = _fingerprint(candidate)
        if existing is None and fp:
            existing = by_fingerprint.get(fp)

        if existing is not None:
            _merge(unique[existing], candidate)
        else:
            idx = len(unique)
            unique.append(candidate)
            if ids.doi:
                by_doi[ids.doi] = idx
            if ids.arxiv_id:
                by_arxiv[ids.arxiv_id] = idx
            if ids.openalex_id:
                by_openalex[ids.openalex_id] = idx
            if ids.semantic_scholar_id:
                by_s2[ids.semantic_scholar_id] = idx
            if fp:
                by_fingerprint[fp] = idx

    return unique, []


def _fingerprint(c: PaperCandidate) -> Optional[str]:
    title = re.sub(r"[^a-z0-9 ]", "", (c.title or "").lower())
    title = re.sub(r"\s+", " ", title).strip()[:80]
    year = str(c.year) if c.year else ""
    first_author = ""
    if c.authors:
        parts = c.authors[0].split()
        if parts:
            first_author = re.sub(r"[^a-z]", "", parts[-1].lower())
    if not title:
        return None
    return f"{title}|{year}|{first_author}"


def _merge(target: PaperCandidate, source: PaperCandidate) -> None:
    for s in source.sources:
        if s not in target.sources:
            target.sources.append(s)

    ids_t, ids_s = target.identifiers, source.identifiers
    if not ids_t.doi and ids_s.doi:
        ids_t.doi = ids_s.doi
    if not ids_t.arxiv_id and ids_s.arxiv_id:
        ids_t.arxiv_id = ids_s.arxiv_id
    if not ids_t.openalex_id and ids_s.openalex_id:
        ids_t.openalex_id = ids_s.openalex_id
    if not ids_t.semantic_scholar_id and ids_s.semantic_scholar_id:
        ids_t.semantic_scholar_id = ids_s.semantic_scholar_id

    if not target.abstract and source.abstract:
        target.abstract = source.abstract
    if not target.url and source.url:
        target.url = source.url
    if not target.pdf_url and source.pdf_url:
        target.pdf_url = source.pdf_url

    target.raw.update(source.raw)
