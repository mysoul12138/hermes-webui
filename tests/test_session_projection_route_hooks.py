import api.routes as routes
from api.conversation_projection import (
    attach_session_projection_fields,
)
from api.conversation_projection.session_payload import build_route_visible_session_projection_rows


def _session(
    session_id,
    *,
    parent=None,
    source="webui",
    profile="default",
    started_at=0,
    ended_at=None,
    end_reason=None,
):
    row = {
        "session_id": session_id,
        "title": session_id,
        "source": source,
        "profile": profile,
        "started_at": started_at,
        "ended_at": ended_at,
        "end_reason": end_reason,
        "parent_session_id": parent,
        "message_count": 1,
    }
    if parent is None:
        row.pop("parent_session_id")
    return row


def _patch_projection_context(monkeypatch, rows):
    monkeypatch.setattr(
        routes, "all_sessions", lambda *args, **kwargs: [dict(row) for row in rows]
    )
    monkeypatch.setattr(routes, "get_cli_sessions", lambda: [])
    monkeypatch.setattr(routes, "load_settings", lambda: {"show_cli_sessions": False})
    monkeypatch.setattr(routes, "_redact_text", lambda text: text)
    monkeypatch.setattr(routes, "_is_cli_session_for_settings", lambda row: False)
    monkeypatch.setattr(routes, "_profiles_match", lambda profile, active: True)
    monkeypatch.setattr(routes, "_keep_latest_messaging_session_per_source", lambda rows, **kwargs: rows)
    monkeypatch.setattr(routes, "_cap_recent_cli_sessions", lambda rows, **kwargs: rows)
    monkeypatch.setattr(routes, "is_cli_session_row_visible", lambda row: True)
    monkeypatch.setattr(routes, "_is_messaging_session_record", lambda row: False)
    monkeypatch.setattr(routes, "_merge_cli_sidebar_metadata", lambda row, meta: row)
    monkeypatch.setattr(routes, "CLI_VISIBLE_SESSION_CAP", 25)
    import api.profiles as profiles
    monkeypatch.setattr(profiles, "get_active_profile_name", lambda: "default")
    monkeypatch.setattr(routes, "j", lambda _handler, payload, **_kwargs: payload)
    monkeypatch.setattr(
        routes._reconcile_stale_stream_state_for_session_rows,
        "last_run_at",
        None,
        raising=False,
    )
    monkeypatch.setattr(
        routes, "_reconcile_stale_stream_state_for_session_rows", lambda _rows: False
    )


class _Handler:
    headers = {}
    client_address = ("127.0.0.1", 0)


def test_route_hooks_share_projection_metadata_for_list_detail_and_search(monkeypatch):
    rows = [
        _session("root", started_at=1, ended_at=10, end_reason="compression"),
        _session("tip", parent="root", started_at=11),
    ]
    _patch_projection_context(monkeypatch, rows)

    list_rows = {
        row["session_id"]: row
        for row in attach_session_projection_fields([dict(row) for row in rows])
    }
    detail = routes._attach_projection_metadata(dict(rows[1]))
    search_rows = routes._attach_projection_metadata_to_rows(
        [dict(rows[1], match_type="title")]
    )
    search = search_rows[0]

    for row in (list_rows["tip"], detail, search):
        assert row["canonical_session_id"] == "root"
        assert row["root_session_id"] == "root"
        assert row["tip_session_id"] == "tip"
        assert row["represented_session_ids"] == ["root", "tip"]

    assert detail["session_id"] == "tip"
    assert search["session_id"] == "tip"
    assert search["match_type"] == "title"


def test_list_detail_and_search_use_single_route_projection_builder(monkeypatch):
    rows = [
        _session("root", started_at=1, ended_at=10, end_reason="compression"),
        _session("tip", parent="root", started_at=11),
    ]
    _patch_projection_context(monkeypatch, rows)
    calls = []

    def spy_builder(**kwargs):
        calls.append(
            {
                "parsed": kwargs.get("parsed"),
                "webui_rows": kwargs.get("webui_rows"),
                "settings": kwargs.get("settings"),
                "all_profiles": kwargs.get("all_profiles"),
            }
        )
        return build_route_visible_session_projection_rows(**kwargs)

    monkeypatch.setattr(routes, "build_route_visible_session_projection_rows", spy_builder)

    import urllib.parse

    list_payload = routes.handle_get(_Handler(), urllib.parse.urlparse("/api/sessions"))
    detail = routes._attach_projection_metadata(dict(rows[1]))
    search_payload = routes._handle_sessions_search(
        _Handler(),
        urllib.parse.urlparse("/api/sessions/search?q=tip&content=0"),
    )

    assert list_payload["sessions"][1]["canonical_session_id"] == "root"
    assert detail["canonical_session_id"] == "root"
    assert search_payload["sessions"][0]["canonical_session_id"] == "root"
    assert len(calls) == 3
    assert calls[0]["parsed"].path == "/api/sessions"
    assert calls[0]["webui_rows"] is not None
    assert calls[0]["settings"] == {"show_cli_sessions": False}
    assert calls[1]["parsed"] is None
    assert calls[2]["parsed"].path == "/api/sessions/search"
    assert calls[2]["all_profiles"] is None


