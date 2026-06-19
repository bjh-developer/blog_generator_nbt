from app import qa
from app.schemas import (
    StoryBrief, StoryMeta, Hero, FundingSection, FundingRoundView, FundingPoint,
    TimelineSection, TimelineItem, CompetitorSection, QuadrantItem,
)


def _comp(quads, axis_x="Desktop-first → Mobile-first", axis_y="Utility → Entertainment"):
    return CompetitorSection(title="Map", axis_x=axis_x, axis_y=axis_y, quadrants=quads)


def _brief(**kw) -> StoryBrief:
    base = dict(
        meta=StoryMeta(startup_name="Luma", slug="luma", volume="Vol. 01",
                       category_tag="X", research_date="2026-06-14"),
        hero=Hero(line1="Luma didn't build a platform.", line2="They built trust."),
    )
    base.update(kw)
    return StoryBrief(**base)


def test_clean_story_has_no_issues():
    errors, warnings = qa.split(qa.audit(_brief()))
    assert errors == [] and warnings == []


def test_duplicate_funding_round_is_error():
    sb = _brief(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="First funding round", date="2012", amount="$1.5M"),
        FundingRoundView(label="First funding round", date="2012", amount="$1.5M"),
    ], chart=[FundingPoint(label="First funding round", value=1.5)]))
    errors, _ = qa.split(qa.audit(sb))
    assert any("duplicate round label" in e for e in errors)


def test_out_of_order_funding_is_error():
    # the image bug: 2011 round listed after 2012
    sb = _brief(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="First funding round", date="2012", amount="$1.5M"),
        FundingRoundView(label="Early investor support", date="2011"),
    ], chart=[FundingPoint(label="First funding round", value=1.5)]))
    errors, _ = qa.split(qa.audit(sb))
    assert any("out of chronological order" in e for e in errors)


def test_round_missing_amount_is_warning_not_error():
    sb = _brief(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="Seed", date="2012", amount="$1.5M"),
        FundingRoundView(label="Early investor support", date="2013"),
    ], chart=[FundingPoint(label="Seed", value=1.5)]))
    errors, warnings = qa.split(qa.audit(sb))
    assert any("missing an amount" in w for w in warnings)
    assert not any("missing an amount" in e for e in errors)   # advisory only


def test_valuation_drop_is_error():
    sb = _brief(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="Series A", date="2015", valuation="$3.2B"),
        FundingRoundView(label="Series B", date="2018", valuation="$1B"),
    ], chart=[]))
    errors, _ = qa.split(qa.audit(sb))
    assert any("valuation drops" in e for e in errors)


def test_competitor_map_clean_like_the_image():
    # the Shopee map: 4 distinct names, 1 winner, distinct cells, labeled axes
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Lazada", quadrant="tl"),
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Tokopedia", quadrant="bl"),
        QuadrantItem(name="TikTok Shop", quadrant="br"),
    ]))
    errors, warnings = qa.split(qa.audit(sb))
    assert errors == [] and warnings == []


def test_competitor_duplicate_label_is_error():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Shopee", quadrant="bl"),
    ]))
    errors, _ = qa.split(qa.audit(sb))
    assert any("duplicate label" in e for e in errors)


def test_competitor_same_cell_is_warning():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Lazada", quadrant="tr"),
    ]))
    errors, warnings = qa.split(qa.audit(sb))
    assert any("share cell" in w for w in warnings)
    assert not any("share cell" in e for e in errors)


def test_competitor_winner_count_is_error():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Lazada", quadrant="tl", winner=True),
    ]))
    errors, _ = qa.split(qa.audit(sb))
    assert any("expected exactly 1 winner" in e for e in errors)


def test_competitor_missing_axis_is_warning():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Lazada", quadrant="tl"),
    ], axis_x=""))
    errors, warnings = qa.split(qa.audit(sb))
    assert any("axis label missing" in w for w in warnings)


def test_timeline_out_of_order_is_error():
    sb = _brief(timeline=TimelineSection(title="T", events=[
        TimelineItem(year="2015", kind="product", heading="b"),
        TimelineItem(year="2012", kind="founder_story", heading="a"),
    ]))
    errors, _ = qa.split(qa.audit(sb))
    assert any("timeline: events out of chronological order" in e for e in errors)


# --- auto-repair -----------------------------------------------------------

