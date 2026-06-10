from typing import List

import numpy as np
from fastembed import TextEmbedding

_MODEL = "BAAI/bge-small-en-v1.5"
_BATCH = 64


class Embedder:
    def __init__(self) -> None:
        self._model = TextEmbedding(_MODEL)

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return np.array(list(self._model.embed(texts, batch_size=_BATCH)), dtype=np.float32)

    @staticmethod
    def max_sim(paper_vecs: np.ndarray, query_vecs: np.ndarray) -> float:
        """MaxSim: best cosine across all (paper_seg, query_seg) pairs, mapped to [0,1]."""
        if paper_vecs.size == 0 or query_vecs.size == 0:
            return 0.0
        pn = paper_vecs / (np.linalg.norm(paper_vecs, axis=1, keepdims=True) + 1e-9)
        qn = query_vecs / (np.linalg.norm(query_vecs, axis=1, keepdims=True) + 1e-9)
        raw = float((pn @ qn.T).max())
        return (raw + 1.0) / 2.0
