"""ResearchAgent: full article text -> structured, sourced ResearchDoc.

Runs once per source then merges partials. Hard rule in the prompt: set any
field you cannot support to null/empty; never fabricate. Mirrors the Codex
Perplexity research stage, trimmed to what the blog actually renders.
"""
from __future__ import annotations

import asyncio
import logging

from app import store
from app.llm import gateway
from app.schemas import ResearchDoc

log = logging.getLogger("app.agents.research")

_SYS = (
    "You are a startup research analyst building a factual breakdown for a youth "
    "entrepreneur blog. From the ARTICLE, extract ONLY verifiable, story-defining "
    "facts about the company. Set any field you cannot support to null/empty. "
    "Never invent numbers, names, dates, or quotes.\n\n"
    "Return JSON matching this shape (omit unknowns, keep arrays you cannot fill empty):\n"
    '{"startup_name":"","tagline":null,"pivotal_insight":null,"origin_story":null,'
    '"timeline":[{"date":"YYYY","kind":"founder_story|product|funding|inflection|user_delight",'
    '"event":"","significance":"","source":{"quote":"","url":""}}],'
    '"founders":[{"name":"","role":"","background":"","why":null,"source":{"quote":"","url":""}}],'
    '"funding":[{"round":"","date":"","amount_usd":null,"valuation_usd":null,"investors":[],'
    '"source":{"quote":"","url":""}}],'
    '"metrics":[{"label":"","value":"","date":null,"source_url":null}],'
    '"competitors":[{"name":"","positioning":"","strengths":[],"weaknesses":[],"our_advantage":null}],'
    '"product_loop_steps":[],'
    '"lessons":[{"lesson":"","context":"","applicable_to":"","source":{"quote":"","url":""}}]}'
)

_LIST_KEYS = ["timeline", "founders", "product_evolution", "funding", "metrics",
              "competitors", "product_loop_steps", "lessons", "sources"]
_SCALAR_KEYS = ["tagline", "pivotal_insight", "origin_story"]


async def _extract_one(text: str, url: str) -> dict:
    try:
        rd = await gateway.complete_json(
            _SYS, f"SOURCE_URL: {url}\n\nARTICLE:\n{text[:16000]}",
            ResearchDoc, role="general",
            # Free-form + repair: full-length constrained-JSON decode on Cloudflare
            # is ~90s/call (13 of these run in parallel) and would time out. The
            # prompt already specifies the shape; structured=True truncates here.
            structured=False,
        )
        return rd.model_dump()
    except gateway.LLMError as e:
        log.warning("research extract failed %s: %s", url, e)
        return {}


def _merge(name: str, partials: list[dict]) -> ResearchDoc:
    base: dict = {"startup_name": name}
    for k in _LIST_KEYS:
        base[k] = []
    for p in partials:
        for k in _SCALAR_KEYS:
            if not base.get(k) and p.get(k):
                base[k] = p[k]
        for k in _LIST_KEYS:
            if p.get(k):
                base[k].extend(p[k])
    return ResearchDoc.model_validate(base)


async def run(sources: list, name: str) -> ResearchDoc:
    log.info("=== research: %d sources for %s (parallel) ===", len(sources), name)
    # Issue all per-source extractions concurrently. The LLM rate-limiter still
    # spaces the actual requests, but their long inference waits now overlap,
    # cutting wall-clock from sum(latency) toward max(latency).
    jobs = []
    for s in sources:
        text = store.read_cached_text(s.raw_text_ref)
        if text:
            log.info("  queue %s (%d chars)", s.url[:70], len(text))
            jobs.append(_extract_one(text, s.url))
    partials = await asyncio.gather(*jobs) if jobs else []
    doc = _merge(name, partials)
    log.info("=== research done: %d timeline, %d funding, %d metrics, %d competitors, %d lessons ===",
             len(doc.timeline), len(doc.funding), len(doc.metrics),
             len(doc.competitors), len(doc.lessons))
    return doc
