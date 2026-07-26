from app.agents.authority import authority


def test_high_authority_domains():
    assert authority("https://www.crunchbase.com/organization/grab") == "high"
    assert authority("techcrunch.com") == "high"
    assert authority("https://www.dealstreetasia.com/stories/grab-funding") == "high"
    assert authority("en.wikipedia.org") == "high"


def test_low_authority_blogs():
    assert authority("https://blog.stackademic.com/grab-x") == "low"
    assert authority("https://someone.medium.com/post") == "low"
    assert authority("https://foo.substack.com/p/bar") == "low"
    assert authority("reddit.com") == "low"


def test_unknown_is_medium():
    assert authority("https://randomnews.example/story") == "med"
    assert authority("") == "med"
