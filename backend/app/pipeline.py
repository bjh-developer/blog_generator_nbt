"""Pipeline: source -> research -> editorial -> write content JSON file.

The emitted file is what the Next.js app renders. Degrades gracefully: a failed
stage yields a thinner StoryBrief rather than a crash.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app import config, qa
from app.agents import editorial, research, source
from app.schemas import StoryBrief
from typing import List, Tuple

log = logging.getLogger("app.pipeline")


def write_story(sb: StoryBrief) -> Path:
    config.CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    p = config.CONTENT_DIR / f"{sb.meta.slug}.json"
    p.write_text(sb.model_dump_json(indent=2), encoding="utf-8")
    log.info("wrote %s", p)
    return p


def _next_volume(slug: str) -> str:
    """Return next Vol. NN, reusing existing number if slug already written."""
    existing = list(config.CONTENT_DIR.glob("*.json"))
    slugs = [p.stem for p in existing]
    if slug in slugs:
        # regeneration — reuse the same ordinal (position in sorted list)
        idx = sorted(slugs).index(slug) + 1
    else:
        idx = len(existing) + 1
    return f"Vol. {idx:02d}"


async def generate(query: str, max_sources: int = 8) -> Tuple[StoryBrief, List[str], List[str]]:
    log.info("▶ pipeline start query=%r", query)
    sources, _arc = await source.gather(query, max_sources=max_sources)
    log.info("▶ source done: %d sources", len(sources))

    rd = await research.run(sources, query)
    log.info("▶ research done")

    sb = await editorial.build(rd, sources)
    sb.meta.volume = _next_volume(sb.meta.slug)

    errors, warnings = qa.split(qa.audit(sb))
    if errors:
        # auto-repair the hard-error classes deterministically, then re-audit
        log.warning("▶ QA found %d error(s), attempting auto-repair: %s", len(errors), errors)
        sb = qa.repair(sb)
        errors, warnings = qa.split(qa.audit(sb))
        if errors:
            log.error("▶ QA auto-repair INCOMPLETE — %d error(s) remain, not writing "
                      "%s.json: %s", len(errors), sb.meta.slug, errors)
            return sb, errors, warnings
        log.info("▶ QA auto-repair succeeded")

    if warnings:
        log.warning("▶ QA warnings (advisory, %d): %s", len(warnings), warnings)
    log.info("▶ QA audit clean (no errors)")
    write_story(sb)
    log.info("▶ pipeline complete slug=%s confidence=%.2f", sb.meta.slug, sb.overall_confidence)
    return sb, errors, warnings
