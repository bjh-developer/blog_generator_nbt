"""Corrector's quote-support gate: only replace with rounds whose amount is
actually stated in the cited quote."""
from app.agents import corrector
from app.agents.corrector import _CorrectedFunding, _quote_supports_amount
from app.schemas import FundingRound, FundingRoundView, SourceRef


def test_quote_supports_amount():
    assert _quote_supports_amount(30_000_000, "raised a $30 million Series A")
    assert _quote_supports_amount(1_460_000_000, "a $1.46 billion round from SoftBank")
    assert not _quote_supports_amount(10_000_000, "an early US$11.2m cheque")  # 11.2m != 10m
    assert not _quote_supports_amount(350_000_000, "")


async def test_corrector_drops_rounds_not_backed_by_quote(monkeypatch):
    async def fake_search(q, n):
        return [{"url": "https://en.wikipedia.org/wiki/Grab", "domain": "en.wikipedia.org",
                 "title": "Grab", "text": "Grab completed Series A through H. An early US$11.2m cheque."}]
    monkeypatch.setattr(corrector.source, "_firecrawl_search", fake_search)

    async def fake_complete_json(system, user, schema, role="general", temperature=0.2, **kw):
        # model pairs Series A with $10M but the quote says 11.2m — must be dropped
        return _CorrectedFunding(rounds=[
            FundingRound(round="Series A", date="2013", amount_usd=10_000_000,
                         source=SourceRef(quote="An early US$11.2m cheque.",
                                          url="https://en.wikipedia.org/wiki/Grab"))])
    monkeypatch.setattr(corrector.gateway, "complete_json", fake_complete_json)

    low = FundingRoundView(label="Series D", date="2016", amount="$350M",
                           source=SourceRef(url="https://blog.stackademic.com/x"))
    rounds, chart, evidence, warns = await corrector.correct_funding("Grab", [low])
    # nothing quote-verified → keep original (user chose flag over drop), warn
    assert rounds is None
    assert warns and "verify manually" in warns[0]
    # a corpus WAS built and extraction attempted, even though nothing verified —
    # still useful context for a downstream judge
    assert evidence and "Grab completed Series A through H" in evidence
