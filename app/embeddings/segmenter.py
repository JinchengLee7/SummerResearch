import re
from typing import List

from app.state.schemas import PaperCandidate

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\d])")
_MIN_SEG_LEN = 25


def segment_paper(paper: PaperCandidate) -> List[str]:
    segs: List[str] = []
    if paper.title and paper.title.strip():
        segs.append(paper.title.strip())
    if paper.abstract:
        for s in _SENTENCE_SPLIT.split(paper.abstract):
            s = s.strip()
            if len(s) >= _MIN_SEG_LEN:
                segs.append(s)
    return segs
