from api.conversation_projection import (
    attach_session_projection_fields,
    attach_session_projection_metadata,
    attach_session_projection_metadata_to_rows,
    build_session_projection_context,
    build_visible_session_projection_rows,
)
from api.conversation_projection.session_payload import build_route_visible_session_projection_rows


def _session(
    session_id,
    *,
    parent=None,
    source="webui",
    started_at=0,
    ended_at=None,
    end_reason=None,
    title=None,
):
    row = {
        "session_id": session_id,
        "title": title or session_id,
        "source": source,
        "started_at": started_at,
        "ended_at": ended_at,
        "end_reason": end_reason,
        "parent_session_id": parent,
        "message_count": 1,
    }
    if parent is None:
        row.pop("parent_session_id")
    return row


def _by_session_id(rows):
    return {row["session_id"]: row for row in rows}


def test_sessions_projection_payload_preserves_legacy_fields_and_adds_projection_fields():
    rows = attach_session_projection_fields(
        [
            _session(
                "root",
                started_at=1,
                ended_at=10,
                end_reason="compression",
                title="Legacy title",
            ),
            _session("tip", parent="root", started_at=11),
        ]
    )

    by_id = _by_session_id(rows)

    assert by_id["root"]["session_id"] == "root"
    assert by_id["root"]["title"] == "Legacy title"
    assert by_id["root"]["source"] == "webui"
    assert by_id["root"]["projection_version"] == 1
    assert by_id["root"]["canonical_session_id"] == "root"
    assert by_id["root"]["root_session_id"] == "root"
    assert by_id["root"]["tip_session_id"] == "tip"
    assert by_id["root"]["represented_session_ids"] == ["root", "tip"]
    assert [segment["session_id"] for segment in by_id["root"]["lineage_segments"]] == [
        "root",
        "tip",
    ]
    assert by_id["root"]["child_sessions"] == []


def test_sessions_projection_payload_keeps_unknown_source_rows_unmerged():
    rows = attach_session_projection_fields(
        [
            _session("parent", source="unknown", ended_at=10, end_reason="compression"),
            _session("child", parent="parent", source="unknown", started_at=11),
        ]
    )

    by_id = _by_session_id(rows)

    assert by_id["parent"]["represented_session_ids"] == ["parent"]
    assert by_id["child"]["represented_session_ids"] == ["child"]
    assert by_id["parent"]["child_sessions"][0]["session_id"] == "child"


def test_sessions_projection_payload_child_session_metadata_does_not_enter_represented_ids():
    rows = attach_session_projection_fields(
        [
            _session("parent", ended_at=10, end_reason="user_stop"),
            _session("child", parent="parent", started_at=11),
        ]
    )

    by_id = _by_session_id(rows)

    assert by_id["parent"]["represented_session_ids"] == ["parent"]
    assert by_id["child"]["represented_session_ids"] == ["child"]
    assert by_id["parent"]["child_sessions"] == [
        {
            "session_id": "child",
            "parent_session_id": "parent",
            "parent_root_session_id": "parent",
            "relationship_type": "child_session",
            "source": "webui",
            "title": "child",
            "started_at": 11,
        }
    ]
    assert by_id["child"]["relationship_type"] == "child_session"
    assert by_id["child"]["parent_session_id"] == "parent"
    assert by_id["child"]["parent_root_session_id"] == "parent"
    assert by_id["child"]["projected_child_session"] is True


def test_projection_annotation_marks_visible_child_row_without_raw_relationship_type():
    raw_rows = [
        _session("parent", ended_at=10, end_reason="user_stop"),
        _session("child", parent="parent", started_at=11),
    ]

    rows = attach_session_projection_fields(raw_rows)
    by_id = _by_session_id(rows)

    assert "relationship_type" not in raw_rows[1]
    assert by_id["parent"]["child_sessions"][0]["session_id"] == "child"
    assert by_id["child"]["relationship_type"] == "child_session"
    assert by_id["child"]["parent_session_id"] == "parent"
    assert by_id["child"]["parent_root_session_id"] == "parent"
    assert by_id["child"]["projected_child_session"] is True


