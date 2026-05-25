from api.conversation_projection import (
    agent_session_to_canonical_row,
    normalize_source,
    project_conversations,
    webui_session_to_canonical_row,
)


def test_webui_session_row_maps_to_canonical_contract():
    row = webui_session_to_canonical_row(
        {
            "session_id": "webui-1",
            "title": "WebUI task",
            "parent_session_id": "parent-1",
            "started_at": 10,
            "ended_at": 20,
            "end_reason": "compression",
            "message_count": "4",
            "updated_at": 25,
            "metadata": {"workspace": "/repo"},
        }
    )

    assert row == {
        "session_id": "webui-1",
        "title": "WebUI task",
        "source": "webui",
        "session_source": "webui",
        "parent_session_id": "parent-1",
        "started_at": 10,
        "ended_at": 20,
        "end_reason": "compression",
        "message_count": 4,
        "last_activity": 25,
        "metadata": {"workspace": "/repo", "updated_at": 25},
    }


def test_agent_row_maps_state_db_fields_to_canonical_contract():
    row = agent_session_to_canonical_row(
        {
            "id": "agent-1",
            "source": "telegram",
            "session_source": "messaging",
            "title": "Agent task",
            "started_at": 30,
            "parent_session_id": "agent-parent",
            "message_count": 7,
            "actual_message_count": 8,
            "last_activity": 35,
            "source_label": "Telegram",
        }
    )

    assert row["session_id"] == "agent-1"
    assert row["source"] == "telegram"
    assert row["session_source"] == "messaging"
    assert row["parent_session_id"] == "agent-parent"
    assert row["message_count"] == 7
    assert row["last_activity"] == 35
    assert row["metadata"]["actual_message_count"] == 8
    assert row["metadata"]["source_label"] == "Telegram"


def test_missing_fields_are_compatible_and_conservative():
    row = agent_session_to_canonical_row({"id": "minimal"})

    assert row["session_id"] == "minimal"
    assert row["title"] is None
    assert row["source"] == "unknown"
    assert row["session_source"] == "other"
    assert row["parent_session_id"] is None
    assert row["message_count"] == 0
    assert row["last_activity"] is None
    assert row["metadata"] == {}


def test_source_normalization_preserves_source_boundaries():
    assert normalize_source("webui") == {"source": "webui", "session_source": "webui"}
    assert normalize_source("cli") == {"source": "cli", "session_source": "cli"}
    assert normalize_source("telegram") == {"source": "telegram", "session_source": "messaging"}
    assert normalize_source("api-server") == {"source": "api_server", "session_source": "api"}
    assert normalize_source("new_surface") == {"source": "new_surface", "session_source": "other"}
    assert normalize_source(None) == {"source": "unknown", "session_source": "other"}


def test_metadata_is_preserved_without_losing_top_level_source_hints():
    row = webui_session_to_canonical_row(
        {
            "id": "webui-meta",
            "source_tag": "browser",
            "message_count": 2,
            "metadata": {"custom": {"nested": True}, "source_tag": "kept"},
            "profile": "default",
        }
    )

    assert row["metadata"] == {
        "custom": {"nested": True},
        "source_tag": "kept",
        "profile": "default",
    }


def test_agent_unknown_source_compression_rows_do_not_merge_in_projection():
    parent = agent_session_to_canonical_row(
        {
            "id": "parent",
            "started_at": 1,
            "ended_at": 10,
            "end_reason": "compression",
        }
    )
    child = agent_session_to_canonical_row(
        {
            "id": "child",
            "parent_session_id": "parent",
            "started_at": 11,
        }
    )

    conversations = {
        conversation["root_session_id"]: conversation
        for conversation in project_conversations([parent, child])
    }

    assert parent["source"] == "unknown"
    assert child["source"] == "unknown"
    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert conversations["child"]["represented_session_ids"] == ["child"]
    assert conversations["parent"]["child_sessions"][0]["session_id"] == "child"
