import json
import logging
import time
import urllib.parse
import urllib.request
from typing import List, Optional

from app.state.schemas import PaperCandidate, PaperIdentifiers

logger = logging.getLogger(__name__)

_API = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,authors,year,abstract,externalIds,openAccessPdf,url"
_DEFAULT_MAX = 25
_RETRY_DELAY = 2.0
# Free-tier rate limit: 1 req/s without API key.
_RATE_SLEEP = 1.1


def search(
    query: str,
    max_results: int = _DEFAULT_MAX,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[PaperCandidate]:
    params = urllib.parse.urlencode(
        {"query": query, "fields": _FIELDS, "limit": min(max_results, 100)}
    )
    url = f"{_API}?{params}"
    logger.info("Semantic Scholar search: %.60s", query)

    data: Optional[dict] = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dynamic-lr/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            time.sleep(_RATE_SLEEP)
            break
        except Exception as exc:
            logger.warning("S2 attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(_RETRY_DELAY)
            else:
                logger.error("S2 search failed for query %r: %s", query, exc)
                return []

    results = []
    for item in (data or {}).get("data", []):
        try:
            c = _parse_item(item, year_from, year_to)
            if c:
                results.append(c)
        except Exception as exc:
            logger.warning("Skipping malformed S2 record: %s", exc)
    return results


def _parse_item(
    item: dict, year_from: Optional[int], year_to: Optional[int]
) -> Optional[PaperCandidate]:
    title = (item.get("title") or "").strip()
    if not title:
        return None

    year: Optional[int] = item.get("year")
    if year_from and year and year < year_from:
        return None
    if year_to and year and year > year_to:
        return None

    authors = [
        a.get("name", "") for a in (item.get("authors") or []) if a.get("name")
    ]
    abstract = (item.get("abstract") or "").strip() or None

    ext = item.get("externalIds") or {}
    doi = ext.get("DOI")
    arxiv_id = ext.get("ArXiv")
    s2_id: Optional[str] = item.get("paperId")

    oa = item.get("openAccessPdf") or {}
    pdf_url: Optional[str] = oa.get("url")
    url: Optional[str] = item.get("url") or (
        f"https://www.semanticscholar.org/paper/{s2_id}" if s2_id else None
    )

    return PaperCandidate(
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        url=url,
        pdf_url=pdf_url,
        identifiers=PaperIdentifiers(doi=doi, arxiv_id=arxiv_id, semantic_scholar_id=s2_id),
        sources=["semantic_scholar"],
        raw={"semantic_scholar": item},
    )
