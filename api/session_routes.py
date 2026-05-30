"""
Session routes for /api/sessions endpoint.

Extracted from api/routes.py to reduce merge conflicts with upstream.
"""

import logging
import time
logger = logging.getLogger(__name__)


def _session_source_is_webui(session: dict) -> bool:
    """Return True for state.db/sidebar rows that describe WebUI-origin sessions."""
    if not isinstance(session, dict):
        return False
    for key in ("source_tag", "raw_source", "session_source", "source"):
        if str(session.get(key) or "").strip().lower() == "webui":
            return True
    return False


def _session_lineage_ids(session: dict) -> set[str]:
    """Return known ids that identify one logical sidebar lineage."""
    if not isinstance(session, dict):
        return set()
    ids: set[str] = set()
    for key in ("session_id", "_lineage_root_id", "_lineage_tip_id"):
        value = session.get(key)
        if value:
            ids.add(str(value))
    return ids


def _is_duplicate_webui_state_projection(session: dict, represented_webui_ids: set[str]) -> bool:
    """Return True when a state.db row is only a duplicate WebUI-origin projection.

    The "Show non-WebUI sessions" toggle should add external/agent-owned
    conversations, not make WebUI compression continuations appear only when the
    external-session bridge is enabled. WebUI-origin state.db rows are still
    useful metadata sidecars, but if any id in their compression lineage is
    already represented by WebUI session JSON, they should not be injected as an
    additive external row.
    """
    if not _session_source_is_webui(session):
        return False
    return bool(_session_lineage_ids(session) & represented_webui_ids)


def handle_sessions_endpoint(handler, parsed, j, bad):
    """Handle GET /api/sessions requests.

    Args:
        handler: The HTTP request handler.
        parsed: The parsed URL.
        j: JSON response helper.
        bad: Error response helper.

    Returns:
        True if the request was handled.
    """
    from api.routes import (
        RequestDiagnostics,
        _all_profiles_query_flag,
        _cap_recent_cli_sessions,
        _is_cli_session_for_settings,
        _is_messaging_session_record,
        _keep_latest_messaging_session_per_source,
        _merge_cli_sidebar_metadata,
        _dedupe_cli_sidebar_sessions_for_api,
        _normalize_sidebar_source_flags,
        _reconcile_stale_stream_state_for_session_rows,
        _redact_text,
        all_sessions,
        get_cli_sessions,
        is_cli_session_row_visible,
        load_settings,
        CLI_VISIBLE_SESSION_CAP,
    )
    from api.profiles import get_active_profile_name, _profiles_match

    diag = RequestDiagnostics.maybe_start("GET", parsed.path, logger=logger)
    try:
        diag.stage("all_sessions")
        webui_sessions = all_sessions(diag=diag)
        diag.stage("reconcile_stale_stream_state")
        if _reconcile_stale_stream_state_for_session_rows(webui_sessions):
            diag.stage("all_sessions_after_stale_stream_reconcile")
            webui_sessions = all_sessions(diag=diag)
        diag.stage("load_settings")
        settings = load_settings()
        show_cli_sessions = bool(settings.get("show_cli_sessions"))
        webui_sessions = [_normalize_sidebar_source_flags(s) for s in webui_sessions]
        if show_cli_sessions:
            diag.stage("get_cli_sessions")
            cli = get_cli_sessions()
            diag.stage("merge_cli_sessions")
            cli_by_id = {s["session_id"]: s for s in cli}
            for s in webui_sessions:
                meta = cli_by_id.get(s.get("session_id"))
                if not meta:
                    continue
                if _is_messaging_session_record(meta):
                    s.update(_merge_cli_sidebar_metadata(s, meta))
                    if s.get("session_id") != meta.get("session_id"):
                        s["session_id"] = meta.get("session_id")
                else:
                    for key in ("source_tag", "raw_source", "session_source", "source_label"):
                        if not s.get(key) and meta.get(key):
                            s[key] = meta[key]
            webui_sessions = [_normalize_sidebar_source_flags(s) for s in webui_sessions]
            webui_sessions = [s for s in webui_sessions if is_cli_session_row_visible(s)]
            represented_webui_ids = set()
            for s in webui_sessions:
                represented_webui_ids.update(_session_lineage_ids(s))
            deduped_cli = _dedupe_cli_sidebar_sessions_for_api(cli, represented_webui_ids)
        else:
            diag.stage("filter_webui_sessions")
            webui_sessions = [s for s in webui_sessions if not _is_cli_session_for_settings(s)]
            deduped_cli = []
        diag.stage("sort_sessions")
        merged = webui_sessions + deduped_cli
        merged.sort(
            key=lambda s: s.get("last_message_at") or s.get("updated_at", 0) or 0,
            reverse=True,
        )
        diag.stage("active_profile")
        active_profile = get_active_profile_name()
        all_profiles = _all_profiles_query_flag(parsed)
        diag.stage("profile_filter")
        if all_profiles:
            scoped = merged
            other_profile_count = 0
        else:
            scoped = [s for s in merged if _profiles_match(s.get("profile"), active_profile)]
            other_profile_count = len(merged) - len(scoped)
        diag.stage("messaging_dedupe")
        scoped = _keep_latest_messaging_session_per_source(
            scoped,
            show_previous_messaging_sessions=bool(
                settings.get("show_previous_messaging_sessions")
            ),
        )
        if show_cli_sessions:
            diag.stage("cli_cap")
            scoped = _cap_recent_cli_sessions(scoped, cli_cap=CLI_VISIBLE_SESSION_CAP)
        diag.stage("redact_sessions")
        safe_merged = []
        for s in scoped:
            item = dict(s)
            if isinstance(item.get("title"), str):
                item["title"] = _redact_text(item["title"])
            safe_merged.append(item)
        diag.stage("response_write")
        return j(handler, {
            "sessions": safe_merged,
            "cli_count": len(deduped_cli),
            "all_profiles": all_profiles,
            "active_profile": active_profile,
            "other_profile_count": other_profile_count,
            "server_time": time.time(),
            "server_tz": time.strftime("%z"),
        })
    finally:
        diag.finish()
