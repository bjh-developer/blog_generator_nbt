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


def test_low_suffix_match_is_label_bounded():
    # Unrelated domains that merely end with a low-authority domain's
    # characters must NOT be treated as subdomains of it.
    assert authority("cryptomedium.com") == "med"
    assert authority("notsubstack.com") == "med"
    # Genuine subdomains still correctly resolve to low, including the
    # bytebridge.medium.com case (now covered via dot-bounded suffix match
    # on medium.com rather than a redundant explicit entry).
    assert authority("someone.medium.com") == "low"
    assert authority("bytebridge.medium.com") == "low"
