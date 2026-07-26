"""FundingCorrector: when a story's funding rounds include any sourced from
low-authority pages (blogs/forums that can carry a wrong funding table), search
authoritative sources via Firecrawl and MERGE in verified data — the rounds
already sourced from a high-authority domain are kept untouched, and only the
low-authority rounds are replaced with newly-verified ones (or left as-is if
none could be verified).

This is the one place the pipeline mutates a story to FIX facts rather than just
flag them. Everything is fail-open: any search/LLM failure leaves the original
rounds untouched and emits an advisory warning instead of raising.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app import config, store
from app.agents import editorial, source, verify
from app.agents.authority import authority
from app.llm import gateway
from app.schemas import FundingPoint, FundingRound, FundingRoundView, Source, SourceRef

log = logging.getLogger("app.agents.corrector")

_AUTH_RANK = {"high": 0, "med": 1, "low": 2}

# funding-relevant text so we don't feed the LLM the top-of-page nav/intro of a
# long article (e.g. Wikipedia's Grab page is 100k+ chars; funding sits deep in it)
_FUND_KW = re.compile(
    r"(series\s+[a-h]\b|seed\s+round|pre-seed|raised|funding\s+round|"
    r"\$\s?\d[\d.,]*\s*(?:m|bn|b|k|million|billion)|valuation|led\s+by|investment\s+round)",
    re.I,
)


def _funding_excerpt(text: str, budget: int = 9000) -> str:
    """Concatenate ~±350-char windows around funding keywords, up to `budget`.
    Falls back to the head of the text when no keyword is found."""
    hits = [m.start() for m in _FUND_KW.finditer(text or "")]
    if not hits:
        return (text or "")[:budget]
    windows: list[tuple[int, int]] = []
    for h in hits:
        a, b = max(0, h - 350), min(len(text), h + 350)
        if windows and a <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], b))
        else:
            windows.append((a, b))
    out = "\n…\n".join(text[a:b] for a, b in windows)
    return out[:budget]


class _CorrectedFunding(BaseModel):
    rounds: List[FundingRound] = Field(default_factory=list)


_SEARCH_SYS = (
    "You are a financial fact-checker. From the AUTHORITATIVE SOURCES about ONE "
    "company, extract its funding rounds. SPAN LOCK: a round's `round` (e.g. "
    "'Series C'), `date` (YYYY), and `amount_usd` MUST appear together in the same "
    "sentence of a source; put that sentence in `source.quote` and the source URL "
    "in `source.url`. If a round's label, year, and amount are not stated together, "
    "omit it — never guess or pair values from different places. Prefer the most "
    "reputable source when sources disagree. Return only rounds you can ground.\n"
    'Return JSON: {"rounds":[{"round":"","date":"YYYY","amount_usd":null,'
    '"valuation_usd":null,"investors":[],"source":{"quote":"","url":""}}]}'
)


def _needs_correction(rounds: List[FundingRoundView]) -> bool:
    """True if any round's source is not high-authority (blog/unknown)."""
    for r in rounds:
        url = r.source.url if r.source else None
        if authority(url or "") != "high":
            return True
    return False


_MONEY = re.compile(r"\$?\s?(\d[\d.,]*)\s*(billion|bn|million|mn|thousand|[kmb])?\b", re.I)
_MULT = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6, "mn": 1e6,
         "m": 1e6, "thousand": 1e3, "k": 1e3}


def _money_values(text: str) -> list[float]:
    out: list[float] = []
    for m in _MONEY.finditer(text or ""):
        try:
            num = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append(num * _MULT.get((m.group(2) or "").lower(), 1))
    return out


def _quote_supports_amount(amount_usd: float, quote: str) -> bool:
    """True if the cited quote contains a money figure within 5% of the amount.
    Stops the corrector from replacing with rounds whose amount the source doesn't
    actually state (the same bar the judge applies)."""
    if not quote:
        return False
    return any(abs(v - amount_usd) <= 0.05 * amount_usd for v in _money_values(quote))


def _to_views(rounds: List[FundingRound]) -> Tuple[List[FundingRoundView], List[FundingPoint]]:
    views: List[FundingRoundView] = []
    chart: List[FundingPoint] = []
    for f in rounds:
        if not f.amount_usd:
            continue
        views.append(FundingRoundView(
            label=f.round, date=f.date,
            amount=editorial._fmt_usd(f.amount_usd),
            valuation=(editorial._fmt_usd(f.valuation_usd) if f.valuation_usd else None),
            source=f.source,
        ))
        chart.append(FundingPoint(label=f.round, value=round(f.amount_usd / 1e6, 2),
                                  unit="$M", date=f.date or None))
    chart.sort(key=lambda p: p.date or "")
    return views, chart


def _authoritative_from_scraped(sources: List[Source]) -> List[dict]:
    """High-authority pages already scraped in the main gather — reuse them
    before spending another Firecrawl search."""
    out: list[dict] = []
    for s in sources or []:
        if authority(s.url) == "high":
            txt = store.read_cached_text(s.raw_text_ref)
            if txt:
                out.append({"url": s.url, "domain": urlparse(s.url).netloc, "text": txt})
    return out


def _dedupe_key(label: str, date: str) -> Tuple[str, str]:
    """Same (label sans trailing '(YYYY)', year) key used by
    editorial.clean_funding, but over a FundingRoundView's `label`/`date`
    instead of a FundingRound's `round`/`date`."""
    base = re.sub(r"\s*\(\d{4}\)$", "", label or "").strip().lower()
    return base, (date or "")[:4]


