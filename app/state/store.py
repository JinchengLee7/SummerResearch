import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from app.state.schemas import ManagerRunResult, PaperCandidate

DATA_DIR = Path("data")
SITE_DATA_DIR = Path("site/data")


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _candidate_to_dict(c: PaperCandidate) -> dict:
    return {
        "title": c.title,
        "authors": c.authors,
        "year": c.year,
        "abstract": c.abstract,
        "url": c.url,
        "pdf_url": c.pdf_url,
        "identifiers": {
            "doi": c.identifiers.doi,
            "arxiv_id": c.identifiers.arxiv_id,
            "openalex_id": c.identifiers.openalex_id,
            "semantic_scholar_id": c.identifiers.semantic_scholar_id,
        },
        "sources": c.sources,
        "score": c.score,
        "rejection_reason": c.rejection_reason,
    }


def _read_ndjson(path: Path) -> List[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _write_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def persist_papers(papers: List[PaperCandidate], dry_run: bool = False) -> None:
    if dry_run:
        return
    _ensure_dirs()
    with open(DATA_DIR / "papers.ndjson", "a", encoding="utf-8") as f:
        for p in papers:
            f.write(json.dumps(_candidate_to_dict(p)) + "\n")


def persist_rejects(rejects: List[PaperCandidate], dry_run: bool = False) -> None:
    if dry_run:
        return
    _ensure_dirs()
    with open(DATA_DIR / "rejects.ndjson", "a", encoding="utf-8") as f:
        for r in rejects:
            f.write(json.dumps(_candidate_to_dict(r)) + "\n")


def persist_run_history(result: ManagerRunResult, dry_run: bool = False) -> None:
    if dry_run:
        return
    _ensure_dirs()
    record = {
        "architecture": result.architecture,
        "queries_generated": result.queries_generated,
        "sources_queried": result.sources_queried,
        "candidates_found": result.candidates_found,
        "candidates_after_dedupe": result.candidates_after_dedupe,
        "papers_accepted": result.papers_accepted,
        "candidates_rejected": result.candidates_rejected,
        "dry_run": result.dry_run,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "errors": result.errors,
    }
    with open(DATA_DIR / "run_history.ndjson", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def update_changelog(
    result: ManagerRunResult, papers: List[PaperCandidate], dry_run: bool = False
) -> None:
    if dry_run:
        return
    _ensure_dirs()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"\n## {timestamp} — {result.architecture}\n\n",
        f"- Queries generated: {result.queries_generated}\n",
        f"- Candidates found: {result.candidates_found}\n",
        f"- After deduplication: {result.candidates_after_dedupe}\n",
        f"- Accepted: {result.papers_accepted}\n",
        f"- Rejected: {result.candidates_rejected}\n",
    ]
    if papers:
        lines.append("\n### Accepted papers\n\n")
        for p in papers[:20]:
            lines.append(f"- {p.title} ({p.year}) — score {p.score:.3f}\n")
    with open(DATA_DIR / "changelog.md", "a", encoding="utf-8") as f:
        f.writelines(lines)


def publish_site_data(
    papers: List[PaperCandidate],
    rejects: List[PaperCandidate],
    result: ManagerRunResult,
    survey_config_raw: dict,
    dry_run: bool = False,
) -> None:
    if dry_run:
        return
    _ensure_dirs()

    all_papers = _read_ndjson(DATA_DIR / "papers.ndjson")
    all_rejects = _read_ndjson(DATA_DIR / "rejects.ndjson")
    history = _read_ndjson(DATA_DIR / "run_history.ndjson")

    _write_json(SITE_DATA_DIR / "papers.json", all_papers)
    _write_json(SITE_DATA_DIR / "rejects.json", all_rejects)
    _write_json(SITE_DATA_DIR / "run_history.json", history)
    _write_json(SITE_DATA_DIR / "survey_config.json", survey_config_raw)
    _write_json(
        SITE_DATA_DIR / "system_status.json",
        {
            "last_run": result.finished_at,
            "architecture": result.architecture,
            "papers_accepted": result.papers_accepted,
            "candidates_rejected": result.candidates_rejected,
            "total_papers": len(all_papers),
        },
    )

    cl_src = DATA_DIR / "changelog.md"
    if cl_src.exists():
        (SITE_DATA_DIR / "changelog.md").write_text(
            cl_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
