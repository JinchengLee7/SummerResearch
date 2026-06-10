import logging
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Optional

from app.state.schemas import PaperCandidate, PaperIdentifiers

logger = logging.getLogger(__name__)

_API = "http://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
_DEFAULT_MAX = 25
_RETRY_DELAY = 3.0


def search(
    query: str,
    max_results: int = _DEFAULT_MAX,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[PaperCandidate]:
    params = urllib.parse.urlencode(
        {"search_query": f"all:{query}", "start": 0, "max_results": max_results}
    )
    url = f"{_API}?{params}"
    logger.info("arXiv search: %.60s", query)

    xml_data: Optional[bytes] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                xml_data = resp.read()
            break
        except Exception as exc:
            logger.warning("arXiv attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(_RETRY_DELAY)
            else:
                logger.error("arXiv search failed for query %r: %s", query, exc)
                return []

    return _parse_feed(xml_data, year_from, year_to)


def _parse_feed(
    xml_data: bytes, year_from: Optional[int], year_to: Optional[int]
) -> List[PaperCandidate]:
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        logger.error("arXiv XML parse error: %s", exc)
        return []

    results = []
    for entry in root.findall("atom:entry", _NS):
        try:
            candidate = _parse_entry(entry, year_from, year_to)
            if candidate:
                results.append(candidate)
        except Exception as exc:
            logger.warning("Skipping malformed arXiv entry: %s", exc)
    return results


def _parse_entry(
    entry: ET.Element, year_from: Optional[int], year_to: Optional[int]
) -> Optional[PaperCandidate]:
    title_el = entry.find("atom:title", _NS)
    title = (
        title_el.text.strip().replace("\n", " ")
        if title_el is not None and title_el.text
        else ""
    )
    if not title:
        return None

    abstract_el = entry.find("atom:summary", _NS)
    abstract = (
        abstract_el.text.strip().replace("\n", " ")
        if abstract_el is not None and abstract_el.text
        else None
    )

    published_el = entry.find("atom:published", _NS)
    year: Optional[int] = None
    if published_el is not None and published_el.text:
        try:
            year = int(published_el.text[:4])
        except ValueError:
            pass

    if year_from and year and year < year_from:
        return None
    if year_to and year and year > year_to:
        return None

    authors = []
    for author_el in entry.findall("atom:author", _NS):
        name_el = author_el.find("atom:name", _NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    id_el = entry.find("atom:id", _NS)
    arxiv_url = id_el.text.strip() if id_el is not None and id_el.text else None
    arxiv_id = None
    if arxiv_url and "/abs/" in arxiv_url:
        arxiv_id = arxiv_url.split("/abs/")[-1]

    pdf_url: Optional[str] = None
    for link in entry.findall("atom:link", _NS):
        if link.get("type") == "application/pdf":
            pdf_url = link.get("href")
            break
    if not pdf_url and arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    doi_el = entry.find("arxiv:doi", _NS)
    doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

    return PaperCandidate(
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        url=arxiv_url,
        pdf_url=pdf_url,
        identifiers=PaperIdentifiers(doi=doi, arxiv_id=arxiv_id),
        sources=["arxiv"],
        raw={"arxiv": {"id": arxiv_url, "title": title}},
    )
