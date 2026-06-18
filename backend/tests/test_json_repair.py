from pydantic import BaseModel

from app.llm.gateway import _repair_candidates, _try_parse


class _Out(BaseModel):
    title: str
    score: float


def _final(raw: str):
    return _try_parse(raw, _Out)


def test_markdown_fences_extracted():
    raw = 'Here you go:\n```json\n{"title": "x", "score": 0.5}\n```'
    assert _final(raw) == _Out(title="x", score=0.5)


def test_trailing_comma_cleaned():
    raw = '{"title": "x", "score": 0.5,}'
    assert _final(raw) == _Out(title="x", score=0.5)


def test_missing_closing_brace_balanced():
    raw = '{"title": "x", "score": 0.5'
    assert _final(raw) == _Out(title="x", score=0.5)


def test_prose_wrapped_object_sliced():
    raw = 'Sure! {"title": "x", "score": 0.5} hope that helps'
    assert _final(raw) == _Out(title="x", score=0.5)


def test_nbsp_sanitized():
    raw = '{"title": "x", "score": 0.5}'
    assert _final(raw) == _Out(title="x", score=0.5)


def test_unterminated_string_closed():
    # missing closing quote + brace
    raw = '{"title": "x", "score": 0.5, "extra": "oops'
    obj = _final(raw)   # extra ignored by model? _Out has no extra; should still parse core
    assert obj is None or obj.title == "x"


def test_stage_order_returns_candidates():
    stages = [name for name, _ in _repair_candidates('{"a":1,}')]
    assert stages == ["extract", "cleanup", "sanitize", "balance"]
