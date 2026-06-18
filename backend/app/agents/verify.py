"""VerifyAgent: ground ResearchDoc items in scraped text + relevance gate.

Two gates protect the blog from the key problem (irrelevant/hallucinated facts):
  - grounding: stat/quote must appear (exact or fuzzy) in the scraped corpus.
  - relevance: an LLM judge keeps only items that teach/inspire a youth founder.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from pydantic import BaseModel

from app import config
from app.llm import gateway
from app.schemas import Metric

log = logging.getLogger("app.agents.verify")

GOAL = "teach and inspire aspiring youth entrepreneurs with a real startup story"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def ground_score(claim: str, text: str) -> float:
    """0..1 confidence that `claim` is supported by `text`."""
    n, h = _norm(claim), _norm(text)
    if not n:
        return 0.0
    if n in h:
        return 1.0
    win = max(8, len(n))
    best = 0.0
    for i in range(0, max(1, len(h) - win + 1), max(1, win // 2)):
        best = max(best, SequenceMatcher(None, n, h[i:i + win]).ratio())
        if best >= 0.95:
            break
    # numbers in the claim must appear in the text, else heavily discount
    for num in re.findall(r"\d[\d,.]*", n):
        if num.replace(",", "") not in h.replace(",", ""):
            best *= 0.4
    return round(best, 3)


def filter_metrics(metrics: list[Metric], text: str, threshold: float = None) -> list[Metric]:
    t = config.VERIFY_THRESHOLD if threshold is None else threshold
    return [m for m in metrics if ground_score(f"{m.value} {m.label}", text) >= t]


class _Rel(BaseModel):
    keep_indices: list[int] = []


async def relevance_filter(items: list[str], goal: str = GOAL) -> list[int]:
    """Return indices worth keeping for the youth-founder goal. Fail-open."""
    if not items:
        return []
    listing = "\n".join(f"[{i}] {t}" for i, t in enumerate(items))
    sys = (
        "You curate insights for an audience of 18-28 aspiring founders. "
        f"GOAL: {goal}. Keep only items that genuinely teach or inspire that "
        "audience; drop generic, trivial, or PR-fluff items. "
        'Return JSON {"keep_indices": [...]} listing the indices to KEEP.'
    )
    try:
        r = await gateway.complete_json(sys, listing, _Rel, role="fast")
        return [i for i in r.keep_indices if 0 <= i < len(items)]
    except gateway.LLMError:
        return list(range(len(items)))      # fail-open: keep all
