from api.conversation_projection import classify_relationship, project_conversations


def _row(
    session_id,
    *,
    parent=None,
    source="webui",
    started_at=0,
    ended_at=None,
    end_reason=None,
    session_source=None,
    title=None,
):
    return {
        "id": session_id,
        "title": title or session_id,
        "source": source,
        "session_source": session_source,
        "started_at": started_at,
        "ended_at": ended_at,
        "end_reason": end_reason,
        "parent_session_id": parent,
    }


def _by_root(conversations):
    return {conversation["root_session_id"]: conversation for conversation in conversations}


def test_source_mismatch_does_not_merge_continuation():
    parent = _row("parent", ended_at=10, end_reason="compression")
    child = _row("child", parent="parent", source="cli", started_at=11)

    conversations = _by_root(project_conversations([parent, child]))

    assert classify_relationship(parent, child) == "child_session"
    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert conversations["child"]["represented_session_ids"] == ["child"]
    assert conversations["parent"]["child_sessions"][0]["session_id"] == "child"


def test_fork_child_does_not_merge_with_compression_parent():
    parent = _row("parent", ended_at=10, end_reason="compression")
    fork = _row("forked", parent="parent", started_at=11, session_source="fork")

    conversations = _by_root(project_conversations([parent, fork]))

    assert classify_relationship(parent, fork) == "child_session"
    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert conversations["forked"]["represented_session_ids"] == ["forked"]
    assert conversations["parent"]["child_sessions"][0]["is_fork"] is True


def test_child_session_is_not_mixed_into_parent_segments():
    parent = _row("parent", ended_at=10, end_reason="user_stop")
    child = _row("child", parent="parent", started_at=11)

    conversations = _by_root(project_conversations([parent, child]))

    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert [segment["session_id"] for segment in conversations["parent"]["segments"]] == ["parent"]
    assert conversations["parent"]["child_sessions"][0]["relationship_type"] == "child_session"
    assert conversations["parent"]["child_sessions"][0]["session_id"] == "child"
    assert conversations["child"]["represented_session_ids"] == ["child"]


def test_compression_chain_projects_as_one_canonical_conversation():
    rows = [
        _row("root", started_at=1, ended_at=10, end_reason="compression", title="Original"),
        _row("middle", parent="root", started_at=10, ended_at=20, end_reason="cli_close"),
        _row("tip", parent="middle", started_at=21, title="Current"),
    ]

    conversations = project_conversations(
        rows,
        messages_metadata={"tip": {"message_count": 7}},
    )

    assert len(conversations) == 1
    conversation = conversations[0]
    assert conversation["root_session_id"] == "root"
    assert conversation["tip_session_id"] == "tip"
    assert conversation["represented_session_ids"] == ["root", "middle", "tip"]
    assert [segment["relationship_type"] for segment in conversation["segments"]] == [
        "root",
        "continuation",
        "continuation",
    ]
    assert conversation["segments"][-1]["messages_metadata"] == {"message_count": 7}


def test_started_before_parent_ended_at_boundary_does_not_merge():
    parent = _row("parent", started_at=1, ended_at=10, end_reason="compression")
    overlapping = _row("overlapping", parent="parent", started_at=9)

    conversations = _by_root(project_conversations([parent, overlapping]))

    assert classify_relationship(parent, overlapping) == "child_session"
    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert conversations["overlapping"]["represented_session_ids"] == ["overlapping"]
    assert conversations["parent"]["child_sessions"][0]["session_id"] == "overlapping"


def test_cycle_detection_keeps_cyclic_links_out_of_represented_segments():
    first = _row("first", parent="second", started_at=20, ended_at=30, end_reason="compression")
    second = _row("second", parent="first", started_at=40, ended_at=50, end_reason="compression")

    conversations = _by_root(project_conversations([first, second]))

    assert conversations["first"]["represented_session_ids"] == ["first"]
    assert conversations["second"]["represented_session_ids"] == ["second"]


def test_cyclic_parent_links_do_not_output_child_tree():
    first = _row("first", parent="second", started_at=20, ended_at=30, end_reason="compression")
    second = _row("second", parent="first", started_at=40, ended_at=50, end_reason="compression")

    conversations = _by_root(project_conversations([first, second]))

    assert conversations["first"]["child_sessions"] == []
    assert conversations["second"]["child_sessions"] == []


def test_cli_close_parent_allows_safe_continuation():
    parent = _row("parent", ended_at=10, end_reason="cli_close")
    child = _row("child", parent="parent", started_at=10)

    conversations = _by_root(project_conversations([parent, child]))

    assert classify_relationship(parent, child) == "continuation"
    assert conversations["parent"]["represented_session_ids"] == ["parent", "child"]
    assert conversations["parent"]["tip_session_id"] == "child"
    assert "child" not in conversations


def test_multiple_continuation_candidates_for_same_parent_stay_separate_children():
    parent = _row("parent", ended_at=10, end_reason="compression")
    first = _row("first", parent="parent", started_at=11)
    second = _row("second", parent="parent", started_at=12)

    conversations = _by_root(project_conversations([parent, first, second]))

    assert classify_relationship(parent, first) == "continuation"
    assert classify_relationship(parent, second) == "continuation"
    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert conversations["first"]["represented_session_ids"] == ["first"]
    assert conversations["second"]["represented_session_ids"] == ["second"]
    assert [child["session_id"] for child in conversations["parent"]["child_sessions"]] == [
        "first",
        "second",
    ]


def test_unknown_or_other_sources_are_not_same_source_continuations():
    for source in ("unknown", "other", ""):
        parent = _row("parent", source=source, ended_at=10, end_reason="compression")
        child = _row("child", parent="parent", source=source, started_at=11)

        conversations = _by_root(project_conversations([parent, child]))

        assert classify_relationship(parent, child) == "child_session"
        assert conversations["parent"]["represented_session_ids"] == ["parent"]
        assert conversations["child"]["represented_session_ids"] == ["child"]
        assert conversations["parent"]["child_sessions"][0]["session_id"] == "child"


def test_missing_parent_ended_at_does_not_merge_child_under_canonical_projection_policy():
    # New canonical projection uses a contamination-prevention policy: missing
    # ended_at never merges, even though legacy agent_sessions compatibility was looser.
    parent = _row("parent", ended_at=None, end_reason="compression")
    child = _row("child", parent="parent", started_at=11)

    conversations = _by_root(project_conversations([parent, child]))

    assert classify_relationship(parent, child) == "child_session"
    assert conversations["parent"]["represented_session_ids"] == ["parent"]
    assert conversations["child"]["represented_session_ids"] == ["child"]
    assert conversations["parent"]["child_sessions"][0]["session_id"] == "child"