def test_all_profiles_search_uses_all_profiles_projection_scope(monkeypatch):
    rows = [
        _session(
            "other-root",
            profile="other",
            started_at=1,
            ended_at=10,
            end_reason="compression",
        ),
        _session("other-tip", parent="other-root", profile="other", started_at=11),
    ]
    _patch_projection_context(monkeypatch, rows)
    monkeypatch.setattr(routes, "_profiles_match", lambda profile, active: profile == active)

    import urllib.parse

    active_payload = routes._handle_sessions_search(
        _Handler(),
        urllib.parse.urlparse("/api/sessions/search?q=other-tip&content=0"),
    )
    all_profiles_payload = routes._handle_sessions_search(
        _Handler(),
        urllib.parse.urlparse("/api/sessions/search?q=other-tip&content=0&all_profiles=1"),
    )
    list_payload = routes.handle_get(
        _Handler(),
        urllib.parse.urlparse("/api/sessions?all_profiles=1"),
    )
    detail = routes._attach_projection_metadata(
        dict(rows[1]),
        parsed=urllib.parse.urlparse("/api/sessions/search?all_profiles=1"),
    )

    all_profiles_search = all_profiles_payload["sessions"][0]
    list_tip = {
        row["session_id"]: row for row in list_payload["sessions"]
    }["other-tip"]

    assert active_payload["sessions"][0]["session_id"] == "other-tip"
    for row in (all_profiles_search, list_tip, detail):
        assert row["canonical_session_id"] == "other-root"
        assert row["represented_session_ids"] == ["other-root", "other-tip"]


def test_route_projection_child_session_does_not_enter_represented_ids(monkeypatch):
    rows = [
        _session("parent", ended_at=10, end_reason="user_stop"),
        _session("child", parent="parent", started_at=11),
    ]
    _patch_projection_context(monkeypatch, rows)

    parent = routes._attach_projection_metadata(dict(rows[0]))
    child = routes._attach_projection_metadata(dict(rows[1]))

    assert parent["represented_session_ids"] == ["parent"]
    assert [segment["session_id"] for segment in parent["lineage_segments"]] == [
        "parent"
    ]
    assert parent["child_sessions"][0]["session_id"] == "child"
    assert child["represented_session_ids"] == ["child"]
    assert child["relationship_type"] == "child_session"
    assert child["parent_session_id"] == "parent"
    assert child["parent_root_session_id"] == "parent"
    assert child["projected_child_session"] is True


def test_route_projection_marks_raw_child_rows_for_frontend_dedup(monkeypatch):
    rows = [
        _session("parent", ended_at=10, end_reason="user_stop"),
        _session("child", parent="parent", started_at=11),
    ]
    _patch_projection_context(monkeypatch, rows)

    list_rows = {
        row["session_id"]: row
        for row in attach_session_projection_fields([dict(row) for row in rows])
    }
    detail = routes._attach_projection_metadata(dict(rows[1]))
    search = routes._attach_projection_metadata_to_rows(
        [dict(rows[1], match_type="title")]
    )[0]

    assert "relationship_type" not in rows[1]
    for row in (list_rows["child"], detail, search):
        assert row["relationship_type"] == "child_session"
        assert row["parent_session_id"] == "parent"
        assert row["parent_root_session_id"] == "parent"
        assert row["projected_child_session"] is True
    assert search["match_type"] == "title"


def test_route_projection_unknown_source_does_not_merge(monkeypatch):
    rows = [
        _session("parent", source="unknown", ended_at=10, end_reason="compression"),
        _session("child", parent="parent", source="unknown", started_at=11),
    ]
    _patch_projection_context(monkeypatch, rows)

    parent = routes._attach_projection_metadata(dict(rows[0]))
    child = routes._attach_projection_metadata(dict(rows[1]))

    assert parent["canonical_session_id"] == "parent"
    assert parent["represented_session_ids"] == ["parent"]
    assert parent["child_sessions"][0]["session_id"] == "child"
    assert child["canonical_session_id"] == "child"
    assert child["represented_session_ids"] == ["child"]
