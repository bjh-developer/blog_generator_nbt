from app.agents import source


def test_dedupe_drops_same_url():
    arts = [
        {"url": "http://a.com/x?utm=1", "title": "Story A"},
        {"url": "http://a.com/x?utm=2", "title": "Story A"},
        {"url": "http://b.com/y", "title": "Different"},
    ]
    out = source._dedupe(arts)
    assert len(out) == 2


def test_dedupe_drops_near_duplicate_titles():
    arts = [
        {"url": "http://a.com/1", "title": "Acme raises 40M in Series B funding round"},
        {"url": "http://b.com/2", "title": "Acme raises 40M in Series B funding round!"},
    ]
    assert len(source._dedupe(arts)) == 1


def test_pick_arc_majority():
    assert source.pick_arc(["cautionary", "cautionary", "success"]) == "cautionary"
    assert source.pick_arc(["success", "success", "cautionary"]) == "success"
    assert source.pick_arc(["reject", "reject"]) == "success"   # default


def test_classify_sys_includes_target():
    from app.agents.source import _classify_sys
    sys = _classify_sys("Luma AI")
    assert "Luma AI" in sys                      # entity threaded in
    assert "DIFFERENT" in sys                     # rejects same-name impostors
    for label in ("success", "cautionary", "reject"):
        assert label in sys
