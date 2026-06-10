import logging
from typing import Dict, List, Tuple

import numpy as np

from app.embeddings.embedder import Embedder
from app.embeddings.segmenter import segment_paper
from app.state.schemas import PaperCandidate, SurveyConfig

logger = logging.getLogger(__name__)


class EmbeddingIndex:
    def __init__(self) -> None:
        self.paper_vectors: Dict[str, np.ndarray] = {}  # paper_id → (N_segs × dim)
        self.query_vectors: np.ndarray = np.zeros((0, 384), dtype=np.float32)
        self.scores: Dict[str, float] = {}  # paper_id → embedding_score

    def build(
        self,
        papers: List[PaperCandidate],
        config: SurveyConfig,
        embedder: Embedder,
    ) -> None:
        logger.info("Building embedding index for %d papers", len(papers))

        query_texts = []
        if config.topic_overview:
            query_texts.append(config.topic_overview)
        query_texts.extend(config.research_questions or [])
        query_texts.extend(config.query_hints or [])
        query_texts = [t.strip() for t in query_texts if t.strip()]

        if query_texts:
            logger.info("Embedding %d query segments", len(query_texts))
            self.query_vectors = embedder.embed(query_texts)
        else:
            logger.warning("No query texts found — embedding scores will be 0")
            self.query_vectors = np.zeros((0, 384), dtype=np.float32)

        # Batch-embed all paper segments
        seg_map: List[Tuple[str, int]] = []  # (paper_id, seg_count)
        all_segs: List[str] = []
        for p in papers:
            if not p.paper_id:
                continue
            segs = segment_paper(p)
            seg_map.append((p.paper_id, len(segs)))
            all_segs.extend(segs)

        logger.info("Embedding %d paper segments across %d papers", len(all_segs), len(seg_map))
        all_vecs = embedder.embed(all_segs) if all_segs else np.zeros((0, 384), dtype=np.float32)

        cursor = 0
        for paper_id, n in seg_map:
            vecs = all_vecs[cursor : cursor + n] if n else np.zeros((0, all_vecs.shape[1] if all_vecs.size else 384), dtype=np.float32)
            self.paper_vectors[paper_id] = vecs
            self.scores[paper_id] = embedder.max_sim(vecs, self.query_vectors)
            cursor += n

        logger.info("Index ready: %d papers scored", len(self.scores))

    def add_paper(self, paper: PaperCandidate, embedder: Embedder) -> float:
        if not paper.paper_id:
            return 0.0
        segs = segment_paper(paper)
        vecs = embedder.embed(segs) if segs else np.zeros((0, 384), dtype=np.float32)
        self.paper_vectors[paper.paper_id] = vecs
        score = embedder.max_sim(vecs, self.query_vectors)
        self.scores[paper.paper_id] = score
        return score

    def remove_paper(self, paper_id: str) -> None:
        self.paper_vectors.pop(paper_id, None)
        self.scores.pop(paper_id, None)

    def search(self, query: str, embedder: Embedder, top_k: int = 20) -> List[Tuple[str, float]]:
        if not self.paper_vectors:
            return []
        q_vec = embedder.embed([query])
        results = [
            (pid, embedder.max_sim(pvecs, q_vec))
            for pid, pvecs in self.paper_vectors.items()
            if pvecs.size > 0
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
