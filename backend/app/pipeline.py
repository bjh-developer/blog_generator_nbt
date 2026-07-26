"""Pipeline: source -> research -> editorial -> write content JSON file.

The emitted file is what the Next.js app renders. Degrades gracefully: a failed
stage yields a thinner StoryBrief rather than a crash.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app import config, qa, store
from app.agents import corrector, editorial, judge, research, source
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

    corpus = "\n".join(store.read_cached_text(s.raw_text_ref) for s in sources)

    # Funding corrector: if funding rounds are sourced from low-authority pages,
    # web-search authoritative sources and REPLACE them. Runs BEFORE the QA audit
    # (so QA validates the corrected funding, not the stale rounds) and BEFORE
    # the judge (so the judge validates the corrected funding too). Fail-open.
    corr_warnings: List[str] = []
    if sb.funding and sb.funding.rounds:
        new_rounds, new_chart, evidence, corr_warnings = await corrector.correct_funding(
            sb.meta.startup_name, sb.funding.rounds, sources)
        if new_rounds is not None:
            sb.funding.rounds = new_rounds
            if new_chart is not None:
                sb.funding.chart = new_chart
        if evidence is not None:
            corpus = corpus + "\n" + evidence

    # QA audit: a final, deterministic consistency pass over the (now
    # funding-corrected) story before it ships.
    errors, qa_warnings = qa.split(qa.audit(sb))
    if errors:
        # auto-repair the hard-error classes deterministically, then re-audit
        log.warning("▶ QA found %d error(s), attempting auto-repair: %s", len(errors), errors)
        sb = qa.repair(sb)
        errors, qa_warnings = qa.split(qa.audit(sb))
        if errors:
            log.error("▶ QA auto-repair INCOMPLETE — %d error(s) remain, not writing "
                      "%s.json: %s", len(errors), sb.meta.slug, errors)
            return sb, errors, corr_warnings + qa_warnings
        log.info("▶ QA auto-repair succeeded")

    # LLM judge: advisory quality/safety/factuality review (flag-for-human).
    # Fail-open — never blocks the write. corpus may now include the corrector's
    # authoritative evidence so freshly-verified funding isn't wrongly re-flagged.
    judge_warnings = await judge.review(sb, corpus)
    if judge_warnings:
        log.warning("▶ judge flagged %d issue(s): %s", len(judge_warnings), judge_warnings)

    warnings = corr_warnings + qa_warnings + judge_warnings
    if warnings:
        log.warning("▶ warnings (advisory, %d): %s", len(warnings), warnings)
    log.info("▶ QA audit clean (no errors)")
    write_story(sb)
    log.info("▶ pipeline complete slug=%s confidence=%.2f", sb.meta.slug, sb.overall_confidence)
    return sb, errors, warnings
