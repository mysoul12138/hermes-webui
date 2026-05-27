"""Tests for custom_providers scanning in get_providers().

Verifies that config.yaml custom_providers entries (e.g. glmcode, timicc)
are surfaced in the /api/providers response alongside built-in providers.
"""

import json
import os
import sys
import types
from pathlib import Path

import api.config as config
import api.profiles as profiles
from tests._pytest_port import BASE


def _install_fake_hermes_cli(monkeypatch):
    """Stub hermes_cli so tests are deterministic and offline."""
    fake_pkg = types.ModuleType("hermes_cli")
    fake_pkg.__path__ = []

    fake_models = types.ModuleType("hermes_cli.models")
    fake_models.list_available_providers = lambda: []
    fake_models.provider_model_ids = lambda pid: []

    fake_auth = types.ModuleType("hermes_cli.auth")
    fake_auth.get_auth_status = lambda _pid: {}

    monkeypatch.setitem(sys.modules, "hermes_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.models", fake_models)
    monkeypatch.setitem(sys.modules, "hermes_cli.auth", fake_auth)
    monkeypatch.delitem(sys.modules, "agent.credential_pool", raising=False)
    monkeypatch.delitem(sys.modules, "agent", raising=False)

    try:
        from api.config import invalidate_models_cache
        invalidate_models_cache()
    except Exception:
        pass


def test_get_providers_does_not_live_fetch_model_catalogs(monkeypatch, tmp_path):
    """Provider list must not block on live model catalog discovery."""
    calls = []
    fake_pkg = types.ModuleType("hermes_cli")
    fake_pkg.__path__ = []
    fake_models = types.ModuleType("hermes_cli.models")
    fake_models.list_available_providers = lambda: []

    def provider_model_ids(provider):
        calls.append(provider)
        raise AssertionError("/api/providers must not live-fetch model catalogs")

    fake_models.provider_model_ids = provider_model_ids
    fake_auth = types.ModuleType("hermes_cli.auth")
    fake_auth.get_auth_status = lambda _pid: {}

    monkeypatch.setitem(sys.modules, "hermes_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.models", fake_models)
    monkeypatch.setitem(sys.modules, "hermes_cli.auth", fake_auth)
    monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)

    old_cfg = dict(config.cfg)
    old_mtime = config._cfg_mtime
    config.cfg.clear()
    config.cfg.update(
        {
            "model": {"provider": "nous"},
            "providers": {
                "lmstudio": {"base_url": "http://127.0.0.1:1234/v1"},
                "xai-oauth": {"api_key": "sk-xai-oauth-test"},
            },
        }
    )
    config._cfg_mtime = 0.0
    try:
        import api.providers as providers

        monkeypatch.setattr(providers, "_read_visible_codex_cache_model_ids", lambda: ["gpt-cached"])
        get_providers = providers.get_providers

        result = get_providers()
    finally:
        config.cfg.clear()
        config.cfg.update(old_cfg)
        config._cfg_mtime = old_mtime

    assert calls == []
    provider_ids = {p["id"] for p in result["providers"]}
    assert {"nous", "lmstudio", "xai-oauth", "openai-codex"}.issubset(provider_ids)