def test_projection_annotation_keeps_orphan_visible_when_parent_row_is_absent():
    projection_context = build_session_projection_context(
        [
            _session("parent", ended_at=10, end_reason="user_stop"),
            _session("child", parent="parent", started_at=11),
        ]
    )

    rows = attach_session_projection_fields(
        [_session("child", parent="parent", started_at=11)],
        projection_context=projection_context,
    )

    assert len(rows) == 1
    assert rows[0]["session_id"] == "child"
    assert rows[0]["relationship_type"] == "child_session"
    assert rows[0]["parent_session_id"] == "parent"
    assert rows[0]["parent_root_session_id"] == "parent"
    assert rows[0]["projected_child_session"] is True


def test_projection_context_keeps_list_detail_and_search_metadata_consistent():
    raw_rows = [
        _session("root", started_at=1, ended_at=10, end_reason="compression"),
        _session("tip", parent="root", started_at=11),
    ]
    projection_context = build_session_projection_context(raw_rows)

    list_rows = _by_session_id(
        attach_session_projection_fields(raw_rows, projection_context=projection_context)
    )
    detail_row = attach_session_projection_metadata(
        dict(raw_rows[1]),
        projection_context,
    )
    search_row = attach_session_projection_metadata_to_rows(
        [dict(raw_rows[1], match_type="title")],
        projection_context,
    )[0]

    for row in (list_rows["tip"], detail_row, search_row):
        assert row["canonical_session_id"] == "root"
        assert row["root_session_id"] == "root"
        assert row["tip_session_id"] == "tip"
        assert row["represented_session_ids"] == ["root", "tip"]

    assert detail_row["session_id"] == "tip"
    assert search_row["session_id"] == "tip"
    assert search_row["match_type"] == "title"


def test_projection_context_keeps_child_sessions_out_of_transcript_segments():
    raw_rows = [
        _session("parent", ended_at=10, end_reason="user_stop"),
        _session("child", parent="parent", started_at=11),
    ]

    projection_context = build_session_projection_context(raw_rows)
    parent_detail = attach_session_projection_metadata(dict(raw_rows[0]), projection_context)
    child_detail = attach_session_projection_metadata(dict(raw_rows[1]), projection_context)

    assert parent_detail["represented_session_ids"] == ["parent"]
    assert [segment["session_id"] for segment in parent_detail["lineage_segments"]] == [
        "parent"
    ]
    assert parent_detail["child_sessions"][0]["session_id"] == "child"
    assert child_detail["represented_session_ids"] == ["child"]


def test_projection_context_does_not_merge_unknown_source_rows():
    raw_rows = [
        _session("parent", source="unknown", ended_at=10, end_reason="compression"),
        _session("child", parent="parent", source="unknown", started_at=11),
    ]

    projection_context = build_session_projection_context(raw_rows)
    detail_row = attach_session_projection_metadata(dict(raw_rows[1]), projection_context)
    search_row = attach_session_projection_metadata_to_rows(
        [dict(raw_rows[0], match_type="title")],
        projection_context,
    )[0]

    assert detail_row["canonical_session_id"] == "child"
    assert detail_row["represented_session_ids"] == ["child"]
    assert search_row["canonical_session_id"] == "parent"
    assert search_row["represented_session_ids"] == ["parent"]
    assert search_row["child_sessions"][0]["session_id"] == "child"


