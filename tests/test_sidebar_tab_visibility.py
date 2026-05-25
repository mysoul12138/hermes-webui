"""Regression tests for sidebar tab visibility feature.

Covers backend validation round-trip, frontend static contracts,
i18n coverage, and the key integration points that have broken before.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PY = (ROOT / "api" / "config.py").read_text(encoding="utf-8")
PANELS_JS = (ROOT / "static" / "panels.js").read_text(encoding="utf-8")
CHANNELS_JS = (ROOT / "static" / "channels.js").read_text(encoding="utf-8")
PANEL_REGISTRY_JS = (ROOT / "static" / "panel-registry.js").read_text(encoding="utf-8")
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


def test_backend_round_trip_and_validation(monkeypatch, tmp_path):
    """hidden_tabs defaults to [], saves/reloads, rejects non-list, filters empty strings."""
    import api.config as config
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_path)

    loaded = config.load_settings()
    assert loaded["hidden_tabs"] == [], "default must be empty list"

    saved = config.save_settings({"hidden_tabs": ["kanban", "insights"]})
    assert saved["hidden_tabs"] == ["kanban", "insights"]
    assert config.load_settings()["hidden_tabs"] == ["kanban", "insights"]

    # Non-list is rejected, default preserved
    bad = config.save_settings({"hidden_tabs": "not-a-list"})
    assert bad["hidden_tabs"] == ["kanban", "insights"]

    # Empty strings filtered, empty list clears
    saved = config.save_settings({"hidden_tabs": ["kanban", "", "  ", "logs"]})
    assert saved["hidden_tabs"] == ["kanban", "logs"]
    cleared = config.save_settings({"hidden_tabs": []})
    assert cleared["hidden_tabs"] == []

    # Must NOT be in bool keys (would corrupt the list)
    assert "hidden_tabs" not in config._SETTINGS_BOOL_KEYS
    assert "hidden_tabs" in config._SETTINGS_ALLOWED_KEYS


def test_frontend_static_contracts():
    """All required HTML, JS, CSS, and boot elements exist with correct wiring."""
    # HTML: container in Appearance pane
    assert 'id="tabVisibilityChips"' in INDEX_HTML
    assert 'data-i18n="settings_label_tab_visibility"' in INDEX_HTML
    assert 'data-i18n="settings_desc_tab_visibility"' in INDEX_HTML
    assert 'data-panel="channels"' in INDEX_HTML
    assert 'id="panelChannels"' in INDEX_HTML
    assert 'id="mainChannels"' in INDEX_HTML
    assert 'static/panel-registry.js?v=__WEBUI_VERSION__' in INDEX_HTML
    assert 'static/channels.js?v=__WEBUI_VERSION__' in INDEX_HTML
    appearance_start = INDEX_HTML.find('id="settingsPaneAppearance"')
    prefs_start = INDEX_HTML.find('id="settingsPanePreferences"', appearance_start + 1)
    chips_pos = INDEX_HTML.find('id="tabVisibilityChips"')
    assert appearance_start < chips_pos < prefs_start, \
        "tabVisibilityChips must be inside Appearance pane"

    # JS: constants, functions, and wiring
    assert "_ALWAYS_VISIBLE_TABS" in PANELS_JS
    assert "'chat'" in PANELS_JS.split("_ALWAYS_VISIBLE_TABS")[1][:80]
    assert "'settings'" in PANELS_JS.split("_ALWAYS_VISIBLE_TABS")[1][:80]
    assert "channels: 'tab_channels'" in PANELS_JS
    main_switch_start = PANELS_JS.find("const mainEl = document.querySelector('main.main')")
    main_switch = PANELS_JS[main_switch_start:main_switch_start + 500]
    assert "'channels'" in main_switch
    assert "showing-' + p" in main_switch
    assert "renderChannelsPanel()" in PANELS_JS
    assert "HermesPanelRegistry" in PANEL_REGISTRY_JS
    assert "registerPanel" in PANEL_REGISTRY_JS
    assert "_openRegisteredPanel('channels', () => renderChannelsPanel())" in PANELS_JS
    assert "window.HermesPanelRegistry.registerPanel('channels'" in CHANNELS_JS
    assert "_HIDDEN_TABS_LS_KEY" in PANELS_JS
    assert "hermes-webui-hidden-tabs" in PANELS_JS
    for fn in ("_getHiddenTabs", "_setHiddenTabs", "_applyTabVisibility",
               "_renderTabVisibilityChips", "_toggleTabVisibilityChip"):
        assert f"function {fn}(" in PANELS_JS, f"panels.js must define {fn}()"

    # Toggle must autosave and respect always-visible tabs
    toggle_block = PANELS_JS[PANELS_JS.find("function _toggleTabVisibilityChip"):]
    toggle_body = toggle_block[:toggle_block.find("\nfunction ", 1) or 2000]
    assert "_scheduleAppearanceAutosave" in toggle_body
    assert "_ALWAYS_VISIBLE_TABS" in toggle_body

    # Appearance payload must include hidden_tabs
    payload_block = PANELS_JS[PANELS_JS.find("function _appearancePayloadFromUi"):]
    payload_body = payload_block[:payload_block.find("\nfunction ", 1) or 2000]
    assert "hidden_tabs" in payload_body
    assert "_getHiddenTabs" in payload_body

    # CSS: hidden class and chip styles
    assert ".nav-tab-hidden" in STYLE_CSS
    assert "display:none" in STYLE_CSS.split(".nav-tab-hidden")[1][:80].replace(" ", "")
    assert ".tab-visibility-chip" in STYLE_CSS

    # No flash-prevention script in <head> (DOM elements don't exist at that point)
    head_end = INDEX_HTML.find("</head>")
    assert "hermes-webui-hidden-tabs" not in INDEX_HTML[:head_end]


def test_boot_restores_visibility_from_localstorage():
    """boot.js must call _applyTabVisibility at boot time so hidden tabs take effect."""
    assert "_restoreTabVisibility" in BOOT_JS
    block = BOOT_JS[BOOT_JS.find("_restoreTabVisibility"):][:1500]
    assert "_applyTabVisibility" in block, \
        "boot.js must call _applyTabVisibility so tabs are hidden before first paint"


def test_i18n_coverage():
    """Label and description keys must exist in all locales with matching counts."""
    label_count = I18N_JS.count("settings_label_tab_visibility")
    desc_count = I18N_JS.count("settings_desc_tab_visibility")
    assert label_count >= 12, f"Expected ≥12 locales, found {label_count}"
    assert desc_count >= 12, f"Expected ≥12 locales, found {desc_count}"
    assert label_count == desc_count, \
        f"Label ({label_count}) and desc ({desc_count}) counts must match"


def test_backend_rejects_chat_and_settings_in_hidden_tabs(monkeypatch, tmp_path):
    """Server-side belt-and-suspenders: a malicious POST that tries to hide
    `chat` or `settings` (the always-visible nav tabs) must be filtered out
    server-side, not just client-side. The client already applies the same
    filter at apply time, but the server should not let a tampered payload
    persist the forbidden values."""
    import api.config as config
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_path)

    saved = config.save_settings({"hidden_tabs": ["chat", "kanban", "settings", "logs"]})
    assert saved["hidden_tabs"] == ["kanban", "logs"], \
        "chat and settings must be stripped server-side"

    # Even an all-forbidden payload reduces to empty (not rejected — empty is fine)
    saved = config.save_settings({"hidden_tabs": ["chat", "settings"]})
    assert saved["hidden_tabs"] == []


def test_backend_round_trips_channel_platform_configs(monkeypatch, tmp_path):
    """Saved channel configs must survive reload so configured status is not
    browser-local-only."""
    import api.config as config
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_path)

    saved = config.save_settings({
        "channel_platform_configs": {
            "weixin": {"token": "wx-token", "account_id": "acct-1"},
            "": {"token": "ignored"},
            "telegram": "not-a-dict",
        }
    })

    assert saved["channel_platform_configs"] == {
        "weixin": {"token": "wx-token", "account_id": "acct-1"}
    }
    assert config.load_settings()["channel_platform_configs"]["weixin"]["token"] == "wx-token"


def test_backend_exposes_safe_weixin_env_prefill(monkeypatch, tmp_path):
    """Weixin QR login writes .env; /api/settings needs a safe UI prefill."""
    import api.config as config

    env_path = tmp_path / ".env"
    env_path.write_text(
        "WEIXIN_ACCOUNT_ID=acct-1\n"
        "WEIXIN_TOKEN=secret-token-value\n"
        "WEIXIN_BASE_URL=https://weixin.local\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_channel_env_path_candidates", lambda: [env_path])

    adapters = config.get_safe_channel_platform_config_adapters()

    assert adapters["weixin"]["account_id"] == "acct-1"
    assert adapters["weixin"]["token_configured"] is True
    assert adapters["weixin"]["token"] == "••••••••"
    assert adapters["weixin"]["token"] != "secret-token-value"


def test_backend_weixin_env_prefill_merges_missing_fields(monkeypatch, tmp_path):
    """A partial active .env must not block token/base_url fallback candidates."""
    import api.config as config

    active_env = tmp_path / "active.env"
    fallback_env = tmp_path / "fallback.env"
    active_env.write_text("WEIXIN_ACCOUNT_ID=acct-active\n", encoding="utf-8")
    fallback_env.write_text(
        "WEIXIN_ACCOUNT_ID=acct-fallback\n"
        "WEIXIN_TOKEN=fallback-token\n"
        "WEIXIN_BASE_URL=https://weixin.fallback\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_channel_env_path_candidates", lambda: [active_env, fallback_env])

    adapters = config.get_safe_channel_platform_config_adapters()

    assert adapters["weixin"]["account_id"] == "acct-active"
    assert adapters["weixin"]["token_configured"] is True
    assert adapters["weixin"]["token"] == "••••••••"
    assert adapters["weixin"]["base_url"] == "https://weixin.fallback"


def test_channel_env_path_candidates_include_windows_wsl_fallbacks(monkeypatch, tmp_path):
    """Windows installs should still look at WSL Hermes homes after active .env."""
    import api.channel_config_adapters as adapters

    active_home = tmp_path / "hermes"
    monkeypatch.setattr(adapters.os, "name", "nt", raising=False)
    monkeypatch.setattr(adapters, "active_hermes_env_path", lambda _home: active_home / ".env")

    candidates = adapters.channel_env_path_candidates(tmp_path)

    assert candidates[0] == active_home / ".env"
    assert Path(r"\\wsl.localhost\Ubuntu-Hermes\home\xl\.hermes\.env") in candidates
    assert Path(r"\\wsl$\Ubuntu\home\xl\.hermes\.env") in candidates


def test_channel_env_path_candidates_non_windows_active_only(monkeypatch, tmp_path):
    """Linux/macOS installs should prefer the active env without WSL fallbacks."""
    import api.channel_config_adapters as adapters

    active_env = tmp_path / "active.env"
    monkeypatch.setattr(adapters.os, "name", "posix", raising=False)
    monkeypatch.setattr(adapters, "active_hermes_env_path", lambda _home: active_env)

    assert adapters.channel_env_path_candidates(tmp_path) == [active_env]


def test_profile_switch_reconciles_hidden_tabs():
    """When a user switches profiles, the new profile's hidden_tabs value
    must be applied — the per-profile settings.json is the source of truth,
    not the previous profile's localStorage value. Stage-394 added a
    /api/settings refetch in _refreshProfileSwitchBackground; verify it stays
    wired (the API call + the _applyTabVisibility call)."""
    bg_start = PANELS_JS.find("function _refreshProfileSwitchBackground")
    assert bg_start >= 0, "_refreshProfileSwitchBackground not found"
    bg_end = PANELS_JS.find("\nfunction ", bg_start + 1)
    if bg_end < 0:
        bg_end = bg_start + 4000
    bg_body = PANELS_JS[bg_start:bg_end]
    assert "/api/settings" in bg_body, \
        "profile-switch background refresh must re-fetch settings for the new profile"
    assert "_applyTabVisibility" in bg_body, \
        "profile-switch background refresh must re-apply tab visibility"
    assert "hidden_tabs" in bg_body, \
        "profile-switch background refresh must read hidden_tabs from server response"


def test_chip_a11y_uses_switch_role_with_aria_checked():
    """Chips should use role=switch + aria-checked instead of plain
    aria-pressed. The pressed/not-pressed wording is confusing for a toggle
    that visually represents an on/off switch; role=switch + aria-checked
    matches user mental model."""
    render_block = PANELS_JS[PANELS_JS.find("function _renderTabVisibilityChips"):]
    body = render_block[:render_block.find("\nfunction ", 1) or 3000]
    assert "role" in body and "'switch'" in body, \
        "chip should declare role='switch' for clearer screen-reader narration"
    assert "aria-checked" in body, "chip should use aria-checked to match role=switch"
    # Group container also has role=group + aria-labelledby
    assert 'role="group"' in INDEX_HTML, "chip container needs role=group"
    assert 'aria-labelledby="tabVisibilityLabel"' in INDEX_HTML, \
        "chip container needs aria-labelledby pointing at the label"
    # Focus-visible style exists
    assert ".tab-visibility-chip:focus-visible" in STYLE_CSS, \
        "chip needs a :focus-visible style for keyboard nav"


def test_channels_tab_static_slice_integrates_with_nav_and_visibility():
    """Channels is a normal nav tab and renders a platform detail config page."""
    assert INDEX_HTML.count('data-panel="channels"') == 2, \
        "Channels must be present in both desktop rail and mobile sidebar nav"
    assert 'data-tooltip="Channels"' in INDEX_HTML
    assert 'data-label="Channels"' in INDEX_HTML
    assert 'id="panelChannels"' in INDEX_HTML
    assert 'id="mainChannels"' in INDEX_HTML
    assert 'id="channelPlatformPicker"' in INDEX_HTML
    assert 'id="channelConfigFields"' in INDEX_HTML
    assert 'onsubmit="saveChannelConfig(event)"' in INDEX_HTML
    panel_slice = INDEX_HTML[INDEX_HTML.find('id="panelChannels"'):INDEX_HTML.find('id="panelMemory"')]
    main_slice = INDEX_HTML[INDEX_HTML.find('id="mainChannels"'):INDEX_HTML.find('id="mainSettings"')]
    assert 'id="channelPlatformPicker"' in panel_slice
    assert 'id="channelPlatformPicker"' not in main_slice
    assert 'class="channels-main-card" data-channel-platform=' not in INDEX_HTML
    assert INDEX_HTML.count('class="channels-main-card" data-channel-platform=') == 0
    for platform in ["Telegram", "Discord", "Slack", "WhatsApp", "Matrix", "Feishu", "DingTalk", "QQBot", "Weixin", "WeCom"]:
        assert f"name: '{platform}'" in CHANNELS_JS
    assert "platform_bot_token" in CHANNELS_JS
    assert "platform_require_mention" in CHANNELS_JS
    assert "platform_free_response_chats" in CHANNELS_JS
    assert "platform_allowed_channels" in CHANNELS_JS
    assert "platform_qr_login" in CHANNELS_JS
    assert "type: 'action', action: 'weixinQrLogin'" in CHANNELS_JS
    assert "onclick=\"runChannelAction('" in CHANNELS_JS
    assert "async function runChannelAction(actionKey)" in CHANNELS_JS
    assert "'/api/hermes/weixin/qrcode'" in CHANNELS_JS
    assert "_renderWeixinQrLoginResult(payload)" in CHANNELS_JS
    assert "data.image || data.qrcode_url || data.url || data.qrcode" in CHANNELS_JS
    assert "data.qrcode || data.url || data.qrcode_url" in CHANNELS_JS
    assert "^https?:\\/\\/.+\\.(png|jpe?g|gif|webp|svg)" in CHANNELS_JS
    assert "data:image/png;base64" in CHANNELS_JS
    assert "platform_qr_login_image_alt" in CHANNELS_JS
    assert "platform_qr_login_text_hint" in CHANNELS_JS
    assert CHANNELS_JS.find("action: 'weixinQrLogin'") < CHANNELS_JS.find("label: 'platform_weixin_token'")
    assert "renderChannelsPanel()" in PANELS_JS
    assert "channel_platform_configs" in CHANNELS_JS
    assert "channel_platform_config_adapters" in CHANNELS_JS
    assert "function _mergeChannelConfigAdapters(configs)" in CHANNELS_JS
    assert "CHANNEL_CONFIGURED_SECRET_MARKER" in CHANNELS_JS
    assert "function _channelConfigsForSave(configs)" in CHANNELS_JS
    assert "values[fieldKey] === CHANNEL_CONFIGURED_SECRET_MARKER" in CHANNELS_JS
    assert "channel_platform_configs: _channelConfigsForSave(_channelConfigDrafts)" in CHANNELS_JS
    assert "_ensureChannelGatewayStatusLoaded()" in CHANNELS_JS
    assert "api('/api/gateway/status')" in CHANNELS_JS
    assert "_channelGatewayStatus.platforms" in CHANNELS_JS
    assert "name !== platformKey" in CHANNELS_JS
    assert "function _renderChannelDetailStatus(platform)" in CHANNELS_JS
    assert "function _channelStatusClass(configured)" in CHANNELS_JS
    assert "channelConfigStatusBadge" in CHANNELS_JS
    assert "badge.className = `channel-storage-badge ${_channelStatusClass(configured)}`" in CHANNELS_JS
    assert '<span class="${_channelStatusClass(configured)}">' in CHANNELS_JS
    assert "channels_status_configured" in CHANNELS_JS
    assert "channels_status_not_configured" in CHANNELS_JS
    assert "function _channelHasPersistedConfig(platform)" in CHANNELS_JS
    assert "values[field.key + '_configured'] === true" in CHANNELS_JS
    assert "let _channelConfigAdapters = {}" in CHANNELS_JS
    assert "_channelConfigAdapters = Object.assign" in CHANNELS_JS
    assert "Open provider settings" not in panel_slice
    assert "Open gateway logs" not in main_slice
    assert "main.main > #mainChannels" in STYLE_CSS
    assert "main.main.showing-channels > #mainChannels" in STYLE_CSS
    assert "not(.showing-channels)" in STYLE_CSS
    assert ".channel-config-shell{display:block;width:100%;}" in STYLE_CSS
    assert ".channel-config-shell{display:grid;grid-template-columns" not in STYLE_CSS
    assert "channel-platform-option" in STYLE_CSS
    assert ".channel-status-configured{color:var(--success)" in STYLE_CSS
    assert "channel-storage-badge{font-size:11px;font-weight:700;padding:4px 9px;}" in STYLE_CSS
    assert "tab_channels" in I18N_JS
    assert "'频道'" in I18N_JS
    assert "channels_platform_selector_label" in I18N_JS
    assert "channels_status_configured" in I18N_JS
    assert "channels_status_not_configured" in I18N_JS
    assert "channels_storage_pending" in I18N_JS
    assert "configuration storage pending" not in I18N_JS
    assert "配置存储待接入" not in I18N_JS
    assert "channels_storage_pending_note" in I18N_JS
    assert "_ensureChannelConfigLoadedFromServer()" in CHANNELS_JS
    assert "settings.channel_platform_configs" in CHANNELS_JS
    assert "drafts[key] = Object.assign({}, values, drafts[key] || {})" in CHANNELS_JS
    assert "channels_save_draft: 'Save'" in I18N_JS
    assert "channels_reset_draft: 'Reset'" in I18N_JS
    assert "channels_save_draft: '保存'" in I18N_JS
    assert "channels_reset_draft: '重置'" in I18N_JS
    assert "platform_bot_token" in I18N_JS
    assert "platform_qr_login_pending" in I18N_JS
    assert "platform_qr_login_started" in I18N_JS
    assert "platform_qr_login_failed" in I18N_JS
    assert "platform_qr_login_image_alt" in I18N_JS
    assert "platform_qr_login_text_hint" in I18N_JS
    assert "platform_qr_login_copy" in I18N_JS
    assert "platform_qr_login_no_qr" in I18N_JS
    assert "providers_add_provider: 'Add provider'" in I18N_JS
    assert "providers_add_provider: '添加提供商'" in I18N_JS