class TestCustomProvidersInGetProviders:
    """Unit tests for custom_providers scanning in get_providers()."""

    def _setup_cfg(self, custom_providers, active_provider=None):
        old_cfg = dict(config.cfg)
        old_mtime = config._cfg_mtime
        config.cfg.clear()
        config.cfg["model"] = {"provider": active_provider or "anthropic"}
        if custom_providers is not None:
            config.cfg["custom_providers"] = custom_providers
        try:
            config._cfg_mtime = config.Path(config._get_config_path()).stat().st_mtime
        except Exception:
            config._cfg_mtime = 0.0
        return old_cfg, old_mtime

    def _restore_cfg(self, old_cfg, old_mtime):
        config.cfg.clear()
        config.cfg.update(old_cfg)
        config._cfg_mtime = old_mtime

    def test_custom_provider_with_models(self, monkeypatch, tmp_path):
        """glmcode custom provider with models should appear in provider list."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
        monkeypatch.setenv("GLMCODE_API_KEY", "test-glm-key-12345678")

        old_cfg, old_mtime = self._setup_cfg([
            {
                "name": "glmcode",
                "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "api_key": "${GLMCODE_API_KEY}",
                "api_mode": "openai_compatible",
                "model": "glm-5.1",
            },
        ])

        from api.providers import get_providers
        try:
            result = get_providers()
            provider_ids = {p["id"] for p in result["providers"]}
            assert "custom:glmcode" in provider_ids, (
                f"custom:glmcode missing; got: {sorted(provider_ids)}"
            )

            glmcode = [p for p in result["providers"] if p["id"] == "custom:glmcode"][0]
            assert glmcode["has_key"] is True, (
                "glmcode should detect key from ${GLMCODE_API_KEY} env var"
            )
            assert glmcode["configurable"] is False, (
                "custom providers should not be configurable via WebUI"
            )
            assert glmcode["is_custom"] is True
            assert glmcode["key_source"] == "config_yaml"
            assert glmcode["display_name"] == "glmcode"

            # Model list — single model entry
            model_ids = {m["id"] for m in glmcode["models"]}
            assert "glm-5.1" in model_ids, (
                f"Expected glm-5.1 in models, got: {model_ids}"
            )
            assert glmcode["models_total"] == 1
        finally:
            self._restore_cfg(old_cfg, old_mtime)

    def test_providers_panel_renders_config_yaml_custom_providers(self):
        """Settings → Providers must not filter out read-only custom providers."""
        src = open("static/panels.js", encoding="utf-8").read()
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")
        assert "filter(p=>p.configurable||p.is_oauth||p.is_custom)" in src
        assert "function _buildProviderCard(p)" not in src
        assert "function _buildProviderCard(p)" in provider_src
        assert "providers_custom_config_yaml_hint" in provider_src
        assert "if(p.configurable||p.is_custom){" in provider_src
        assert "openProviderConfigModal(p)" in provider_src

    def test_add_provider_modal_functions_are_global_for_inline_button(self):
        """The static Add provider button uses inline onclick, so the modal API must be on window."""
        html = open("static/index.html", encoding="utf-8").read()
        src = open("static/panels.js", encoding="utf-8").read()
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")
        registry_src = Path("static/panel-registry.js").read_text(encoding="utf-8")
        i18n = Path("static/i18n.js").read_text(encoding="utf-8")
        assert 'onclick="openProviderConfigModal()"' in html
        assert 'static/panel-registry.js?v=__WEBUI_VERSION__' in html
        assert 'static/provider-config.js?v=__WEBUI_VERSION__' in html
        assert 'static/panel-registry.js?v=__WEBUI_VERSION__' in html.split('static/provider-config.js?v=__WEBUI_VERSION__')[0]
        assert "registerSettingsSection" in registry_src
        assert "window.HermesPanelRegistry.registerSettingsSection('providers'" in provider_src
        assert "_openRegisteredSettingsSection('providers', () => loadProvidersPanel())" in src
        assert "_notifyRegisteredSettingsLoaded('providers', () => loadProvidersPanel())" in src
        assert "window.openProviderConfigModal=openProviderConfigModal;" in provider_src
        assert "window.closeProviderConfigModal=closeProviderConfigModal;" in provider_src
        assert "window.saveProviderConfigModal=saveProviderConfigModal;" in provider_src
        assert "overlay.style.display='flex';" in provider_src
        assert "overlay.setAttribute('aria-hidden','false');" in provider_src
        assert 'data-i18n="provider_modal_add_title"' in html
        assert 'data-i18n="provider_modal_desc"' in html
        assert 'data-i18n="provider_modal_name_label"' in html
        assert 'data-i18n-placeholder="provider_modal_api_key_placeholder_keep"' in html
        assert 'id="providerConfigSaveBtn" type="submit" data-i18n="save"' in html
        assert "const PROVIDER_MODAL_I18N = {" in provider_src
        assert "const titleKey = editing ? PROVIDER_MODAL_I18N.editTitle : PROVIDER_MODAL_I18N.addTitle;" in provider_src
        assert "title.textContent=t(titleKey)" in provider_src
        assert "t('providers_saving')" in provider_src
        assert "btn.textContent='Save'" not in provider_src
        assert "openProviderConfigModal(p)" in provider_src
        assert "saveBtn.closest('.app-dialog-actions')" in provider_src
        assert "providers_refresh_models" in provider_src
        assert "_ensureProviderRefreshButton(provider);" in provider_src
        assert "if(!provider||!provider.id){" not in provider_src
        assert "refreshBtn.hidden=false;" in provider_src
        assert "const providerId=(provider&&typeof provider==='object'&&typeof provider.id==='string'&&provider.id.trim())" in provider_src
        assert "refreshBtn.onclick=()=>_refreshProviderModels(providerId, refreshBtn);" in provider_src
        for key in (
            "providers_add_provider",
            "providers_refresh_models",
            "providers_show_key",
            "providers_hide_key",
            "providers_models_label",
            "providers_models_refreshed",
            "provider_modal_add_title",
            "provider_modal_edit_title",
            "provider_modal_desc",
            "provider_modal_api_key_placeholder_keep",
            "provider_modal_api_key_placeholder_new",
        ):
            assert i18n.count(f"{key}:") >= 2

    def test_providers_panel_load_is_single_flight_and_preserves_success_state(self):
        """A later timeout must not overwrite a successful providers render."""
        src = Path("static/panels.js").read_text(encoding="utf-8")
        assert "let _providersPanelLoadPromise = null;" in src
        assert "if(_providersPanelLoadPromise) return _providersPanelLoadPromise;" in src
        assert "list.dataset.providersLoaded='1';" in src
        assert "if(list.dataset.providersLoaded==='1') return;" in src
        assert "list.dataset.providersLoaded='0';" in src

    def test_provider_frontend_ux_keeps_card_and_modal_consistent(self):
        """Provider cards share behavior; refresh models lives in the edit modal."""
        src = Path("static/panels.js").read_text(encoding="utf-8")
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")

        assert "providers_refresh_models" not in src
        assert "Refresh Models" not in src
        assert "_providerCardEls" not in src
        assert "function _refreshProviderModels" not in src
        assert "function _refreshProviderModels" in provider_src
        assert "function _ensureProviderRefreshButton(provider)" in provider_src
        assert "refreshBtn.hidden=false;" in provider_src
        assert "const providerId=(provider&&typeof provider==='object'&&typeof provider.id==='string'&&provider.id.trim())" in provider_src
        assert "refreshBtn.onclick=()=>_refreshProviderModels(providerId, refreshBtn);" in provider_src
        assert "const PROVIDER_MODEL_DATALIST_ID = 'providerConfigModelOptions';" in provider_src
        assert "input.setAttribute('list', PROVIDER_MODEL_DATALIST_ID);" in provider_src
        assert "function _setProviderModelOptions(models)" in provider_src
        assert "function _getProviderModelOptions()" in provider_src
        assert "option.value=model.id;" in provider_src
        assert "if(models.length) body.models=models;" in provider_src
        assert "if(p.configurable||p.is_custom){" in provider_src
        assert "input.className='provider-card-input';" in provider_src
        assert "function _ensureProviderConfigApiKeyToggle()" in provider_src
        assert "toggleBtn.id='providerConfigApiKeyToggle';" in provider_src
        assert "apiKey.dataset.savedKeyHidden=editing&&provider.has_key?'1':'0';" in provider_src
        assert "const placeholderKey=editing&&provider.has_key?'provider_modal_api_key_placeholder_saved':'provider_modal_api_key_placeholder_new';" in provider_src
        assert "button.disabled=true;" in provider_src
        assert "button.textContent=t(input.dataset.savedKeyHidden==='1'?'providers_saved_key_hidden':'providers_show_key');" in provider_src
        assert "button.disabled=false;" in provider_src
        assert "_setProviderModalStatus(t('provider_modal_saved_key_hidden_hint'), 'warning');" in provider_src
        assert "button.textContent=t(revealed?'providers_hide_key':'providers_show_key');" in provider_src
        assert "toggleBtn.onclick=()=>_toggleProviderKeyInput(input, toggleBtn);" in provider_src
        assert "modelLabel.textContent=t('providers_models_label');" in provider_src
        assert "more.textContent=t('providers_models_more', hiddenCount);" in provider_src
        assert "function _updateProviderCardModels(providerId, models)" in provider_src
        assert "function _providerSelectorValue(value)" in provider_src
        assert 'document.querySelector(`.provider-card[data-provider="${_providerSelectorValue(providerId)}"]`)' in provider_src
        assert "_providerStateById.set(providerId,provider);" in provider_src
        assert "if(meta) meta.textContent=_formatProviderMeta(provider,provider.models_total);" in provider_src
        assert "await loadProvidersPanel();" not in provider_src.split("async function _refreshProviderModels(providerId, btn)")[1].split("if (window.HermesPanelRegistry)")[0]
        assert "showToast(" not in provider_src.split("async function _refreshProviderModels(providerId, btn)")[1].split("if (window.HermesPanelRegistry)")[0]
        assert "_setProviderModalStatus(t('providers_models_refreshed', res.provider||providerId), 'success');" in provider_src
        assert "_setProviderModalStatus(res.message||res.error||t('providers_models_refresh_failed'), 'error');" in provider_src
        assert "if(!models.length){" in provider_src
        assert "_setProviderModalStatus(res.message||res.error||t('providers_models_refresh_empty'), 'warning');" in provider_src
        assert "base_url:body.base_url" in provider_src
        assert "api_key:body.api_key" in provider_src
        assert "if(!body.api_key){" in provider_src
        assert "_setProviderModalStatus(t('provider_modal_api_key_required_for_refresh'), 'error');" in provider_src

    def test_provider_panel_reload_preserves_expanded_state(self):
        """Provider cards should reopen after panel reloads rebuild the DOM."""
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")

        assert "const _providerExpandedIds = new Set();" in provider_src
        assert "if(_providerExpandedIds.has(p.id)) card.classList.add('open');" in provider_src
        assert "function _toggleProviderCardExpanded(card, providerId)" in provider_src
        assert "_providerExpandedIds.add(providerId);" in provider_src
        assert "_providerExpandedIds.delete(providerId);" in provider_src
        assert "header.addEventListener('click',()=>_toggleProviderCardExpanded(card,p.id));" in provider_src
        assert "_toggleProviderCardExpanded(card,p.id);" in provider_src

    def test_provider_modal_key_visibility_and_refresh_i18n_exist(self):
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")
        i18n = Path("static/i18n.js").read_text(encoding="utf-8")

        toggle_src = provider_src.split("function _toggleProviderKeyInput(input, button)")[1].split("function _ensureProviderConfigApiKeyToggle()")[0]
        assert "const hasValue=!!String(input.value||'').trim();" in toggle_src
        assert "if(!hasValue){" in toggle_src
        assert "input.type='password';" in toggle_src
        assert "input.type=input.type==='text'?'password':'text';" in toggle_src
        assert "if(hasValue) _setProviderModalStatus();" in toggle_src

        sync_src = provider_src.split("function _syncProviderKeyToggle(input, button)")[1].split("function _toggleProviderKeyInput(input, button)")[0]
        assert "button.disabled=true;" in sync_src
        assert "providers_saved_key_hidden" in sync_src
        assert "button.disabled=false;" in sync_src

        refresh_src = provider_src.split("async function _refreshProviderModels(providerId, btn)")[1].split("if (window.HermesPanelRegistry)")[0]
        assert "if(!body.api_key){" in refresh_src
        assert "api('/api/models/refresh'" in refresh_src
        assert "api_key:body.api_key" in refresh_src
        assert "use_saved_key" not in refresh_src
        assert "provider_modal_api_key_required_for_refresh" in i18n
        assert "provider_modal_saved_key_hidden_hint" in i18n
        assert "provider_modal_api_key_placeholder_saved" in i18n
        assert "providers_saved_key_hidden" in i18n

    def test_provider_models_frontend_dedupe_uses_canonical_id(self):
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")
        normalize_src = provider_src.split("function _normalizeProviderModels(models)")[1].split("function _ensureProviderModelDatalist()")[0]

        assert "firstText(model.id, model.model, model.name, model.label, model.title)" in normalize_src
        assert "firstText(model.label, model.title, model.name, model.id, model.model)" in normalize_src
        assert "const key=id.toLowerCase();" in normalize_src
        assert "seen.has(key)" in normalize_src
        assert "tag.textContent=m.id||m.label||m;" in provider_src

    def test_custom_provider_frontend_requires_default_model_before_save(self):
        """Custom provider saves must not submit an empty default model."""
        provider_src = Path("static/provider-config.js").read_text(encoding="utf-8")
        i18n = Path("static/i18n.js").read_text(encoding="utf-8")

        save_src = provider_src.split("async function saveProviderConfigModal(event)")[1].split("window.saveProviderConfigModal")[0]
        assert "const body=_providerModalPayload();" in save_src
        assert "if(!body.default_model){" in save_src
        assert "_setProviderModalStatus(t('provider_modal_default_model_required'), 'error');" in save_src
        assert "return;" in save_src
        assert "delete body.default_model" not in save_src
        assert "provider_modal_default_model_required" in i18n

    def test_custom_provider_with_multi_models(self, monkeypatch, tmp_path):
        """Custom provider with `models` list should expose all entries."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test-12345678")

        old_cfg, old_mtime = self._setup_cfg([
            {
                "name": "deepseek",
                "base_url": "https://api.deepseek.com",
                "api_key": "${DEEPSEEK_API_KEY}",
                "api_mode": "openai_compatible",
                "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
            },
        ])

        from api.providers import get_providers
        try:
            result = get_providers()
            provider_ids = {p["id"] for p in result["providers"]}
            assert "custom:deepseek" in provider_ids

            ds = [p for p in result["providers"] if p["id"] == "custom:deepseek"][0]
            assert ds["has_key"] is True
            model_ids = {m["id"] for m in ds["models"]}
            assert model_ids == {"deepseek-v4-flash", "deepseek-v4-pro"}, (
                f"Expected v4 models, got: {model_ids}"
            )
        finally:
            self._restore_cfg(old_cfg, old_mtime)

    def test_custom_provider_no_key(self, monkeypatch, tmp_path):
        """Custom provider without a configured key should show has_key=False."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
        # Ensure TIMICC_API_KEY is not set
        monkeypatch.delenv("TIMICC_API_KEY", raising=False)

        old_cfg, old_mtime = self._setup_cfg([
            {
                "name": "timicc-claude",
                "base_url": "https://timicc.com/v1",
                "api_key": "${TIMICC_API_KEY}",
                "api_mode": "anthropic_messages",
            },
        ])

        from api.providers import get_providers
        try:
            result = get_providers()
            # TIMICC_API_KEY env var is not set → has_key should be False
            cp = [p for p in result["providers"] if p["id"] == "custom:timicc-claude"]
            assert len(cp) == 1
            assert cp[0]["has_key"] is False
            assert cp[0]["key_source"] == "none"
        finally:
            self._restore_cfg(old_cfg, old_mtime)

    def test_empty_custom_providers_no_crash(self, monkeypatch, tmp_path):
        """get_providers should not crash when custom_providers is empty list."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)

        old_cfg, old_mtime = self._setup_cfg([])

        from api.providers import get_providers
        try:
            result = get_providers()
            # No crash, still returns built-in providers
            provider_ids = {p["id"] for p in result["providers"]}
            # Should not contain any custom: entries
            custom_ids = {pid for pid in provider_ids if pid.startswith("custom:")}
            assert len(custom_ids) == 0, (
                f"Empty custom_providers should not produce entries, got: {custom_ids}"
            )
        finally:
            self._restore_cfg(old_cfg, old_mtime)

    def test_custom_provider_bare_api_key(self, monkeypatch, tmp_path):
        """Custom provider with inline api_key (not env ref) should show has_key=True."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)

        old_cfg, old_mtime = self._setup_cfg([
            {
                "name": "my-proxy",
                "base_url": "https://proxy.example.com/v1",
                "api_key": "sk-inline-key-12345678",
            },
        ])

        from api.providers import get_providers
        try:
            result = get_providers()
            cp = [p for p in result["providers"] if p["id"] == "custom:my-proxy"]
            assert len(cp) == 1
            assert cp[0]["has_key"] is True
        finally:
            self._restore_cfg(old_cfg, old_mtime)

    def test_custom_provider_parenthesized_port_uses_safe_provider_id(self, monkeypatch, tmp_path):
        """Local setup names with ports must expose the same safe id used by routing."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)
        monkeypatch.setenv("LOCAL_PORT_API_KEY", "sk-local-port-test-12345678")

        old_cfg, old_mtime = self._setup_cfg([
            {
                "name": "Local (127.0.0.1:15721)",
                "base_url": "http://127.0.0.1:15721/v1",
                "api_key": "${LOCAL_PORT_API_KEY}",
                "model": "deepseek-v4-flash",
            },
        ])

        from api.providers import _get_provider_api_key, _provider_has_key, get_providers
        try:
            provider_id = "custom:local-127.0.0.1-15721"
            result = get_providers()
            provider_ids = {p["id"] for p in result["providers"]}
            assert provider_id in provider_ids
            assert "custom:Local (127.0.0.1:15721)" not in provider_ids
            assert "custom:local-(127.0.0.1:15721)" not in provider_ids

            local = [p for p in result["providers"] if p["id"] == provider_id][0]
            assert local["display_name"] == "Local (127.0.0.1:15721)"
            assert local["has_key"] is True
            assert _provider_has_key(provider_id) is True
            assert _get_provider_api_key(provider_id) == "sk-local-port-test-12345678"
        finally:
            self._restore_cfg(old_cfg, old_mtime)

    def test_custom_provider_no_name_skipped(self, monkeypatch, tmp_path):
        """Malformed custom provider without name should be silently skipped."""
        _install_fake_hermes_cli(monkeypatch)
        monkeypatch.setattr(profiles, "get_active_hermes_home", lambda: tmp_path)

        old_cfg, old_mtime = self._setup_cfg([
            {"base_url": "https://no-name.example.com/v1"},
        ])

        from api.providers import get_providers
        try:
            result = get_providers()
            custom_ids = {p["id"] for p in result["providers"] if p["id"].startswith("custom:")}
            assert len(custom_ids) == 0, (
                f"Entry without name should be skipped, got: {custom_ids}"
            )
        finally:
            self._restore_cfg(old_cfg, old_mtime)


