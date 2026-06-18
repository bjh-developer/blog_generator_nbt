from app.agents import research
from app.schemas import ResearchDoc


def test_merge_research_prefers_nonnull_and_concats_lists():
    doc = research._merge("Luma", [
        {"startup_name": "Luma", "tagline": None, "timeline": [
            {"date": "2020", "kind": "founder_story", "event": "Founded", "significance": "x"}]},
        {"startup_name": "Luma", "tagline": "Event OS", "metrics": [
            {"label": "Hosts", "value": "250K+"}]},
    ])
    assert isinstance(doc, ResearchDoc)
    assert doc.tagline == "Event OS"
    assert len(doc.timeline) == 1
    assert doc.metrics[0].value == "250K+"


def test_merge_empty_partials():
    doc = research._merge("Acme", [])
    assert doc.startup_name == "Acme"
    assert doc.timeline == []
