import json
import logging
import time
import urllib.parse
import urllib.request
from typing import List, Optional

from app.state.schemas import PaperCandidate, PaperIdentifiers

logger = logging.getLogger(__name__)

_API = "https://api.openalex.org/works"
_SELECT = "id,title,authorships,publication_year,abstract_inverted_index,doi,primary_location,open_access,ids"
_DEFAULT_MAX = 25
_RETRY_DELAY = 1.0


def search(
    query: str,
    max_results: int = _DEFAULT_MAX,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[PaperCandidate]:
    # OpenAlex returns 400 on question-form queries containing "?"
    oa_query = query.replace("?", "").strip()

    params: dict = {
        "search": oa_query,
        "per-page": min(max_results, 200),
        "select": _SELECT,
        "mailto": "dynamic-lr@example.com",
    }

    filters = []
    if year_from and year_to:
        filters.append(f"publication_year:{year_from}-{year_to}")
    elif year_from:
        filters.append(f"publication_year:>{year_from - 1}")
    elif year_to:
        filters.append(f"publication_year:<{year_to + 1}")
    if filters:
        params["filter"] = ",".join(filters)

    url = f"{_API}?{urllib.parse.urlencode(params)}"
    logger.info("OpenAlex search: %.60s", query)

    data: Optional[dict] = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dynamic-lr/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            break
        except Exception as exc:
            logger.warning("OpenAlex attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(_RETRY_DELAY)
            else:
                logger.error("OpenAlex search failed for query %r: %s", query, exc)
                return []

    results = []
    for item in (data or {}).get("results", []):
        try:
            c = _parse_item(item)
            if c:
                results.append(c)
        except Exception as exc:
            logger.warning("Skipping malformed OpenAlex record: %s", exc)
    return results


def _reconstruct_abstract(inverted_index: Optional[dict]) -> Optional[str]:
    if not inverted_index:
        return None
    word_pos = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_pos.append((pos, word))
    word_pos.sort()
    return " ".join(w for _, w in word_pos)


def _parse_item(item: dict) -> Optional[PaperCandidate]:
    title = (item.get("title") or "").strip()
    if not title:
        return None

    year: Optional[int] = item.get("publication_year")

    authors = []
    for auth in item.get("authorships") or []:
        name = (auth.get("author") or {}).get("display_name", "")
        if name:
            authors.append(name)

    abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

    raw_doi = item.get("doi") or ""
    doi = raw_doi.replace("https://doi.org/", "").strip() or None

    oa_id = (item.get("id") or "").replace("https://openalex.org/", "").strip() or None

    ids = item.get("ids") or {}
    arxiv_raw = ids.get("arxiv", "")
    arxiv_id = (
        arxiv_raw.replace("https://arxiv.org/abs/", "").strip() or None
        if arxiv_raw
        else None
    )

    primary = item.get("primary_location") or {}
    url: Optional[str] = primary.get("landing_page_url") or (
        f"https://doi.org/{doi}" if doi else None
    )

    oa = item.get("open_access") or {}
    pdf_url: Optional[str] = oa.get("oa_url")

    return PaperCandidate(
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        url=url,
        pdf_url=pdf_url,
        identifiers=PaperIdentifiers(doi=doi, arxiv_id=arxiv_id, openalex_id=oa_id),
        sources=["openalex"],
        raw={"openalex": item},
    )
