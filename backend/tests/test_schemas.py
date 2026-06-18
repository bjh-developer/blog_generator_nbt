from app.schemas import ResearchDoc, StoryBrief, StoryMeta, Hero, StatItem


def test_storybrief_minimal_valid():
    sb = StoryBrief(
        meta=StoryMeta(startup_name="Luma", slug="luma", volume="Vol. 01",
                       category_tag="Community Infrastructure", research_date="2026-06-14"),
        hero=Hero(line1="Luma didn't build an event platform.",
                  line2="They built infrastructure for identities.",
                  accent_word_orange="infrastructure", accent_word_purple="identities",
                  subheadline="How a calendar tool became the OS for startup communities.",
                  stat_bar=[StatItem(value="5M+", label="Monthly Attendees")]),
        lessons=[],
    )
    assert sb.meta.slug == "luma"
    assert sb.hero.stat_bar[0].value == "5M+"
    assert sb.competitors is None        # optional sections omitted from UI


def test_researchdoc_allows_nulls():
    rd = ResearchDoc(startup_name="Luma")
    assert rd.tagline is None
    assert rd.timeline == []
