"""SourceAgent: discover -> extract -> classify (success/cautionary/reject).

Discovery is Firecrawl v2 /search, which both finds and scrapes articles in one
call (markdown main content). When Firecrawl omits content, trafilatura is the
fallback extractor. Classification keeps only narrative-worthy stories and tags
each accepted article success|cautionary; the dominant label sets the story arc.
"""
from __future__ import annotations

import asyncio
import logging
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from .. import config, store
from ..llm import gateway
from ..schemas import Source, SourceLabel

log = logging.getLogger("app.agents.source")


# --- LLM response schema ---------------------------------------------------

class _Classification(BaseModel):
    label: SourceLabel
    reason: str = ""


# --- discovery (Firecrawl v2 search + scrape) ------------------------------

# story-relevant query expansion so search skews to narrative coverage
_QUERY_EXPANSION = (
    '(founding OR founder OR funding OR investment '
    'OR success OR growth OR failure OR challenges OR pivot OR "market fit" '
    'OR breakthrough OR lessons OR journey OR "go-to-market" OR interviews)'
)


async def _firecrawl_search(query: str, max_records: int) -> list[dict]:
    if not config.FIRECRAWL_API_KEY:
        log.error("FIRECRAWL_API_KEY not set — no discovery source available")
        return []
    payload = {
        "query": f'"{query}" {_QUERY_EXPANSION}',
        "sources": ["web"],
        "categories": [],
        "limit": max_records,
        "scrapeOptions": {
            "onlyMainContent": True,
            "maxAge": config.FIRECRAWL_MAX_AGE,
            "parsers": [],
            "formats": ["markdown"],   # REQUIRED to get article text back
        },
    }
    headers = {
        "Authorization": f"Bearer {config.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    log.info("Firecrawl search query=%r limit=%d", query, max_records)
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(config.FIRECRAWL_SEARCH_API, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001 - degrade rather than crash pipeline
        log.error("Firecrawl search failed: %s", e)
        return []

    out = _normalize_results(data)
    log.info("Firecrawl returned %d results", len(out))
    return out


def _normalize_results(data: dict) -> list[dict]:
    """Parse a Firecrawl v2 search response into {url,title,domain,text}.

    Keeps the FULL scraped markdown (no truncation) so the research agent has
    real material to synthesize from.
    """
    body = data.get("data", data)            # v2: {"data": {"web": [...]}} or flat
    results = body.get("web", []) if isinstance(body, dict) else (body or [])
    out: list[dict] = []
    for x in results:
        url = x.get("url", "")
        md = x.get("markdown") or x.get("content") or x.get("description") or ""
        out.append({
            "url": url,
            "title": x.get("title") or x.get("metadata", {}).get("title", ""),
            "domain": urlparse(url).netloc,
            "text": md,
        })
    return out


def _dedupe(candidates: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    kept: list[dict] = []
    for art in candidates:
        url = (art.get("url") or "").split("?")[0]
        title = art.get("title", "")
        if not url or url in seen_urls:
            continue
        if any(SequenceMatcher(None, title, k.get("title", "")).ratio() > 0.85 for k in kept):
            continue
        seen_urls.add(url)
        kept.append(art)
    return kept


# --- extraction ------------------------------------------------------------

def _extract(url: str) -> Optional[str]:
    """trafilatura full-text extraction. Returns clean text or None."""
    try:
        import trafilatura
    except ImportError:
        return None
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(downloaded, include_comments=False, include_tables=False)


# --- classification (BATCH: one LLM call for all candidates) ---------------

class _BatchResult(BaseModel):
    # flat index->label map: {"labels": {"0": "success", "1": "reject"}}
    # far easier for small/weak models than a list of nested objects
    labels: dict[str, str] = {}


_CLASSIFY_SYS = (
    "You triage business-news articles for a story blog. For EACH numbered "
    "article (title + lead) assign exactly one label:\n"
    "- success: a company/founder success narrative (growth, breakout funding, "
    "market win, turnaround).\n"
    "- cautionary: a failure / lessons-learnt narrative (shutdown, pivot, scandal, "
    "post-mortem, what-went-wrong).\n"
    "- reject: routine/neutral/PR/listicle/price-update coverage, no narrative arc.\n\n"
    'Respond ONLY as JSON mapping each index to its label, e.g.:\n'
    '{"labels": {"0": "success", "1": "reject", "2": "cautionary"}}\n'
    "Include every index exactly once. Use only those three label words."
)

_VALID = {"success", "cautionary", "reject"}


async def _classify_batch(items: list[tuple[int, str, str]]) -> dict[int, _Classification]:
    """items: (index, title, lead). One LLM call. Returns index -> classification."""
    if not items:
        return {}
    blocks = [f"[{idx}] TITLE: {title}\nLEAD: {lead[:500]}" for idx, title, lead in items]
    user = "\n\n".join(blocks)
    out: dict[int, _Classification] = {}
    try:
        result = await gateway.complete_json(
            _CLASSIFY_SYS, user, _BatchResult,
            role="fast",   # tiny triage task — never a slow reasoning model
        )
        for k, v in result.labels.items():
            label = v.strip().lower() if isinstance(v, str) else "reject"
            if label not in _VALID:
                label = "reject"
            try:
                out[int(k)] = _Classification(label=label)  # type: ignore[arg-type]
            except ValueError:
                continue
    except gateway.LLMError as e:
        log.error("batch classify failed (%s) — rejecting all", e)
        return {idx: _Classification(label="reject", reason="classify failed")
                for idx, _, _ in items}
    for idx, _, _ in items:
        out.setdefault(idx, _Classification(label="reject", reason="missing in response"))
    return out


def pick_arc(labels: list[SourceLabel]) -> str:
    """Dominant non-reject label -> story arc. Defaults to 'success'."""
    keep = [l for l in labels if l != "reject"]
    if not keep:
        return "success"
    return "cautionary" if keep.count("cautionary") > keep.count("success") else "success"


# --- public API ------------------------------------------------------------

async def gather(query: str, max_sources: int = 8) -> tuple[list[Source], str]:
    """Return (accepted sources with cached text, story arc)."""
    log.info("=== gather query=%r max_sources=%d ===", query, max_sources)
    raw = await _firecrawl_search(query, max_sources * 2)
    candidates = _dedupe(raw)[: max_sources * 2]
    log.info("candidates after dedupe: %d", len(candidates))

    # 1) resolve usable text for each candidate (Firecrawl raw_content, else trafilatura)
    prepared: list[dict] = []   # {url,title,text,domain}
    for i, art in enumerate(candidates):
        url = art.get("url", "")
        title = art.get("title", "") or url
        text = art.get("text") or ""
        if len(text) < 400:
            log.info("[%d/%d] trafilatura fallback: %s", i + 1, len(candidates), url[:80])
            text = await asyncio.to_thread(_extract, url) or ""
        else:
            log.info("[%d/%d] firecrawl raw_content: %s", i + 1, len(candidates), url[:80])
        if not text or len(text) < 400:
            log.debug("  → skip (no usable text, len=%d)", len(text or ""))
            continue
        prepared.append({"url": url, "title": title, "text": text,
                         "domain": art.get("domain")})

    # 2) ONE batch classify call for all prepared candidates (saves RPM budget)
    log.info("batch-classifying %d candidates in one call", len(prepared))
    cls_map = await _classify_batch(
        [(i, p["title"], p["text"][:800]) for i, p in enumerate(prepared)]
    )

    # 3) keep non-reject up to max_sources
    sources: list[Source] = []
    labels: list[SourceLabel] = []
    for i, p in enumerate(prepared):
        if len(sources) >= max_sources:
            break
        cls = cls_map.get(i, _Classification(label="reject"))
        log.info("  [%d] label=%s — %.60s", i, cls.label, p["title"])
        if cls.label == "reject":
            continue
        ref = store.cache_text(p["url"], p["text"])
        sources.append(Source(
            id=f"s{len(sources)}",
            url=p["url"],
            title=p["title"],
            publisher=p["domain"] or None,
            raw_text_ref=ref,
            label=cls.label,
        ))
        labels.append(cls.label)

    arc = pick_arc(labels)
    log.info("=== gather done: %d sources accepted, arc=%s ===", len(sources), arc)
    return sources, arc
