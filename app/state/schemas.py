from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PaperIdentifiers:
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    openalex_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None


@dataclass
class PaperCandidate:
    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    identifiers: PaperIdentifiers = field(default_factory=PaperIdentifiers)
    sources: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    rejection_reason: Optional[str] = None
    paper_id: Optional[str] = None
    embedding_score: Optional[float] = None


@dataclass
class SurveyConfig:
    topic_overview: str
    research_questions: List[str] = field(default_factory=list)
    question_context: str = ""
    query_hints: List[str] = field(default_factory=list)
    timeline_from_year: Optional[int] = None
    timeline_to_year: Optional[int] = None
    min_relevance_score: float = 0.0


@dataclass
class ManagerRunResult:
    architecture: str
    queries_generated: int
    sources_queried: List[str]
    candidates_found: int
    candidates_after_dedupe: int
    papers_accepted: int
    candidates_rejected: int
    dry_run: bool
    started_at: str
    finished_at: str
    errors: List[str] = field(default_factory=list)
