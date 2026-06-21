import importlib


def test_config_cf_defaults(monkeypatch):
    monkeypatch.delenv("MODEL_FAST", raising=False)
    monkeypatch.delenv("MODEL_GENERAL", raising=False)
    monkeypatch.delenv("MODEL_REASONING", raising=False)
    monkeypatch.delenv("MODEL_FALLBACK", raising=False)
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    from app import config
    importlib.reload(config)
    assert config.MODEL_FAST == "@cf/meta/llama-3.1-8b-instruct"
    assert config.MODEL_GENERAL == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert config.MODEL_REASONING == config.MODEL_GENERAL
    assert config.MODEL_FALLBACK == "openrouter/owl-alpha"
    assert hasattr(config, "CF_ACCOUNT_ID")
    assert hasattr(config, "CF_API_TOKEN")


from app.llm import gateway
from app import config


def test_provider_for_cloudflare(monkeypatch):
    monkeypatch.setattr(config, "CF_ACCOUNT_ID", "acct123")
    monkeypatch.setattr(config, "CF_API_TOKEN", "cftok")
    url, headers = gateway._provider_for("@cf/meta/llama-3.1-8b-instruct")
    assert url == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer cftok"


def test_provider_for_openrouter(monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "orkey")
    monkeypatch.setattr(config, "OPENROUTER_BASE", "https://openrouter.ai/api/v1")
    url, headers = gateway._provider_for("openrouter/owl-alpha")
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer orkey"
