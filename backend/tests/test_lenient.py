from app.schemas import Founder, ResearchDoc
from app.agents.editorial import _Narratives


def test_null_string_coerced_to_default():
    # model sent background: null for a str field -> coerced to ""
    f = Founder.model_validate({"name": "Brian", "role": "CEO", "background": None})
    assert f.background == ""


def test_researchdoc_null_lists_ok():
    rd = ResearchDoc.model_validate({"startup_name": "Airbnb", "founders": [
        {"name": "Brian", "background": None, "why": None}]})
    assert rd.founders[0].background == ""


def test_narratives_flattens_nested_hero():
    raw = {
        "hero": {"line1": "Airbnb didn't build a hotel.",
                 "line2": "They built a trust engine.",
                 "accent_word_orange": "trust"},
        "subheadline": "x",
        "lessons": [{"headline": "Ship trust first"}],
    }
    n = _Narratives.model_validate(raw)
    assert n.hero_line1 == "Airbnb didn't build a hotel."
    assert n.hero_line2 == "They built a trust engine."
    assert n.accent_word_orange == "trust"


def test_narratives_drops_junk_quadrant_entries():
    # model emitted broken array items like {"{": ","} -> must be dropped, not fail
    raw = {"hero_line1": "a", "hero_line2": "b",
           "quadrants": [{"name": "Airbnb", "quadrant": "tr", "winner": True},
                         {"{": ","}, {"name": "Hotels", "quadrant": "bl"}],
           "lessons": [{"headline": "Good"}, {"junk": 1}]}
    n = _Narratives.model_validate(raw)
    assert [q.name for q in n.quadrants] == ["Airbnb", "Hotels"]
    assert [l.headline for l in n.lessons] == ["Good"]


def test_narratives_quadrants_dict_to_list():
    raw = {"hero_line1": "a", "hero_line2": "b",
           "competitor": {"axis_x": "scale", "axis_y": "design",
                          "quadrants": {"Airbnb": {"quadrant": "tr", "winner": True},
                                        "Hotels": {"quadrant": "bl"}}}}
    n = _Narratives.model_validate(raw)
    assert n.axis_x == "scale"
    names = {q.name for q in n.quadrants}
    assert names == {"Airbnb", "Hotels"}
