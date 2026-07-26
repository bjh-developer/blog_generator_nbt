"""Offline tests for the funding corrector — Firecrawl and the LLM are
monkeypatched so no network is used."""
from app.agents import corrector
from app.agents.corrector import _CorrectedFunding
from app.schemas import FundingRound, FundingRoundView, SourceRef


def _low_round():
    return FundingRoundView(label="Series D", date="2016", amount="$350M",
                            source=SourceRef(url="https://blog.stackademic.com/x"))


def _high_round():
    return FundingRoundView(label="Series A", date="2014", amount="$10M",
                            source=SourceRef(url="https://www.crunchbase.com/grab"))


async def test_skips_when_all_high_authority(monkeypatch):
    called = {"search": False}

    async def fake_search(q, n):
        called["search"] = True
        return []
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    rounds, chart, warns = await corrector.correct_funding("Grab", [_high_round()])
    assert rounds is None and warns == []
    assert called["search"] is False  # no search when sources already authoritative


async def test_replaces_low_authority_with_searched(monkeypatch):
    async def fake_search(q, n):
        return [
            {"url": "https://www.crunchbase.com/grab", "domain": "crunchbase.com",
             "title": "Grab funding",
             "text": "Grab raised a $30 million Series A in 2014 from Vertex."},
            {"url": "https://blog.stackademic.com/x", "domain": "stackademic.com",
             "title": "blog", "text": "wrong numbers here"},
        ]
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    async def fake_complete_json(system, user, schema, role="general", temperature=0.2, **kw):
        # authoritative extraction returns the corrected round
        return _CorrectedFunding(rounds=[
            FundingRound(round="Series A", date="2014", amount_usd=30_000_000,
                         source=SourceRef(
                             quote="Grab raised a $30 million Series A in 2014 from Vertex.",
                             url="https://www.crunchbase.com/grab"))])
    # note: the quote appears verbatim in the source text above, so the
    # anti-fabrication ground-check passes
    monkeypatch.setattr(corrector.gateway, "complete_json", fake_complete_json)

    rounds, chart, warns = await corrector.correct_funding("Grab", [_low_round()])
    assert rounds is not None
    assert rounds[0].label == "Series A" and rounds[0].amount == "$30M"
    assert chart and chart[0].value == 30.0
    assert any("REPLACED" in w for w in warns)


async def test_failopen_when_no_authoritative_source(monkeypatch):
    async def fake_search(q, n):
        return [{"url": "https://x.medium.com/p", "domain": "medium.com",
                 "title": "blog", "text": "blah"}]
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    rounds, chart, warns = await corrector.correct_funding("Grab", [_low_round()])
    assert rounds is None  # nothing authoritative → leave original
    assert warns and "no authoritative source" in warns[0]


async def test_failopen_on_search_error(monkeypatch):
    async def boom(q, n):
        raise RuntimeError("firecrawl down")
    monkeypatch.setattr(corrector.source, "_firecrawl_search", boom)

    rounds, chart, warns = await corrector.correct_funding("Grab", [_low_round()])
    assert rounds is None and warns and "left as-is" in warns[0]
