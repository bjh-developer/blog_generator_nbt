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
