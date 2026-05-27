"""Regression tests for custom provider modal refresh wiring.

Ensures the refresh button passes a provider id string (or a safe custom
fallback) instead of the raw provider object, and remains visible with the
expected label/icon wiring in both saved and unsaved-provider flows.
"""

import pathlib

REPO = pathlib.Path(__file__).parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


class TestCustomProviderRefreshButton:
    def test_refresh_button_does_not_pass_raw_provider_object(self):
        src = read("static/provider-config.js")
        assert "_refreshProviderModels(provider||{id:''}, refreshBtn)" not in src, (
            "refresh button must not pass the raw provider object; new providers "
            "have no id and end up posting {id:''} as the provider"
        )

    def test_refresh_button_uses_provider_id_or_custom_fallback(self):
        src = read("static/provider-config.js")
        assert "const providerId=(provider&&typeof provider==='object'&&typeof provider.id==='string'&&provider.id.trim())" in src
        assert ": 'custom';" in src, (
            "refresh button should fall back to 'custom' for unsaved providers"
        )
        assert "refreshBtn.onclick=()=>_refreshProviderModels(providerId, refreshBtn);" in src, (
            "refresh button should pass the normalized providerId string to the refresh handler"
        )

    def test_refresh_button_is_forced_visible(self):
        src = read("static/provider-config.js")
        assert "refreshBtn.hidden=false;" in src, (
            "refresh button should be explicitly shown in the provider modal"
        )

    def test_refresh_button_restores_icon_and_label(self):
        src = read("static/provider-config.js")
        assert "refreshBtn.innerHTML=_providerModelRefreshIcon()+' '+esc(t('providers_refresh_models'));" in src, (
            "refresh button should render the refresh icon plus i18n label"
        )
