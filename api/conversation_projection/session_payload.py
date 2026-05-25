from __future__ import annotations

from dataclasses import replace
from typing import Any

from . import (
    VisibleSessionProjectionRows,
    build_session_projection_context,
    build_visible_session_projection_rows,
)


def build_route_visible_session_projection_rows(
    *,
    all_sessions_loader,
    get_cli_sessions_loader,
    load_settings_loader,
    get_active_profile_name,
    all_profiles_parser,
    is_cli_session_for_settings,
    profiles_match,
    is_cli_session_row_visible,
    hide_from_default_sidebar,
    merge_cli_sidebar_metadata,
    keep_latest_messaging_session_per_source,
    cap_recent_cli_sessions,
    parsed=None,
    webui_rows=None,
    settings=None,
    cli_rows=None,
    all_profiles=None,
    cli_cap=20,
) -> VisibleSessionProjectionRows:
    if webui_rows is not None:
        effective_webui_rows = [dict(row) for row in webui_rows]
    else:
        try:
            effective_webui_rows = [dict(row) for row in all_sessions_loader()]
        except TypeError:
            effective_webui_rows = [dict(row) for row in all_sessions_loader(diag=None)]
    effective_settings: dict[str, Any] = (
        dict(settings) if settings is not None else dict(load_settings_loader() or {})
    )
    show_cli_sessions = bool(effective_settings.get("show_cli_sessions"))
    effective_cli_rows = (
        [dict(row) for row in cli_rows]
        if cli_rows is not None
        else ([dict(row) for row in get_cli_sessions_loader()] if show_cli_sessions else [])
    )
    active_profile = get_active_profile_name()
    effective_all_profiles = (
        all_profiles_parser(parsed)
        if all_profiles is None and parsed is not None
        else bool(all_profiles)
    )

    visible = build_visible_session_projection_rows(
        effective_webui_rows,
        show_cli_sessions=show_cli_sessions,
        is_cli_session_for_settings=is_cli_session_for_settings,
        profiles_match=profiles_match,
        active_profile=active_profile,
        all_profiles=effective_all_profiles,
        cli_rows=effective_cli_rows,
        is_cli_session_row_visible=is_cli_session_row_visible,
        hide_from_default_sidebar=hide_from_default_sidebar,
        merge_cli_sidebar_metadata=merge_cli_sidebar_metadata,
        keep_latest_messaging_session_per_source=keep_latest_messaging_session_per_source,
        cap_recent_cli_sessions=cap_recent_cli_sessions,
        show_previous_messaging_sessions=bool(
            effective_settings.get("show_previous_messaging_sessions")
        ),
        cli_cap=cli_cap,
    )
    return replace(
        visible,
        projection_context=build_session_projection_context(visible.rows),
    )
