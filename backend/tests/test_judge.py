"""Offline tests for the judge agent — the LLM call is monkeypatched so no
network/model is needed. Verifies warning formatting + the deterministic
funding-grounding path (which must work even without the judge model)."""
from app.agents import judge
from app.agents.judge import (
    _OkVerdict, _LessonVerdict, _LessonVerdicts, _FundingVerdict, _FundingVerdicts,
)
from app.agents.research import _SYS as RESEARCH_SYS
from app.schemas import (
    StoryBrief, StoryMeta, Hero, CoreInsight, LessonCard, Closing,
    FundingSection, FundingRoundView,
)


def _story(**kw):
    base = dict(
        meta=StoryMeta(startup_name="Grab", slug="grab", volume="Vol. 01",
                       category_tag="X", research_date="2026-07-05"),
        hero=Hero(line1="a", line2="b"),
    )
    base.update(kw)
    return StoryBrief(**base)


def _fake_gateway(monkeypatch, *, ok=False):
    async def fake_complete_json(system, user, schema, role="general",
                                 temperature=0.2, **kw):
        name = schema.__name__
        if name == "_OkVerdict":
            return _OkVerdict(ok=ok, reason="restatement")
        if name == "_LessonVerdicts":
            return _LessonVerdicts(verdicts=[
                _LessonVerdict(index=0, quality_ok=True, safety_ok=False, reason="endorses disownment"),
            ])
        if name == "_FundingVerdicts":
            return _FundingVerdicts(verdicts=[
                _FundingVerdict(index=0, supported=False, reason="Series/year mismatch"),
            ])
        return schema()
    monkeypatch.setattr(judge.gateway, "complete_json", fake_complete_json)


async def test_review_flags_insight_lesson_closing_funding(monkeypatch):
    _fake_gateway(monkeypatch, ok=False)  # insight + closing judged bad
    sb = _story(
        core_insight=CoreInsight(title="t", statement="He was already rich.", narrative="n"),
        lessons=[LessonCard(number=1, headline="Get disowned", body="Let family cut you off.",
                            applicable_to="founders")],
        closing=Closing(title="The NBT take", narrative="He was already rich."),
        funding=FundingSection(title="F", rounds=[
            FundingRoundView(label="Series D", date="2016", amount="$350M")]),
    )
    warns = await judge.review(sb, corpus="unrelated corpus text with no figures")
    joined = " | ".join(warns)
    assert "insight:" in joined
    assert "lesson 1: SAFETY" in joined
    assert "closing:" in joined
    assert "funding:" in joined and "Series D" in joined


async def test_review_clean_story_no_warnings(monkeypatch):
    _fake_gateway(monkeypatch, ok=True)  # insight + closing judged good

    async def all_good(system, user, schema, role="general", temperature=0.2, **kw):
        name = schema.__name__
        if name == "_OkVerdict":
            return _OkVerdict(ok=True)
        if name == "_LessonVerdicts":
            return _LessonVerdicts(verdicts=[_LessonVerdict(index=0)])
        if name == "_FundingVerdicts":
            return _FundingVerdicts(verdicts=[_FundingVerdict(index=0, supported=True)])
        return schema()
    monkeypatch.setattr(judge.gateway, "complete_json", all_good)

    # corpus literally contains the amount so grounding passes
    sb = _story(
        core_insight=CoreInsight(title="t", statement="They made listing feel like posting a story.", narrative="n"),
        funding=FundingSection(title="F", rounds=[
            FundingRoundView(label="Series D", date="2016", amount="$350M")]),
    )
    warns = await judge.review(sb, corpus="Grab raised a $350M Series D in 2016.")
    assert warns == []


async def test_funding_grounding_flags_absent_amount_without_llm(monkeypatch):
    # judge LLM unavailable → only the deterministic grounding pass runs
    async def boom(*a, **k):
        raise judge.gateway.LLMError("down")
    monkeypatch.setattr(judge.gateway, "complete_json", boom)

    sb = _story(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="Series D", date="2016", amount="$350M")]))
    warns = await judge.review(sb, corpus="This article never mentions that number.")
    assert any("funding:" in w and "not found in sources" in w for w in warns)


def test_research_prompt_has_span_lock():
    assert "SPAN LOCK" in RESEARCH_SYS