def test_visible_projection_rows_are_shared_by_list_detail_and_search_helpers():
    raw_rows = [
        _session("root", started_at=1, ended_at=10, end_reason="compression"),
        _session("tip", parent="root", started_at=11),
    ]
    visible = build_visible_session_projection_rows(
        raw_rows,
        show_cli_sessions=False,
        is_cli_session_for_settings=lambda row: False,
        profiles_match=lambda profile, active: True,
        active_profile="default",
        all_profiles=False,
    )

    list_rows = _by_session_id(
        attach_session_projection_fields(
            visible.rows,
            projection_context=visible.projection_context,
        )
    )
    detail_row = attach_session_projection_metadata(
        dict(raw_rows[1]),
        visible.projection_context,
    )
    search_row = attach_session_projection_metadata_to_rows(
        [dict(raw_rows[1], match_type="title")],
        visible.projection_context,
    )[0]

    expected = {
        "canonical_session_id": "root",
        "represented_session_ids": ["root", "tip"],
        "tip_session_id": "tip",
    }
    for row in (list_rows["tip"], detail_row, search_row):
        assert {key: row[key] for key in expected} == expected


def test_route_visible_projection_helper_accepts_fake_dependencies_for_context():
    raw_rows = [
        _session("root", started_at=1, ended_at=10, end_reason="compression"),
        _session("tip", parent="root", started_at=11),
        _session("other", started_at=12, title="Other", source="webui"),
    ]
    cli_rows = [
        _session("cli", source="cli", started_at=13, title="CLI"),
    ]
    calls = {"all_profiles_parser": 0, "cli_loader": 0}

    class _Parsed:
        query = "all_profiles=1"

    def all_profiles_parser(parsed):
        calls["all_profiles_parser"] += 1
        return "all_profiles=1" in parsed.query

    def get_cli_sessions_loader():
        calls["cli_loader"] += 1
        return [dict(row) for row in cli_rows]

    visible = build_route_visible_session_projection_rows(
        all_sessions_loader=lambda: [dict(row) for row in raw_rows],
        get_cli_sessions_loader=get_cli_sessions_loader,
        load_settings_loader=lambda: {"show_cli_sessions": True},
        get_active_profile_name=lambda: "default",
        all_profiles_parser=all_profiles_parser,
        is_cli_session_for_settings=lambda row: row.get("source") == "cli",
        profiles_match=lambda profile, active: True,
        is_cli_session_row_visible=lambda row: True,
        hide_from_default_sidebar=lambda row: False,
        merge_cli_sidebar_metadata=lambda row, meta: {**row, **meta},
        keep_latest_messaging_session_per_source=lambda rows, **kwargs: rows,
        cap_recent_cli_sessions=lambda rows, **kwargs: rows,
        parsed=_Parsed(),
        cli_cap=99,
    )

    by_id = _by_session_id(visible.rows)

    assert calls == {"all_profiles_parser": 1, "cli_loader": 1}
    assert visible.all_profiles is True
    assert by_id["tip"]["session_id"] == "tip"
    assert by_id["cli"]["source"] == "cli"
    assert (
        attach_session_projection_metadata(
            dict(raw_rows[1]),
            visible.projection_context,
        )["canonical_session_id"]
        == "root"
    )


def test_visible_projection_keeps_cron_cli_rows_for_project_filter():
    cli_rows = [
        _session(
            "cron_daily_123",
            source="cron",
            started_at=13,
            title="Daily cron",
        )
        | {
            "project_id": "cron-project",
            "source_tag": "cron",
            "raw_source": "cron",
            "session_source": "cron",
            "is_cli_session": True,
        }
    ]

    visible = build_visible_session_projection_rows(
        [],
        show_cli_sessions=True,
        is_cli_session_for_settings=lambda row: False,
        profiles_match=lambda profile, active: True,
        active_profile="default",
        all_profiles=False,
        cli_rows=cli_rows,
        is_cli_session_row_visible=lambda row: True,
        hide_from_default_sidebar=lambda row: row.get("source_tag") == "cron",
        merge_cli_sidebar_metadata=lambda row, meta: {**row, **meta},
        keep_latest_messaging_session_per_source=lambda rows, **kwargs: rows,
        cap_recent_cli_sessions=lambda rows, **kwargs: rows,
    )

    assert visible.rows[0]["session_id"] == "cron_daily_123"
    assert visible.rows[0]["project_id"] == "cron-project"
    assert visible.rows[0]["source_tag"] == "cron"
