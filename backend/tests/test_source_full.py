from app.agents.source import _normalize_results


def test_normalize_keeps_full_markdown():
    raw = {"data": {"web": [
        {"url": "https://x.com/a", "title": "A", "markdown": "M" * 5000,
         "metadata": {"title": "A"}},
    ]}}
    out = _normalize_results(raw)
    assert len(out) == 1
    assert len(out[0]["text"]) == 5000          # full content, not truncated
    assert out[0]["domain"] == "x.com"


def test_normalize_flat_list_and_fallbacks():
    raw = {"data": [{"url": "https://y.org/p", "metadata": {"title": "Y"},
                     "description": "snippet only"}]}
    out = _normalize_results(raw)
    assert out[0]["title"] == "Y"
    assert out[0]["text"] == "snippet only"     # falls back to description
