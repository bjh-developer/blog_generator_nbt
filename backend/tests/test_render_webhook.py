"""Contract tests for the async webhook mode + auth + SSRF guard added for the
NextBigThing admin. Mocks the pipeline so no LLM/Firecrawl calls happen.
"""
import pytest
from starlette.testclient import TestClient

from app import config, main, schemas


def _brief(with_content: bool = True) -> schemas.StoryBrief:
    b = schemas.StoryBrief(
        meta=schemas.StoryMeta(
            startup_name="Acme", slug="acme", volume="VOL. 1",
            category_tag="SaaS", research_date="2026-01-01",
        ),
        hero=schemas.Hero(line1="How did Acme", line2="win?", subheadline="A story"),
    )
    if with_content:
        b.lessons = [schemas.LessonCard(number=1, headline="Ship fast")]
        b.sources = [schemas.SourceRef(quote="q", outlet="Wired", url="https://x")]
    return b


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_SHARED_SECRET", "sekret")
    monkeypatch.setattr(config, "CALLBACK_ALLOWLIST", {"localhost"})
    captured: list[tuple[str, dict]] = []

    async def fake_cb(url, payload):
        captured.append((url, payload))

    monkeypatch.setattr(main, "_post_callback", fake_cb)
    return captured


def _mock_pipeline(monkeypatch, brief, errors=None, warnings=None):
    async def fake_gen(query, max_sources=8):
        return brief, errors or [], warnings or []
    monkeypatch.setattr(main.pipeline, "generate", fake_gen)


AUTH = {"authorization": "Bearer sekret"}
CB = "http://localhost:3000/api/webhooks/generation"


def test_missing_auth_rejected(env):
    c = TestClient(main.app)
    r = c.post("/generate", json={"query": "Acme", "job_id": "j1", "callback_url": CB})
    assert r.status_code == 401


def test_async_success_posts_draft_callback(env, monkeypatch):
    _mock_pipeline(monkeypatch, _brief(True), warnings=["w1"])
    c = TestClient(main.app)
    r = c.post("/generate", headers=AUTH, json={"query": "Acme", "job_id": "j1", "callback_url": CB})
    assert r.status_code == 202
    assert r.json()["status"] == "running"
    # TestClient runs the BackgroundTask before returning.
    assert len(env) == 1
    url, payload = env[0]
    assert url == CB
    assert payload["ok"] is True
    assert payload["job_id"] == "j1"
    assert payload["slug"] == "acme"
    assert payload["brief"]["status"] == "draft"
    assert payload["brief"]["meta"]["startup_name"] == "Acme"


def test_empty_shell_callback_fails(env, monkeypatch):
    _mock_pipeline(monkeypatch, _brief(with_content=False))
    c = TestClient(main.app)
    r = c.post("/generate", headers=AUTH, json={"query": "Acme", "job_id": "j2", "callback_url": CB})
    assert r.status_code == 202
    _, payload = env[0]
    assert payload["ok"] is False
    assert payload["error"] == "empty_shell"


def test_qa_errors_callback_fails(env, monkeypatch):
    _mock_pipeline(monkeypatch, _brief(True), errors=["fabricated stat"])
    c = TestClient(main.app)
    r = c.post("/generate", headers=AUTH, json={"query": "Acme", "job_id": "j3", "callback_url": CB})
    assert r.status_code == 202
    _, payload = env[0]
    assert payload["ok"] is False
    assert payload["qa_errors"] == ["fabricated stat"]


def test_ssrf_callback_rejected(env, monkeypatch):
    _mock_pipeline(monkeypatch, _brief(True))
    c = TestClient(main.app)
    # cloud metadata host, not in allowlist -> 400, no job scheduled
    r = c.post("/generate", headers=AUTH, json={
        "query": "Acme", "job_id": "j4", "callback_url": "http://169.254.169.254/latest/",
    })
    assert r.status_code == 400
    assert env == []


def test_sync_mode_returns_brief(env, monkeypatch):
    _mock_pipeline(monkeypatch, _brief(True), warnings=["w"])
    c = TestClient(main.app)
    r = c.post("/generate", headers=AUTH, json={"query": "Acme"})
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "acme"
    assert body["brief"]["status"] == "draft"


def test_health(env):
    c = TestClient(main.app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["auth_required"] is True
