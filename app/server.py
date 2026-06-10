"""
app/server.py — Flask API server for Dynamic-LR

Startup (synchronous, before accepting requests):
  1. Load fastembed model
  2. Load survey config → embed query segments
  3. Load papers + rejects from NDJSON
  4. Assign paper_id to any record missing one
  5. Batch-embed all papers → in-memory EmbeddingIndex
  6. Compute embedding_score for every paper and reject
  7. Write updated records back to NDJSON + refresh site/data

Run:
  python -m app.server [--port 8000] [--host 127.0.0.1]
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from flask import Flask, jsonify, request, send_from_directory

from app.architectures.baseline.dedupe import deduplicate
from app.architectures.baseline.scorer import score as keyword_score
from app.embeddings.embedder import Embedder
from app.embeddings.index import EmbeddingIndex
from app.sources import arxiv as src_arxiv
from app.sources import openalexapi as src_oa
from app.sources import semantic_scholar as src_s2
from app.state import store
from app.state.schemas import PaperCandidate, PaperIdentifiers, SurveyConfig
from app.state.store import (
    candidate_to_dict,
    load_papers,
    load_rejects,
    make_paper_id,
    save_papers,
    save_rejects,
)

logger = logging.getLogger(__name__)

SITE_DIR = Path(__file__).parent.parent / "site"
DATA_DIR = Path("data")

app = Flask(__name__)

# ── In-memory state (populated during startup) ─────────────────────────────
_papers: List[PaperCandidate] = []
_rejects: List[PaperCandidate] = []
_index: EmbeddingIndex = EmbeddingIndex()
_embedder: Optional[Embedder] = None
_config: Optional[SurveyConfig] = None


def _load_config() -> SurveyConfig:
    path = DATA_DIR / "survey_config.json"
    if not path.exists():
        path = Path("site/data/survey_config.json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return SurveyConfig(
        topic_overview=raw.get("topic_overview", ""),
        research_questions=raw.get("research_questions", []),
        question_context=raw.get("question_context", ""),
        query_hints=raw.get("query_hints", []),
        timeline_from_year=raw.get("timeline_from_year"),
        timeline_to_year=raw.get("timeline_to_year"),
        min_relevance_score=float(raw.get("min_relevance_score", 0.0)),
    ), raw


def _startup() -> None:
    global _papers, _rejects, _config, _embedder

    logger.info("Step 1/7: Loading fastembed model (BAAI/bge-small-en-v1.5)…")
    _embedder = Embedder()

    logger.info("Step 2/7: Loading survey config…")
    _config, config_raw = _load_config()

    logger.info("Step 3/7: Loading papers and rejects…")
    _papers = load_papers()
    _rejects = load_rejects()
    logger.info("  %d papers, %d rejects", len(_papers), len(_rejects))

    logger.info("Step 4/7: Assigning missing paper_ids…")
    for p in _papers + _rejects:
        if not p.paper_id:
            p.paper_id = make_paper_id(p)

    logger.info("Step 5-6/7: Building embedding index and scoring…")
    _index.build(_papers, _config, _embedder)

    # Also score rejects (they weren't included in build)
    for p in _rejects:
        if p.paper_id not in _index.scores:
            score = _index.add_paper(p, _embedder)
            _index.remove_paper(p.paper_id)  # keep rejects out of search index
            p.embedding_score = round(score, 4)

    for p in _papers:
        p.embedding_score = round(_index.scores.get(p.paper_id, 0.0), 4)

    logger.info("Step 7/7: Persisting updated records and refreshing site data…")
    save_papers(_papers)
    save_rejects(_rejects)

    from app.state.schemas import ManagerRunResult
    dummy = ManagerRunResult(
        architecture="server",
        queries_generated=0,
        sources_queried=[],
        candidates_found=len(_papers),
        candidates_after_dedupe=len(_papers),
        papers_accepted=len(_papers),
        candidates_rejected=len(_rejects),
        dry_run=False,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    store.publish_site_data(_papers, _rejects, dummy, config_raw)
    logger.info("Startup complete. %d papers indexed.", len(_papers))


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(str(SITE_DIR), "index.html")


@app.route("/data/<path:filename>")
def serve_site_data(filename):
    return send_from_directory(str(SITE_DIR / "data"), filename)


@app.route("/api/status")
def api_status():
    return jsonify({
        "index_ready": _embedder is not None,
        "papers": len(_papers),
        "rejects": len(_rejects),
    })


@app.route("/api/papers")
def api_papers():
    return jsonify([candidate_to_dict(p) for p in _papers])


@app.route("/api/rejects")
def api_rejects():
    return jsonify([candidate_to_dict(p) for p in _rejects])


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "q is required"}), 400

    active_sources = set(request.args.get("sources", "arxiv,semantic_scholar,openalex").split(","))

    # Similarity search within existing DB
    db_hits = _index.search(q, _embedder, top_k=10)
    pid_map = {p.paper_id: p for p in _papers}
    db_matches = [
        {**candidate_to_dict(pid_map[pid]), "db_score": round(sc, 4)}
        for pid, sc in db_hits
        if pid in pid_map
    ]

    # External API calls
    source_modules = {
        "arxiv": src_arxiv,
        "semantic_scholar": src_s2,
        "openalex": src_oa,
    }
    raw: List[PaperCandidate] = []
    errors = []
    for name, mod in source_modules.items():
        if name not in active_sources:
            continue
        try:
            results = mod.search(
                q,
                max_results=15,
                year_from=_config.timeline_from_year if _config else None,
                year_to=_config.timeline_to_year if _config else None,
            )
            raw.extend(results)
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    # Dedup and filter against known IDs
    known_ids = {p.paper_id for p in _papers + _rejects if p.paper_id}
    unique, _ = deduplicate(raw)
    new_candidates = []
    for p in unique:
        p.paper_id = make_paper_id(p)
        if p.paper_id in known_ids:
            continue
        score = _index.add_paper(p, _embedder)
        _index.remove_paper(p.paper_id)
        p.embedding_score = round(score, 4)
        if _config:
            p.score = keyword_score(p, _config)
        new_candidates.append(candidate_to_dict(p))

    new_candidates.sort(key=lambda x: x.get("embedding_score") or 0, reverse=True)
    return jsonify({"db_matches": db_matches, "new_candidates": new_candidates, "errors": errors})


@app.route("/api/papers/<paper_id>", methods=["PUT"])
def api_update_paper(paper_id):
    data = request.get_json() or {}
    paper = next((p for p in _papers if p.paper_id == paper_id), None)
    if paper is None:
        return jsonify({"error": "not found"}), 404

    for field in ("title", "authors", "year", "abstract", "url", "pdf_url"):
        if field in data:
            setattr(paper, field, data[field])

    score = _index.add_paper(paper, _embedder)
    paper.embedding_score = round(score, 4)
    if _config:
        paper.score = keyword_score(paper, _config)

    save_papers(_papers)
    return jsonify(candidate_to_dict(paper))


@app.route("/api/papers/<paper_id>/reject", methods=["POST"])
def api_reject_paper(paper_id):
    data = request.get_json() or {}
    reason = data.get("reason", "manually_rejected")
    paper = next((p for p in _papers if p.paper_id == paper_id), None)
    if paper is None:
        return jsonify({"error": "not found"}), 404

    _papers.remove(paper)
    _index.remove_paper(paper_id)
    paper.rejection_reason = reason
    _rejects.append(paper)

    save_papers(_papers)
    save_rejects(_rejects)
    return jsonify({"ok": True})


@app.route("/api/rejects/<paper_id>/approve", methods=["POST"])
def api_approve_reject(paper_id):
    paper = next((p for p in _rejects if p.paper_id == paper_id), None)
    if paper is None:
        return jsonify({"error": "not found"}), 404

    _rejects.remove(paper)
    paper.rejection_reason = None

    score = _index.add_paper(paper, _embedder)
    paper.embedding_score = round(score, 4)
    _papers.append(paper)

    save_papers(_papers)
    save_rejects(_rejects)
    return jsonify({"ok": True})


@app.route("/api/papers/<paper_id>", methods=["DELETE"])
def api_delete_paper(paper_id):
    paper = next((p for p in _papers if p.paper_id == paper_id), None)
    if paper is None:
        return jsonify({"error": "not found"}), 404

    _papers.remove(paper)
    _index.remove_paper(paper_id)
    save_papers(_papers)
    return jsonify({"ok": True})


@app.route("/api/candidates/add", methods=["POST"])
def api_add_candidate():
    data = request.get_json() or {}
    ids_data = data.get("identifiers") or {}
    p = PaperCandidate(
        title=data.get("title", ""),
        authors=data.get("authors", []),
        year=data.get("year"),
        abstract=data.get("abstract"),
        url=data.get("url"),
        pdf_url=data.get("pdf_url"),
        identifiers=PaperIdentifiers(
            doi=ids_data.get("doi"),
            arxiv_id=ids_data.get("arxiv_id"),
            openalex_id=ids_data.get("openalex_id"),
            semantic_scholar_id=ids_data.get("semantic_scholar_id"),
        ),
        sources=data.get("sources", []),
        raw={},
        score=float(data.get("score", 0.0)),
        embedding_score=data.get("embedding_score"),
    )
    p.paper_id = make_paper_id(p)

    known_ids = {x.paper_id for x in _papers + _rejects if x.paper_id}
    if p.paper_id in known_ids:
        return jsonify({"error": "already in database"}), 409

    score = _index.add_paper(p, _embedder)
    p.embedding_score = round(score, 4)
    if _config:
        p.score = keyword_score(p, _config)

    _papers.append(p)
    save_papers(_papers)
    return jsonify(candidate_to_dict(p)), 201


# ── Entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Dynamic-LR server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    )

    _startup()
    logger.info("Serving on http://%s:%d", args.host, args.port)
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
