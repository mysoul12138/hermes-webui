from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


PROJECTION_VERSION = 1
_MESSAGING_SOURCES = {
    "telegram",
    "slack",
    "discord",
    "wechat",
    "whatsapp",
    "signal",
}
_CONTINUATION_END_REASONS = {"compression", "cli_close"}
_UNKNOWN_SOURCES = {"", "unknown", "other"}


@dataclass(frozen=True)
class SessionProjectionContext:
    conversations: list[dict[str, Any]]
    conversation_by_session_id: dict[str, dict[str, Any]]
    child_relationship_by_session_id: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class VisibleSessionProjectionRows:
    rows: list[dict[str, Any]]
    projection_context: SessionProjectionContext
    cli_count: int = 0
    all_profiles: bool = False
    active_profile: str = "default"
    other_profile_count: int = 0


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _session_id(row: dict[str, Any]) -> str | None:
    value = row.get("session_id") or row.get("id")
    return _safe_str(value) or None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float_or_none(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def normalize_source(source: Any) -> dict[str, str]:
    normalized = _safe_str(source).lower().replace("-", "_")
    if not normalized:
        normalized = "unknown"
    if normalized == "webui":
        session_source = "webui"
    elif normalized == "cli":
        session_source = "cli"
    elif normalized in _MESSAGING_SOURCES:
        session_source = "messaging"
    elif normalized in {"api", "api_server"}:
        session_source = "api"
    else:
        session_source = "other"
    return {"source": normalized, "session_source": session_source}


def webui_session_to_canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    source_info = normalize_source(row.get("source") or row.get("source_tag") or "webui")
    metadata = dict(row.get("metadata") or {})
    for key in ("source_tag", "raw_source", "profile", "updated_at", "created_at"):
        if row.get(key) is not None and key not in metadata:
            metadata[key] = row.get(key)
    return {
        "session_id": _session_id(row),
        "title": row.get("title"),
        "source": source_info["source"],
        "session_source": row.get("session_source") or source_info["session_source"],
        "parent_session_id": row.get("parent_session_id") or None,
        "started_at": _as_float_or_none(row.get("started_at") or row.get("created_at")),
        "ended_at": _as_float_or_none(row.get("ended_at")),
        "end_reason": row.get("end_reason"),
        "message_count": _as_int(row.get("message_count")),
        "last_activity": _as_float_or_none(
            row.get("last_message_at") or row.get("updated_at") or row.get("created_at")
        ),
        "metadata": metadata,
    }


def agent_session_to_canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    source_info = normalize_source(row.get("source") or row.get("raw_source"))
    metadata = dict(row.get("metadata") or {})
    for key in (
        "actual_message_count",
        "source_label",
        "source_tag",
        "raw_source",
        "profile",
        "chat_id",
        "thread_id",
        "session_key",
    ):
        if row.get(key) is not None and key not in metadata:
            metadata[key] = row.get(key)
    return {
        "session_id": _session_id(row),
        "title": row.get("title"),
        "source": source_info["source"],
        "session_source": row.get("session_source") or source_info["session_source"],
        "parent_session_id": row.get("parent_session_id") or None,
        "started_at": _as_float_or_none(row.get("started_at") or row.get("created_at")),
        "ended_at": _as_float_or_none(row.get("ended_at")),
        "end_reason": row.get("end_reason"),
        "message_count": _as_int(row.get("message_count")),
        "last_activity": _as_float_or_none(
            row.get("last_activity") or row.get("last_message_at") or row.get("updated_at")
        ),
        "metadata": metadata,
    }


def _canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    if "session_id" not in row and "id" in row:
        canonical = webui_session_to_canonical_row(row)
        if "source" in row and not _safe_str(row.get("source")):
            canonical["source"] = "unknown"
            canonical["session_source"] = "other"
    else:
        canonical = dict(row)
        canonical["session_id"] = _session_id(row)
        source_info = normalize_source(canonical.get("source"))
        canonical["source"] = source_info["source"]
        canonical["session_source"] = canonical.get("session_source") or source_info["session_source"]
        canonical["parent_session_id"] = canonical.get("parent_session_id") or None
        canonical["started_at"] = _as_float_or_none(canonical.get("started_at") or canonical.get("created_at"))
        canonical["ended_at"] = _as_float_or_none(canonical.get("ended_at"))
        canonical["message_count"] = _as_int(canonical.get("message_count"))
        canonical["last_activity"] = _as_float_or_none(
            canonical.get("last_activity") or canonical.get("last_message_at") or canonical.get("updated_at")
        )
        canonical.setdefault("metadata", dict(row.get("metadata") or {}))
    return canonical


def classify_relationship(parent: dict[str, Any] | None, child: dict[str, Any] | None) -> str:
    if not parent or not child:
        return "child_session"
    if _safe_str(child.get("session_source")).lower() == "fork":
        return "child_session"
    parent_source = normalize_source(parent.get("source")).get("source", "unknown")
    child_source = normalize_source(child.get("source")).get("source", "unknown")
    if parent_source in _UNKNOWN_SOURCES or child_source in _UNKNOWN_SOURCES:
        return "child_session"
    if parent_source != child_source:
        return "child_session"
    if parent.get("end_reason") not in _CONTINUATION_END_REASONS:
        return "child_session"
    parent_ended_at = _as_float_or_none(parent.get("ended_at"))
    child_started_at = _as_float_or_none(child.get("started_at"))
    if parent_ended_at is None or child_started_at is None:
        return "child_session"
    if child_started_at < parent_ended_at:
        return "child_session"
    return "continuation"


def _find_cycle_nodes(rows_by_id: dict[str, dict[str, Any]]) -> set[str]:
    cyclic: set[str] = set()
    for sid in rows_by_id:
        seen: set[str] = set()
        current = sid
        while current:
            if current in seen:
                cyclic.update(seen)
                break
            seen.add(current)
            parent = rows_by_id.get(current, {}).get("parent_session_id")
            if parent not in rows_by_id:
                break
            current = parent
    return cyclic


def _sort_key(row: dict[str, Any]) -> tuple[float, str]:
    ts = _as_float_or_none(row.get("started_at") or row.get("last_activity")) or 0
    return (float(ts), _safe_str(row.get("session_id")))


def _child_summary(
    child: dict[str, Any],
    *,
    parent_session_id: str,
    parent_root_session_id: str,
    relationship_type: str = "child_session",
) -> dict[str, Any]:
    summary = {
        "session_id": child.get("session_id"),
        "parent_session_id": parent_session_id,
        "parent_root_session_id": parent_root_session_id,
        "relationship_type": relationship_type,
        "source": child.get("source"),
        "title": child.get("title"),
        "started_at": child.get("started_at"),
    }
    if child.get("session_source") == "fork":
        summary["is_fork"] = True
    return summary


def _segment_for(
    row: dict[str, Any],
    relationship_type: str,
    messages_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    sid = row.get("session_id")
    segment = {
        "session_id": sid,
        "parent_session_id": row.get("parent_session_id"),
        "relationship_type": relationship_type,
        "source": row.get("source"),
        "title": row.get("title"),
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "end_reason": row.get("end_reason"),
        "message_count": row.get("message_count"),
    }
    if messages_metadata and sid in messages_metadata:
        segment["messages_metadata"] = messages_metadata[sid]
    return segment


def project_conversations(
    rows: Iterable[dict[str, Any]],
    *,
    messages_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    canonical_rows = [_canonicalize_row(row) for row in rows]
    canonical_rows = [row for row in canonical_rows if row.get("session_id")]
    rows_by_id = {row["session_id"]: row for row in canonical_rows}
    cyclic = _find_cycle_nodes(rows_by_id)

    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    continuation_candidates: dict[str, list[dict[str, Any]]] = {}
    for row in canonical_rows:
        sid = row["session_id"]
        parent_id = row.get("parent_session_id")
        parent = rows_by_id.get(parent_id)
        if not parent or sid in cyclic or parent_id in cyclic:
            continue
        children_by_parent.setdefault(parent_id, []).append(row)
        if classify_relationship(parent, row) == "continuation":
            continuation_candidates.setdefault(parent_id, []).append(row)

    merge_child_by_parent: dict[str, str] = {}
    merge_parent_by_child: dict[str, str] = {}
    for parent_id, candidates in continuation_candidates.items():
        if len(candidates) == 1:
            child_id = candidates[0]["session_id"]
            merge_child_by_parent[parent_id] = child_id
            merge_parent_by_child[child_id] = parent_id

    conversations: list[dict[str, Any]] = []
    visited_segments: set[str] = set()
    roots = [
        row for row in sorted(canonical_rows, key=_sort_key)
        if row["session_id"] not in merge_parent_by_child
    ]
    for root in roots:
        root_id = root["session_id"]
        if root_id in visited_segments:
            continue
        segments: list[dict[str, Any]] = []
        represented_ids: list[str] = []
        segment_ids: set[str] = set()
        current = root
        relationship_type = "root"
        while current and current["session_id"] not in segment_ids:
            sid = current["session_id"]
            represented_ids.append(sid)
            segment_ids.add(sid)
            visited_segments.add(sid)
            segments.append(_segment_for(current, relationship_type, messages_metadata))
            next_id = merge_child_by_parent.get(sid)
            current = rows_by_id.get(next_id) if next_id else None
            relationship_type = "continuation"

        child_sessions: list[dict[str, Any]] = []
        for segment_id in represented_ids:
            for child in sorted(children_by_parent.get(segment_id, []), key=_sort_key):
                child_id = child["session_id"]
                if merge_child_by_parent.get(segment_id) == child_id:
                    continue
                child_sessions.append(
                    _child_summary(
                        child,
                        parent_session_id=segment_id,
                        parent_root_session_id=root_id,
                    )
                )

        conversations.append(
            {
                "root_session_id": root_id,
                "tip_session_id": represented_ids[-1],
                "represented_session_ids": represented_ids,
                "segments": segments,
                "child_sessions": child_sessions,
            }
        )
    return conversations


def build_session_projection_context(rows: Iterable[dict[str, Any]]) -> SessionProjectionContext:
    conversations = project_conversations(rows)
    conversation_by_session_id: dict[str, dict[str, Any]] = {}
    child_relationship_by_session_id: dict[str, dict[str, Any]] = {}
    for conversation in conversations:
        for sid in conversation["represented_session_ids"]:
            conversation_by_session_id[sid] = conversation
        for child in conversation["child_sessions"]:
            child_relationship_by_session_id[child["session_id"]] = child
    return SessionProjectionContext(
        conversations=conversations,
        conversation_by_session_id=conversation_by_session_id,
        child_relationship_by_session_id=child_relationship_by_session_id,
    )


def _apply_projection(row: dict[str, Any], context: SessionProjectionContext) -> dict[str, Any]:
    sid = _session_id(row)
    if not sid:
        return row
    conversation = context.conversation_by_session_id.get(sid)
    if conversation:
        row["projection_version"] = PROJECTION_VERSION
        row["canonical_session_id"] = conversation["root_session_id"]
        row["root_session_id"] = conversation["root_session_id"]
        row["tip_session_id"] = conversation["tip_session_id"]
        row["lineage_key"] = conversation["root_session_id"]
        row["represented_session_ids"] = list(conversation["represented_session_ids"])
        row["lineage_segments"] = [dict(segment) for segment in conversation["segments"]]
        row["child_sessions"] = [dict(child) for child in conversation["child_sessions"]]

    child = context.child_relationship_by_session_id.get(sid)
    if child:
        row["projection_version"] = PROJECTION_VERSION
        row.setdefault("canonical_session_id", sid)
        row.setdefault("root_session_id", sid)
        row.setdefault("tip_session_id", sid)
        row.setdefault("lineage_key", sid)
        row.setdefault("represented_session_ids", [sid])
        row.setdefault(
            "lineage_segments",
            [
                {
                    "session_id": sid,
                    "parent_session_id": row.get("parent_session_id"),
                    "relationship_type": "root",
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "started_at": row.get("started_at"),
                    "ended_at": row.get("ended_at"),
                    "end_reason": row.get("end_reason"),
                    "message_count": row.get("message_count"),
                }
            ],
        )
        row.setdefault("child_sessions", [])
        row["relationship_type"] = child["relationship_type"]
        row["parent_session_id"] = child["parent_session_id"]
        row["parent_root_session_id"] = child["parent_root_session_id"]
        row["projected_child_session"] = True
    return row


def attach_session_projection_fields(
    rows: Iterable[dict[str, Any]],
    *,
    projection_context: SessionProjectionContext | None = None,
) -> list[dict[str, Any]]:
    copied = [dict(row) for row in rows]
    context = projection_context or build_session_projection_context(copied)
    return [_apply_projection(row, context) for row in copied]


def attach_session_projection_metadata(
    row: dict[str, Any],
    projection_context: SessionProjectionContext,
) -> dict[str, Any]:
    return _apply_projection(row, projection_context)


def attach_session_projection_metadata_to_rows(
    rows: Iterable[dict[str, Any]],
    projection_context: SessionProjectionContext,
) -> list[dict[str, Any]]:
    if isinstance(rows, list):
        for index, row in enumerate(rows):
            rows[index] = attach_session_projection_metadata(row, projection_context)
        return rows
    return [attach_session_projection_metadata(dict(row), projection_context) for row in rows]


def _sort_session_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> float:
        return float(
            _as_float_or_none(
                row.get("last_message_at") or row.get("updated_at") or row.get("created_at") or row.get("started_at")
            )
            or 0
        )

    return sorted([dict(row) for row in rows], key=key, reverse=True)


def build_visible_session_projection_rows(
    webui_rows: Iterable[dict[str, Any]],
    *,
    show_cli_sessions: bool,
    is_cli_session_for_settings: Callable[[dict[str, Any]], bool],
    profiles_match: Callable[[Any, Any], bool],
    active_profile: str,
    all_profiles: bool,
    cli_rows: Iterable[dict[str, Any]] | None = None,
    is_cli_session_row_visible: Callable[[dict[str, Any]], bool] | None = None,
    hide_from_default_sidebar: Callable[[dict[str, Any]], bool] | None = None,
    merge_cli_sidebar_metadata: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
    keep_latest_messaging_session_per_source: Callable[..., list[dict[str, Any]]] | None = None,
    cap_recent_cli_sessions: Callable[..., list[dict[str, Any]]] | None = None,
    show_previous_messaging_sessions: bool = False,
    cli_cap: int = 20,
) -> VisibleSessionProjectionRows:
    webui = [dict(row) for row in webui_rows]
    cli = [dict(row) for row in (cli_rows or [])]
    is_cli_session_row_visible = is_cli_session_row_visible or (lambda row: True)
    hide_from_default_sidebar = hide_from_default_sidebar or (lambda row: False)
    merge_cli_sidebar_metadata = merge_cli_sidebar_metadata or (lambda row, meta: {**row, **meta})

    if show_cli_sessions:
        cli_by_id = {row.get("session_id"): row for row in cli if row.get("session_id")}
        merged_webui: list[dict[str, Any]] = []
        for row in webui:
            meta = cli_by_id.get(row.get("session_id"))
            if meta:
                row = merge_cli_sidebar_metadata(row, meta)
            if is_cli_session_row_visible(row):
                merged_webui.append(row)
        webui_ids = {row.get("session_id") for row in merged_webui}
        deduped_cli = [
            row
            for row in cli
            if row.get("session_id") not in webui_ids
            and is_cli_session_row_visible(row)
        ]
        merged = merged_webui + deduped_cli
    else:
        deduped_cli = []
        merged = [row for row in webui if not is_cli_session_for_settings(row)]

    sorted_rows = _sort_session_rows(merged)
    if all_profiles:
        scoped = sorted_rows
        other_profile_count = 0
    else:
        scoped = [row for row in sorted_rows if profiles_match(row.get("profile"), active_profile)]
        other_profile_count = len(sorted_rows) - len(scoped)

    if keep_latest_messaging_session_per_source:
        scoped = keep_latest_messaging_session_per_source(
            scoped,
            show_previous_messaging_sessions=show_previous_messaging_sessions,
        )
    if show_cli_sessions and cap_recent_cli_sessions:
        scoped = cap_recent_cli_sessions(scoped, cli_cap=cli_cap)

    context = build_session_projection_context(sorted_rows)
    return VisibleSessionProjectionRows(
        rows=[dict(row) for row in scoped],
        projection_context=context,
        cli_count=len(deduped_cli),
        all_profiles=all_profiles,
        active_profile=active_profile,
        other_profile_count=other_profile_count,
    )
