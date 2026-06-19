from app.agents import editorial
from app.agents.editorial import _Narratives, _Quadrant
from app.schemas import ResearchDoc, FundingRound, Metric, Source


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
