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

    rounds, chart, evidence, warns = await corrector.correct_funding("Grab", [_high_round()])
    assert rounds is None and warns == []
    assert evidence is None  # nothing needed correction
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

    rounds, chart, evidence, warns = await corrector.correct_funding("Grab", [_low_round()])
    assert rounds is not None
    assert rounds[0].label == "Series A" and rounds[0].amount == "$30M"
    assert chart and chart[0].value == 30.0
    assert evidence and "Vertex" in evidence
    assert any("corrected" in w for w in warns)


async def test_failopen_when_no_authoritative_source(monkeypatch):
    async def fake_search(q, n):
        return [{"url": "https://x.medium.com/p", "domain": "medium.com",
                 "title": "blog", "text": "blah"}]
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    rounds, chart, evidence, warns = await corrector.correct_funding("Grab", [_low_round()])
    assert rounds is None  # nothing authoritative → leave original
    assert evidence is None
    assert warns and "no authoritative source" in warns[0]


async def test_failopen_on_search_error(monkeypatch):
    async def boom(q, n):
        raise RuntimeError("firecrawl down")
    monkeypatch.setattr(corrector.source, "_firecrawl_search", boom)

    rounds, chart, evidence, warns = await corrector.correct_funding("Grab", [_low_round()])
    assert rounds is None and warns and "left as-is" in warns[0]
    assert evidence is None


async def test_merge_preserves_high_authority_round(monkeypatch):
    """The core fix: correcting one low-authority round must not wipe out a
    round that was already sourced from a high-authority domain."""
    async def fake_search(q, n):
        return [
            {"url": "https://www.crunchbase.com/grab", "domain": "crunchbase.com",
             "title": "Grab funding",
             "text": "Grab raised a $50 million Series B in 2015 led by GGV Capital."},
        ]
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    async def fake_complete_json(system, user, schema, role="general", temperature=0.2, **kw):
        # extraction verifies a DIFFERENT round (Series B/2015) than either the
        # kept high round (Series A/2014) or the low round being corrected (Series D/2016)
        return _CorrectedFunding(rounds=[
            FundingRound(round="Series B", date="2015", amount_usd=50_000_000,
                         source=SourceRef(
                             quote="Grab raised a $50 million Series B in 2015 led by GGV Capital.",
                             url="https://www.crunchbase.com/grab"))])
    monkeypatch.setattr(corrector.gateway, "complete_json", fake_complete_json)

    high = _high_round()  # Series A, 2014, Crunchbase (already high-authority)
    low = _low_round()    # Series D, 2016, blog (low-authority)
    rounds, chart, evidence, warns = await corrector.correct_funding("Grab", [high, low])

    assert rounds is not None
    labels = {(r.label, r.date) for r in rounds}
    assert ("Series A", "2014") in labels  # original high-authority round preserved
    assert ("Series B", "2015") in labels  # newly verified round merged in

    kept = next(r for r in rounds if r.label == "Series A")
    assert kept.amount == "$10M" and kept.source.url == high.source.url  # untouched


async def test_warning_counts_only_low_authority_rounds(monkeypatch):
    """current has 2 rounds total but only 1 is low-authority — the warning
    must say '1', not '2'."""
    async def fake_search(q, n):
        return [
            {"url": "https://www.crunchbase.com/grab", "domain": "crunchbase.com",
             "title": "Grab funding",
             "text": "Grab raised a $350 million Series D in 2016."},
        ]
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    async def fake_complete_json(system, user, schema, role="general", temperature=0.2, **kw):
        return _CorrectedFunding(rounds=[
            FundingRound(round="Series D", date="2016", amount_usd=350_000_000,
                         source=SourceRef(
                             quote="Grab raised a $350 million Series D in 2016.",
                             url="https://www.crunchbase.com/grab"))])
    monkeypatch.setattr(corrector.gateway, "complete_json", fake_complete_json)

    rounds, chart, evidence, warns = await corrector.correct_funding(
        "Grab", [_high_round(), _low_round()])
    assert warns and "1 low-authority round" in warns[0]
    assert "2 low-authority round" not in warns[0]
