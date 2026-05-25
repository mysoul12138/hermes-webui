import json
import sys
import types
from io import BytesIO
from urllib.parse import urlparse


class _PostHandler:
    def __init__(self, body):
        raw = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = BytesIO(raw)


def _install_provider_model_ids(monkeypatch, fn):
    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.__path__ = []
    models = types.ModuleType("hermes_cli.models")
    models.provider_model_ids = fn
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.models", models)


def test_models_refresh_post_route_refreshes_provider_models(monkeypatch):
    import api.config as config
    import api.profiles as profiles
    import api.routes as routes

    calls = []

    def provider_model_ids(provider):
        calls.append(provider)
        return [f"{provider}/model-{len(calls)}"]

    _install_provider_model_ids(monkeypatch, provider_model_ids)
    routes._clear_live_models_cache()
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload)
    monkeypatch.setattr(config, "get_config", lambda: {"model": {"provider": "openai"}})
    monkeypatch.setattr(config, "_resolve_provider_alias", lambda provider: provider)
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "default")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    cached = routes._handle_live_models(object(), urlparse("/api/models/live?provider=openai"))
    refreshed = routes.handle_post(
        _PostHandler({"provider": "openai"}),
        urlparse("/api/models/refresh"),
    )

    assert calls == ["openai", "openai"]
    assert cached["models"][0]["id"] == "openai/model-1"
    assert refreshed["models"][0]["id"] == "openai/model-2"
    assert refreshed["ok"] is True


def test_models_refresh_empty_catalog_is_not_success(monkeypatch):
    import api.config as config
    import api.profiles as profiles
    import api.routes as routes

    _install_provider_model_ids(monkeypatch, lambda _provider: [])
    routes._clear_live_models_cache()
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload | {"_status": status})
    monkeypatch.setattr(config, "get_config", lambda: {"model": {"provider": "empty-provider"}})
    monkeypatch.setattr(config, "_resolve_provider_alias", lambda provider: provider)
    monkeypatch.setattr(config, "_PROVIDER_MODELS", {})
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "default")
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    refreshed = routes.handle_post(
        _PostHandler({"provider": "empty-provider"}),
        urlparse("/api/models/refresh"),
    )

    assert refreshed["ok"] is False
    assert refreshed["models"] == []
    assert refreshed["count"] == 0
    assert refreshed["_status"] == 200
    assert "No models were returned" in refreshed["message"]


def test_provider_models_fetch_parses_dedupes_and_sorts(monkeypatch):
    import urllib.request

    import api.routes as routes

    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": [
                        {"id": "zeta-model"},
                        {"id": "alpha-model"},
                        {"id": "zeta-model"},
                        {"model": "beta-model"},
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        requests.append(
            {
                "url": req.full_url,
                "authorization": req.headers.get("Authorization"),
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload | {"_status": status})
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    payload = routes.handle_post(
        _PostHandler({"base_url": "https://models.example.test/api", "api_key": "sk-test"}),
        urlparse("/api/provider-models/fetch"),
    )

    assert requests == [
        {
            "url": "https://models.example.test/api/v1/models",
            "authorization": "Bearer sk-test",
            "timeout": 8,
        }
    ]
    assert payload["ok"] is True
    assert payload["_status"] == 200
    assert [m["id"] for m in payload["models"]] == ["alpha-model", "beta-model", "zeta-model"]


def test_provider_models_fetch_normalizes_openai_compatible_models_url(monkeypatch):
    import urllib.request

    import api.routes as routes

    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "model-a"}]}).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        requests.append(req.full_url)
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload | {"_status": status})
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    for base_url in ("https://models.example.test", "https://models.example.test/v1"):
        payload = routes.handle_post(
            _PostHandler({"base_url": base_url, "api_key": "sk-test"}),
            urlparse("/api/provider-models/fetch"),
        )
        assert payload["ok"] is True

    assert requests == [
        "https://models.example.test/v1/models",
        "https://models.example.test/v1/models",
    ]


def test_provider_models_fetch_network_failure_returns_displayable_error(monkeypatch):
    import urllib.request

    import api.routes as routes

    def fake_urlopen(_req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload | {"_status": status})
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    payload = routes.handle_post(
        _PostHandler({"provider": "custom", "base_url": "https://models.example.test/v1"}),
        urlparse("/api/provider-models/fetch"),
    )

    assert payload["ok"] is False
    assert payload["_status"] == 502
    assert payload["models"] == []
    assert "Failed to fetch models" in payload["error"]
    assert "https://models.example.test/v1/models" in payload["error"]
    assert "timed out" in payload["error"]


def test_custom_models_refresh_fetches_current_modal_connection(monkeypatch):
    import urllib.request

    import api.config as config
    import api.routes as routes

    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"data": [{"id": "live-model"}, {"id": "second-model"}, {"id": "live-model"}]}
            ).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        requests.append((req.full_url, req.headers.get("Authorization")))
        return Response()

    monkeypatch.setattr(config, "_resolve_provider_alias", lambda provider: provider)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload | {"_status": status})
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    payload = routes.handle_post(
        _PostHandler(
            {
                "provider": "custom:math-model",
                "base_url": "https://fresh.example.test",
                "api_key": "sk-fresh-key",
            }
        ),
        urlparse("/api/models/refresh"),
    )

    assert requests == [("https://fresh.example.test/v1/models", "Bearer sk-fresh-key")]
    assert payload["ok"] is True
    assert payload["_status"] == 200
    assert [m["id"] for m in payload["models"]] == ["live-model", "second-model"]


def test_custom_models_refresh_rejects_missing_modal_api_key(monkeypatch):
    import urllib.request

    import api.routes as routes

    requests = []

    def fake_urlopen(req, timeout=None):
        requests.append(req.full_url)
        raise AssertionError("custom model refresh must not fetch without an API key")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload | {"_status": status})
    monkeypatch.setattr(routes, "bad", lambda _handler, message, status=400: {"ok": False, "error": message, "_status": status})
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    payload = routes.handle_post(
        _PostHandler(
            {
                "provider": "custom:math-model",
                "base_url": "https://fresh.example.test",
            }
        ),
        urlparse("/api/models/refresh"),
    )

    assert requests == []
    assert payload["ok"] is False
    assert payload["_status"] == 400
    assert "api_key is required" in payload["error"]


def test_provider_models_fetch_uses_providers_config_without_writing(monkeypatch):
    import urllib.request

    import api.config as config
    import api.routes as routes

    requests = []
    cfg = {
        "providers": {
            "localai": {
                "base_url": "https://localai.example.test/v1",
                "api_key": "${LOCALAI_TEST_KEY}",
            }
        }
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "local-model"}]}).encode("utf-8")

    def fake_urlopen(req, timeout=None):
        requests.append((req.full_url, req.headers.get("Authorization"), timeout))
        return Response()

    monkeypatch.setenv("LOCALAI_TEST_KEY", "sk-from-env")
    monkeypatch.setattr(config, "get_config", lambda: cfg)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(routes, "j", lambda _handler, payload, status=200, extra_headers=None: payload)
    monkeypatch.setattr(routes, "_check_csrf", lambda _handler: True)

    payload = routes.handle_post(
        _PostHandler({"provider": "localai"}),
        urlparse("/api/provider-models/fetch"),
    )

    assert requests == [("https://localai.example.test/v1/models", "Bearer sk-from-env", 8)]
    assert payload["ok"] is True
    assert [m["id"] for m in payload["models"]] == ["local-model"]
    assert cfg["providers"]["localai"]["api_key"] == "${LOCALAI_TEST_KEY}"
