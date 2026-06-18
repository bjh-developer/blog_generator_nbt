"""Pipeline: source -> research -> editorial -> write content JSON file.

The emitted file is what the Next.js app renders. Degrades gracefully: a failed
stage yields a thinner StoryBrief rather than a crash.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app import config
from app.agents import editorial, research, source
from app.schemas import StoryBrief

log = logging.getLogger("app.pipeline")


def write_story(sb: StoryBrief) -> Path:
    config.CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    p = config.CONTENT_DIR / f"{sb.meta.slug}.json"
    p.write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    log.info("wrote %s", p)
    return p


async def generate(query: str, max_sources: int = 8) -> StoryBrief:
    log.info("▶ pipeline start query=%r", query)
    sources, _arc = await source.gather(query, max_sources=max_sources)
    log.info("▶ source done: %d sources", len(sources))

    rd = await research.run(sources, query)
    log.info("▶ research done")

    sb = await editorial.build(rd, sources)
    write_story(sb)
    log.info("▶ pipeline complete slug=%s confidence=%.2f", sb.meta.slug, sb.overall_confidence)
    return sb