class TestDeepSeekV4Models:
    """Verify DeepSeek V4 models are in the model lists, V3 is removed."""

    def test_v4_models_in_provider_models(self):
        """_PROVIDER_MODELS['deepseek'] should contain v4 and legacy v3 entries."""
        from api.config import _PROVIDER_MODELS
        ds_models = _PROVIDER_MODELS.get("deepseek", [])
        ids = {m["id"] for m in ds_models}

        assert "deepseek-v4-flash" in ids, f"v4-flash missing: {ids}"
        assert "deepseek-v4-pro" in ids, f"v4-pro missing: {ids}"

        # Legacy models still present (deprecated 2026-07-24, not yet removed)
        assert "deepseek-chat-v3-0324" in ids, (
            f"V3 legacy should remain until deprecation date: {ids}"
        )
        assert "deepseek-reasoner" in ids, (
            f"Reasoner legacy should remain until deprecation date: {ids}"
        )

    def test_zai_models_include_glm_series(self):
        """_PROVIDER_MODELS['zai'] should have GLM-5.x and GLM-4.x models."""
        from api.config import _PROVIDER_MODELS
        zai_models = _PROVIDER_MODELS.get("zai", [])
        ids = {m["id"] for m in zai_models}

        assert "glm-5.1" in ids, f"glm-5.1 missing from zai models: {ids}"
        assert "glm-5" in ids, f"glm-5 missing from zai models: {ids}"
        assert "glm-5-turbo" in ids, f"glm-5-turbo missing from zai models: {ids}"
        assert "glm-4.7" in ids, f"glm-4.7 missing from zai models: {ids}"
        assert "glm-4.5" in ids, f"glm-4.5 missing from zai models: {ids}"
        assert "glm-4.5-flash" in ids, f"glm-4.5-flash missing from zai models: {ids}"

    def test_zai_in_onboarding_setup(self):
        """_SUPPORTED_PROVIDER_SETUPS should have 'zai' entry."""
        from api.onboarding import _SUPPORTED_PROVIDER_SETUPS
        assert "zai" in _SUPPORTED_PROVIDER_SETUPS, (
            "zai provider should be in onboarding quick-setup"
        )
        zai = _SUPPORTED_PROVIDER_SETUPS["zai"]
        assert zai["label"] == "Z.AI / GLM (智谱)"
        assert zai["env_var"] == "GLM_API_KEY"
        assert zai["default_model"] == "glm-5.1"
        assert zai["default_base_url"] == "https://open.bigmodel.cn/api/paas/v4"

    def test_deepseek_onboarding_default_is_v4(self):
        """DeepSeek onboarding default should be v4-flash, not V3."""
        from api.onboarding import _SUPPORTED_PROVIDER_SETUPS
        ds = _SUPPORTED_PROVIDER_SETUPS.get("deepseek", {})
        assert ds.get("default_model") == "deepseek-v4-flash", (
            f"DeepSeek default should be v4-flash, got: {ds.get('default_model')}"
        )
        assert ds.get("default_base_url") == "https://api.deepseek.com", (
            f"Base URL should be bare domain, got: {ds.get('default_base_url')}"
        )
