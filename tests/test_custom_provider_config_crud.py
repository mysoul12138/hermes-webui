"""Custom provider config CRUD tests for Settings > Providers."""

import yaml

import api.config as cfg_mod
import api.providers as providers


def _read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_create_custom_provider_writes_providers_slug(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "model": {"provider": "anthropic", "default": "claude-sonnet-4.6"},
                "ui": {"theme": "dark"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_models_cache", lambda *args, **kwargs: None)

    result = providers.upsert_custom_provider_config(
        {
            "name": "Math Model",
            "base_url": "https://llm.mathmodel.tech/v1",
            "api_key": "sk-tes...ider",
            "default_model": "deepseek-ai/DeepSeek-V4-Pro",
            "context_length": 128000,
        }
    )

    assert result == {
        "ok": True,
        "provider": "custom:math-model",
        "slug": "math-model",
        "display_name": "Math Model",
        "action": "created",
    }
    data = _read(config_path)
    assert data["ui"] == {"theme": "dark"}
    assert data["model"] == {"provider": "anthropic", "default": "claude-sonnet-4.6"}
    assert data["providers"]["math-model"] == {
        "name": "Math Model",
        "base_url": "https://llm.mathmodel.tech/v1",
        "api_mode": "openai_compatible",
        "api_key": "sk-tes...ider",
        "model": "deepseek-ai/DeepSeek-V4-Pro",
        "models": ["deepseek-ai/DeepSeek-V4-Pro"],
        "context_length": 128000,
    }


def test_create_custom_provider_uses_base_url_when_name_missing(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_provider_models_cache", lambda *args, **kwargs: None)

    result = providers.upsert_custom_provider_config(
        {
            "name": "",
            "base_url": "https://llm.mathmodel.tech/v1",
            "api_key": "sk-tes...ider",
            "default_model": "deepseek-ai/DeepSeek-V4-Pro",
            "context_length": 128000,
        }
    )

    assert result["ok"] is True
    assert result["display_name"] == "Mathmodel"
    data = _read(config_path)
    assert data["providers"]["mathmodel"]["name"] == "Mathmodel"


def test_create_custom_provider_uses_provider_cache_invalidation(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")
    invalidated = []

    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_provider_models_cache", lambda provider_id: invalidated.append(provider_id))

    result = providers.upsert_custom_provider_config(
        {
            "name": "Math Model",
            "base_url": "https://llm.mathmodel.tech/v1",
            "api_key": "sk-test-custom-provider",
            "default_model": "deepseek-ai/DeepSeek-V4-Pro",
        }
    )

    assert result["ok"] is True
    assert invalidated == ["custom:math-model"]


def test_create_custom_provider_requires_default_model(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_provider_models_cache", lambda _provider_id: None)

    result = providers.upsert_custom_provider_config(
        {
            "name": "Math Model",
            "base_url": "https://llm.mathmodel.tech/v1",
            "api_key": "sk-test-custom-provider",
        }
    )

    assert result == {"ok": False, "error": "default_model is required"}
    assert _read(config_path) == {"providers": {}}


def test_update_custom_provider_preserves_key_and_cleans_legacy_conflict(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "providers": {
                    "math-model": {
                        "name": "Math Model",
                        "base_url": "https://old.example/v1",
                        "api_key": "sk-existing",
                    },
                    "openrouter": {"api_key": "sk-openrouter"},
                },
                "custom_providers": [
                    {
                        "name": "Math Model",
                        "base_url": "https://legacy.example/v1",
                        "api_key": "sk-legacy",
                    },
                    {"name": "Other Provider", "base_url": "https://other.example/v1"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_models_cache", lambda *args, **kwargs: None)

    result = providers.upsert_custom_provider_config(
        {
            "name": "Math Model",
            "base_url": "https://new.example/v1",
            "default_model": "new-model",
        }
    )

    assert result["ok"] is True
    assert result["action"] == "updated"
    data = _read(config_path)
    assert data["providers"]["openrouter"] == {"api_key": "sk-openrouter"}
    assert data["providers"]["math-model"]["api_key"] == "sk-existing"
    assert data["providers"]["math-model"]["base_url"] == "https://new.example/v1"
    assert data["providers"]["math-model"]["model"] == "new-model"
    assert data["providers"]["math-model"]["models"] == ["new-model"]
    assert data["custom_providers"] == [
        {"name": "Other Provider", "base_url": "https://other.example/v1"}
    ]


def test_save_custom_provider_preserves_refreshed_models_after_reload(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_provider_models_cache", lambda _provider_id: None)
    monkeypatch.setattr(providers, "_provider_has_key", lambda provider_id: provider_id == "custom:math-model")

    result = providers.upsert_custom_provider_config(
        {
            "name": "Math Model",
            "base_url": "https://llm.mathmodel.tech/v1",
            "api_key": "sk-test-custom-provider",
            "default_model": "model-b",
            "models": ["model-a", "model-b", "model-a", {"id": "model-c"}],
        }
    )

    assert result["ok"] is True
    data = _read(config_path)
    assert data["providers"]["math-model"]["models"] == ["model-b", "model-a", "model-c"]

    monkeypatch.setattr(
        providers,
        "get_config",
        lambda: {
            "providers": {
                "math-model": data["providers"]["math-model"],
            }
        },
    )
    reloaded = providers.get_providers()
    card = next(p for p in reloaded["providers"] if p["id"] == "custom:math-model")
    assert [m["id"] for m in card["models"]] == ["model-b", "model-a", "model-c"]
    assert card["models_total"] == 3


def test_custom_provider_models_dedupe_canonical_id_not_title(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"providers": {}}), encoding="utf-8")

    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_provider_models_cache", lambda _provider_id: None)
    monkeypatch.setattr(providers, "_provider_has_key", lambda provider_id: provider_id == "custom:math-model")

    result = providers.upsert_custom_provider_config(
        {
            "name": "Math Model",
            "base_url": "https://llm.mathmodel.tech/v1",
            "api_key": "sk-test-custom-provider",
            "default_model": "deepseek-ai/DeepSeek-V4-Pro",
            "models": [
                {"id": "deepseek-ai/DeepSeek-V4-Pro", "title": "DeepSeek V4 Pro"},
                {"id": "deepseek-ai/DeepSeek-V4-Pro", "label": "DeepSeek V4 Pro"},
                {"id": "DEEPSEEK-AI/DEEPSEEK-V4-PRO", "label": "same id, different case"},
                {"model": "deepseek-ai/DeepSeek-V4-Flash", "title": "DeepSeek V4 Flash"},
            ],
        }
    )

    assert result["ok"] is True
    data = _read(config_path)
    assert data["providers"]["math-model"]["models"] == [
        "deepseek-ai/DeepSeek-V4-Pro",
        "deepseek-ai/DeepSeek-V4-Flash",
    ]

    monkeypatch.setattr(
        providers,
        "get_config",
        lambda: {
            "providers": {
                "math-model": data["providers"]["math-model"],
            }
        },
    )
    reloaded = providers.get_providers()
    card = next(p for p in reloaded["providers"] if p["id"] == "custom:math-model")
    assert [m["id"] for m in card["models"]] == [
        "deepseek-ai/DeepSeek-V4-Pro",
        "deepseek-ai/DeepSeek-V4-Flash",
    ]
    assert card["models_total"] == 2


def test_delete_custom_provider_removes_slug_legacy_and_active_model(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "model": {
                    "provider": "custom:math-model",
                    "default": "old-model",
                    "base_url": "https://old.example/v1",
                    "api_key": "sk-model",
                },
                "providers": {
                    "math-model": {"name": "Math Model", "base_url": "https://old.example/v1"},
                    "openrouter": {"api_key": "sk-openrouter"},
                },
                "custom_providers": [
                    {"name": "Math Model", "base_url": "https://legacy.example/v1"},
                    {"name": "Other Provider", "base_url": "https://other.example/v1"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "_get_config_path", lambda: config_path)
    monkeypatch.setattr(providers, "reload_config", lambda: None)
    monkeypatch.setattr(providers, "invalidate_models_cache", lambda *args, **kwargs: None)

    result = providers.delete_custom_provider_config("custom:math-model")

    assert result == {
        "ok": True,
        "provider": "custom:math-model",
        "slug": "math-model",
        "action": "removed",
    }
    data = _read(config_path)
    assert data["providers"] == {"openrouter": {"api_key": "sk-openrouter"}}
    assert data["custom_providers"] == [
        {"name": "Other Provider", "base_url": "https://other.example/v1"}
    ]
    assert data["model"] == {"default": "old-model"}
