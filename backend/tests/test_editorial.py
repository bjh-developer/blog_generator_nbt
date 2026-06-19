from app.agents import editorial
from app.agents.editorial import _Narratives, _Quadrant, _TimelineN
from app.schemas import ResearchDoc, FundingRound, Metric, Source, TimelineEvent


def test_slugify():
    assert editorial.slugify("Luma.com") == "luma-com"
    assert editorial.slugify("ShopBack!") == "shopback"


def test_funding_chart_normalizes_to_millions_sorted():
    rd = ResearchDoc(startup_name="Luma", funding=[
        FundingRound(round="Series A", date="2022", amount_usd=30_000_000),
        FundingRound(round="Seed", date="2020", amount_usd=3_000_000)])
    pts = editorial.funding_chart(rd)
    assert [p.value for p in pts] == [3.0, 30.0]      # sorted by date
    assert pts[0].unit == "$M"


def test_stat_bar_from_metrics_capped_at_4():
    rd = ResearchDoc(startup_name="Luma", metrics=[
        Metric(label=f"M{i}", value=f"{i}") for i in range(6)])
    assert len(editorial.stat_bar(rd)) == 4


def test_normalize_stat_compresses_units():
    f = editorial.normalize_stat_value
    assert f("$1.1 billion") == "$1.1B"
    assert f("42 million") == "42M"
    assert f("Over $42 billion") == ">$42B"      # quantifier + unit both applied


def test_compress_units_requires_digit_before():
    f = editorial.normalize_stat_value
    assert f("half a million") == "half a million"   # no digit -> not compressed
    assert f("$5mn") == "$5M"                         # digit-attached -> compressed


def test_stat_bar_drops_non_numeric_values():
    rd = ResearchDoc(startup_name="X", metrics=[
        Metric(label="Monthly active users", value="half a million"),  # -> dropped (len/non-num)
        Metric(label="First customers", value="10"),                   # kept (numeric)
        Metric(label="Raised", value="$30M"),
    ])
    vals = [s.value for s in editorial.stat_bar(rd)]
    assert "10" in vals and "$30M" in vals
    assert not any("aM" in v for v in vals)          # the "half aM" bug is gone


def test_stat_bar_drops_overlong_prose_values():
    rd = ResearchDoc(startup_name="Carousell", metrics=[
        Metric(label="App Store Ranking", value="Top 2 Free Lifestyle App in Singapore"),
        Metric(label="Valuation", value="$1.1 billion"),
    ])
    bar = editorial.stat_bar(rd)
    vals = [s.value for s in bar]
    assert "$1.1B" in vals
    assert all(len(v) <= 12 for v in vals)        # prose stat dropped


def test_clean_funding_drops_junk_amountless_dedupes_sorts():
    funding = [
        FundingRound(round="", date="", amount_usd=None),                       # junk: empty
        FundingRound(round="Multiple rounds (unspecified)", date="2012-2019",
                     valuation_usd=550_000_000),                                # junk label
        FundingRound(round="Grant", date="2012", amount_usd=None),             # no amount
        FundingRound(round="Series C", date="2017", amount_usd=85_000_000),
        FundingRound(round="Series C (2017)", date="2017"),                    # dup, no amount
        FundingRound(round="Seed", date="2013", amount_usd=800_000),
    ]
    out = editorial.clean_funding(funding)
    labels = [f.round for f in out]
    assert labels == ["Seed", "Series C"]            # junk + amount-less gone, sorted by date
    assert all(f.amount_usd for f in out)


def test_clean_funding_backfills_amount_from_duplicate():
    funding = [
        FundingRound(round="Series A", date="2014"),                  # no amount
        FundingRound(round="Series A (2014)", date="2014", amount_usd=7_800_000),
    ]
    out = editorial.clean_funding(funding)
    assert len(out) == 1
    assert out[0].amount_usd == 7_800_000            # backfilled before amount-less drop


def test_assemble_uses_llm_timeline_events_when_present():
    rd = ResearchDoc(startup_name="Luma")
    nar = _Narratives(hero_line1="a", hero_line2="b", timeline_events=[
        _TimelineN(year="2020", kind="founder_story", heading="The itch to scratch",
                   body="Built a tool for a friend."),
        _TimelineN(year="2023", kind="funding", heading="Series A: $30M",
                   body="Funded the shift to community OS."),
    ])
    sb = editorial.assemble(rd, nar, [])
    assert sb.timeline is not None
    assert [e.heading for e in sb.timeline.events] == ["The itch to scratch", "Series A: $30M"]
    assert sb.timeline.events[0].kind == "founder_story"


def test_assemble_falls_back_to_deterministic_timeline():
    rd = ResearchDoc(startup_name="Luma", timeline=[
        TimelineEvent(date="2020", kind="product", event="ship v1")])
    nar = _Narratives(hero_line1="a", hero_line2="b")     # no timeline_events
    sb = editorial.assemble(rd, nar, [])
    assert sb.timeline is not None
    assert sb.timeline.events[0].heading == "ship v1"      # deterministic fallback


def test_assemble_coerces_invalid_timeline_kind():
    rd = ResearchDoc(startup_name="Luma")
    nar = _Narratives(hero_line1="a", hero_line2="b", timeline_events=[
        _TimelineN(year="2020", kind="bogus", heading="x", body="y")])
    sb = editorial.assemble(rd, nar, [])
    assert sb.timeline.events[0].kind == "product"


def test_timeline_items_fallback_prioritizes_and_caps():
    rd = ResearchDoc(startup_name="Luma", timeline=[
        TimelineEvent(date="2018", kind="product", event="ship v1"),
        TimelineEvent(date="2019", kind="product", event="ship v2"),
        TimelineEvent(date="2020", kind="inflection", event="near death pivot"),
        TimelineEvent(date="2021", kind="product", event="ship v3"),
        TimelineEvent(date="2022", kind="founder_story", event="the original bet"),
        TimelineEvent(date="2023", kind="product", event="ship v4"),
    ])
    items = editorial.timeline_items(rd, max_items=3)
    kinds = {it.kind for it in items}
    assert "inflection" in kinds and "founder_story" in kinds
    assert len(items) == 3
    assert [it.year for it in items] == sorted(it.year for it in items)


def test_assemble_omits_unsupported_sections():
    rd = ResearchDoc(startup_name="Luma")          # no funding/competitors/timeline
    nar = _Narratives(hero_line1="Luma didn't build an event platform.",
                      hero_line2="They built infrastructure for identities.",
                      accent_word_orange="infrastructure")
    sources = [Source(id="s0", url="http://x", title="t")]
    sb = editorial.assemble(rd, nar, sources)
    assert sb.funding is None
    assert sb.competitors is None
    assert sb.timeline is None
    assert sb.hero.accent_word_orange == "infrastructure"


def test_assemble_builds_competitor_quadrants():
    rd = ResearchDoc(startup_name="Luma")
    nar = _Narratives(hero_line1="a", hero_line2="b",
                      quadrants=[_Quadrant(name="Luma", quadrant="tr", winner=True),
                                 _Quadrant(name="Eventbrite", quadrant="bl")])
    sb = editorial.assemble(rd, nar, [])
    assert sb.competitors is not None
    assert sb.competitors.quadrants[0].winner is True