def test_repair_disambiguates_duplicate_funding_label():
    # the Carousell bug: two "Series C" in different years
    sb = _brief(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="Series C", date="2017", amount="$20M"),
        FundingRoundView(label="Series C", date="2019", amount="$80M"),
    ], chart=[FundingPoint(label="Series C", value=20.0, date="2017"),
              FundingPoint(label="Series C", value=80.0, date="2019")]))
    assert qa.split(qa.audit(sb))[0]            # has errors before
    sb = qa.repair(sb)
    errors, _ = qa.split(qa.audit(sb))
    assert errors == []                          # fixed
    labels = [r.label for r in sb.funding.rounds]
    assert len(set(labels)) == 2                 # now unique
    assert set(p.label for p in sb.funding.chart) == set(labels)   # chart synced


def test_repair_enforces_single_winner():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Lazada", quadrant="tl", winner=True),
    ]))
    sb = qa.repair(sb)
    assert sum(q.winner for q in sb.competitors.quadrants) == 1
    assert qa.split(qa.audit(sb))[0] == []


def test_repair_caps_competitors_to_four():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="A", quadrant="tl"),
        QuadrantItem(name="B", quadrant="bl"),
        QuadrantItem(name="C", quadrant="br"),
        QuadrantItem(name="D", quadrant="tl"),
        QuadrantItem(name="Winner", quadrant="br", winner=True),
    ]))
    sb = qa.repair(sb)
    quads = sb.competitors.quadrants
    assert len(quads) == 4
    assert any(q.winner and q.name == "Winner" for q in quads)   # winner survived the cap
    cells = [q.quadrant for q in quads]
    assert len(set(cells)) == len(cells)                          # unique cells
    assert qa.split(qa.audit(sb))[0] == []                        # clean after repair


def test_repair_syncs_chart_label_for_same_date_duplicates():
    sb = _brief(funding=FundingSection(title="F", rounds=[
        FundingRoundView(label="Series C", date="2017", amount="$20M"),
        FundingRoundView(label="Series C", date="2017", amount="$80M"),
    ], chart=[FundingPoint(label="Series C", value=20.0, date="2017"),
              FundingPoint(label="Series C", value=80.0, date="2017")]))
    sb = qa.repair(sb)
    chart_labels = sorted(p.label for p in sb.funding.chart)
    round_labels = sorted(r.label for r in sb.funding.rounds)
    assert chart_labels == round_labels          # no collapse to one label
    assert len(set(chart_labels)) == 2           # both points distinctly labeled


def test_repair_forces_winner_into_tr():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Carousell", quadrant="br", winner=True),
        QuadrantItem(name="eBay", quadrant="tl"),
    ]))
    sb = qa.repair(sb)
    winner = next(q for q in sb.competitors.quadrants if q.winner)
    assert winner.quadrant == "tr"


def test_repair_reassigns_colliding_cells_to_unique():
    # the Carousell bug: eBay + forums both in tl
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Carousell", quadrant="br", winner=True),
        QuadrantItem(name="eBay", quadrant="tl"),
        QuadrantItem(name="Forums", quadrant="tl"),
        QuadrantItem(name="Facebook Marketplace", quadrant="bl"),
    ]))
    sb = qa.repair(sb)
    cells = [q.quadrant for q in sb.competitors.quadrants]
    assert len(set(cells)) == len(cells)           # all unique cells
    assert qa.split(qa.audit(sb))[0] == []         # no errors remain


def test_repair_drops_duplicate_competitor():
    sb = _brief(competitors=_comp([
        QuadrantItem(name="Shopee", quadrant="tr", winner=True),
        QuadrantItem(name="Shopee", quadrant="bl"),
    ]))
    sb = qa.repair(sb)
    assert len(sb.competitors.quadrants) == 1
    assert qa.split(qa.audit(sb))[0] == []


def test_repair_clears_accent_word_not_in_headline():
    sb = _brief(hero=Hero(line1="Luma built a platform.", line2="For events.",
                          accent_word_orange="trust"))
    sb = qa.repair(sb)
    assert sb.hero.accent_word_orange is None
    assert qa.split(qa.audit(sb))[0] == []


def test_repair_sorts_timeline():
    sb = _brief(timeline=TimelineSection(title="T", events=[
        TimelineItem(year="2015", kind="product", heading="b"),
        TimelineItem(year="2012", kind="founder_story", heading="a"),
    ]))
    sb = qa.repair(sb)
    assert [e.year for e in sb.timeline.events] == ["2012", "2015"]


def test_accent_word_not_in_headline_is_error():
    sb = _brief(hero=Hero(line1="Luma built a platform.", line2="For events.",
                          accent_word_orange="trust"))
    errors, _ = qa.split(qa.audit(sb))
    assert any("accent word" in e for e in errors)