_FMT_USD_RE = re.compile(r"^\$(\d[\d.]*)\s*([MB])$")
_FMT_USD_MULT = {"M": 1e6, "B": 1e9}


def _parse_fmt_usd(text: Optional[str]) -> Optional[float]:
    """Inverse of editorial._fmt_usd: '$1.5M' / '$350M' / '$2B' -> raw USD float.
    Returns None if `text` isn't in that exact format."""
    if not text:
        return None
    m = _FMT_USD_RE.match(text.strip())
    if not m:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    return num * _FMT_USD_MULT[m.group(2)]


def _chart_point(view: FundingRoundView) -> Optional[FundingPoint]:
    amount_usd = _parse_fmt_usd(view.amount)
    if amount_usd is None:
        return None
    return FundingPoint(label=view.label, value=round(amount_usd / 1e6, 2),
                         unit="$M", date=view.date or None)


async def correct_funding(
    company: str,
    current: List[FundingRoundView],
    sources: Optional[List[Source]] = None,
) -> Tuple[Optional[List[FundingRoundView]], Optional[List[FundingPoint]], Optional[str], List[str]]:
    """Return (new_rounds, new_chart, evidence, warnings).

    new_rounds/new_chart are None when nothing changed (caller leaves `current`
    untouched). When a correction IS produced, new_rounds is `current`'s
    already-high-authority rounds MERGED with newly-verified rounds (never a
    wholesale replacement of rounds that were already fine).

    evidence is the authoritative-source corpus used for extraction, so a
    caller (e.g. the judge step) can fact-check the corrected numbers against
    it instead of re-flagging them against the original, non-authoritative
    corpus. It is None whenever no authoritative corpus was built.
    """
    if not current or not _needs_correction(current):
        return None, None, None, []

    high: List[FundingRoundView] = []
    low: List[FundingRoundView] = []
    for r in current:
        url = r.source.url if r.source else None
        (high if authority(url or "") == "high" else low).append(r)
    if not low:
        return None, None, None, []

    # 1) Prefer high-authority pages ALREADY scraped in the main gather (free);
    #    only web-search as a fallback. Rank by domain authority either way.
    good = _authoritative_from_scraped(sources or [])[:3]
    if not good:
        # Keep the query natural — barewords like "crunchbase OR techcrunch" make
        # Firecrawl return nothing; rank whatever comes back by authority instead.
        query = f'"{company}" total funding rounds by year Series seed amount raised'
        try:
            results = await source._firecrawl_search(query, 10)
        except Exception as e:  # noqa: BLE001 — degrade, never crash
            log.warning("corrector search failed: %s", e)
            return None, None, None, [f"funding: could not search to verify ({e}) — left as-is, verify manually"]
        ranked = sorted(results, key=lambda x: _AUTH_RANK[authority(x.get("domain", ""))])
        good = [x for x in ranked if authority(x.get("domain", "")) in ("high", "med") and x.get("text")][:3]

    if not good:
        return None, None, None, ["funding: no authoritative source found to verify — left as-is, verify manually"]

    corpus = "\n\n".join(
        f"SOURCE {x['url']} ({x['domain']}):\n{_funding_excerpt(x['text'])}" for x in good)

    # 2) extract grounded rounds from the authoritative corpus
    try:
        res = await gateway.complete_json(_SEARCH_SYS, corpus, _CorrectedFunding,
                                          role="general", temperature=0.0, structured=True)
    except gateway.LLMError as e:
        log.warning("corrector extract failed: %s", e)
        return None, None, None, [f"funding: authoritative extraction failed ({e}) — left as-is"]

    # Keep a round only if BOTH:
    #  (a) its amount is stated in its cited quote, AND
    #  (b) that quote actually appears in the authoritative source text.
    # (b) is the anti-fabrication gate: the LLM can invent an amount AND a matching
    # quote, so self-consistency isn't enough — the quote must be real.
    verified = []
    for f in res.rounds:
        if not f.amount_usd:
            continue
        q = (f.source.quote if f.source else "") or ""
        if not _quote_supports_amount(f.amount_usd, q):
            continue
        if verify.ground_score(q, corpus) < config.VERIFY_THRESHOLD:
            continue  # quote not found in the source → fabricated
        verified.append(f)
    cleaned = editorial.clean_funding(verified)
    views, _ = _to_views(cleaned)
    if not views:
        return None, None, corpus, ["funding: no round amount could be verified against an authoritative source — left as-is, verify manually"]

    # 3) MERGE: keep the already-high-authority rounds untouched, and add only
    #    the newly-verified rounds that aren't duplicates of a kept round —
    #    never let a partial fresh extraction wipe out good, already-verified data.
    kept_keys = {_dedupe_key(r.label, r.date) for r in high}
    added = [v for v in views if _dedupe_key(v.label, v.date) not in kept_keys]
    merged = high + added

    chart = [p for p in (_chart_point(r) for r in merged) if p is not None]
    chart.sort(key=lambda p: p.date or "")

    domains = ", ".join(sorted({x["domain"] for x in good}))
    warn = (f"funding: corrected {len(low)} low-authority round(s) using "
            f"{len(views)} verified from {domains}")
    log.info(warn)
    return merged, chart, corpus, [warn]
