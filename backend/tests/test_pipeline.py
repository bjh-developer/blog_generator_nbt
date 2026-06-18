from app import pipeline
from app.schemas import StoryBrief, StoryMeta, Hero


def test_write_story_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.config, "CONTENT_DIR", tmp_path)
    sb = StoryBrief(
        meta=StoryMeta(startup_name="Luma", slug="luma", volume="Vol. 01",
                       category_tag="X", research_date="2026-06-14"),
        hero=Hero(line1="a", line2="b"))
    path = pipeline.write_story(sb)
    assert path.name == "luma.json"
    assert (tmp_path / "luma.json").exists()
    assert '"slug": "luma"' in (tmp_path / "luma.json").read_text()


def test_main_imports():
    # ensure FastAPI app wiring is importable (no stale symbols)
    import app.main as m
    assert m.app is not None
