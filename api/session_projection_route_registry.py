"""Session projection route registration.

The projection builder still lives in the existing modules; this file only owns
the route-to-handler dispatch so new projection endpoints do not edit routes.py.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from api.route_registry import RouteRegistry


def register_session_projection_routes(registry: RouteRegistry) -> None:
    registry.get("/api/sessions", _list_sessions)
    registry.get("/api/sessions/search", _search_sessions)


def _list_sessions(handler, parsed, ctx):
    diag = ctx.RequestDiagnostics.maybe_start("GET", parsed.path, logger=ctx.logger)
    try:
        diag.stage("all_sessions")
        webui_sessions = ctx.all_sessions(diag=diag)
        diag.stage("reconcile_stale_stream_state")
        if ctx._reconcile_stale_stream_state_for_session_rows(webui_sessions):
            diag.stage("all_sessions_after_stale_stream_reconcile")
            webui_sessions = ctx.all_sessions(diag=diag)
        diag.stage("load_settings")
        settings = ctx.load_settings()
        diag.stage("visible_session_projection_rows")
        visible_projection = ctx._visible_session_projection_rows(
            parsed=parsed,
            webui_rows=webui_sessions,
            settings=settings,
        )
        safe_merged = ctx.attach_session_projection_fields(
            visible_projection.rows,
            projection_context=visible_projection.projection_context,
        )
        diag.stage("response_write")
        return ctx.j(
            handler,
            {
                "sessions": safe_merged,
                "cli_count": visible_projection.cli_count,
                "all_profiles": visible_projection.all_profiles,
                "active_profile": visible_projection.active_profile,
                "other_profile_count": visible_projection.other_profile_count,
                "server_time": ctx.time.time(),
                "server_tz": ctx.time.strftime("%z"),
            },
        )
    finally:
        diag.finish()


def _search_sessions(handler, parsed, ctx):
    qs = parse_qs(parsed.query)
    q = qs.get("q", [""])[0].lower().strip()
    content_search = qs.get("content", ["1"])[0] == "1"
    depth = int(qs.get("depth", ["5"])[0])
    if not q:
        safe_sessions = []
        for session in ctx.all_sessions():
            item = dict(session)
            if isinstance(item.get("title"), str):
                item["title"] = ctx._redact_text(item["title"])
            safe_sessions.append(item)
        ctx._attach_projection_metadata_to_rows(safe_sessions, parsed=parsed)
        return ctx.j(handler, {"sessions": safe_sessions})

    results = []
    for session in ctx.all_sessions():
        title_match = q in (session.get("title") or "").lower()
        if title_match:
            item = dict(session, match_type="title")
            if isinstance(item.get("title"), str):
                item["title"] = ctx._redact_text(item["title"])
            results.append(item)
            continue
        if content_search:
            try:
                loaded_session = ctx.get_session(session["session_id"])
                messages = loaded_session.messages[:depth] if depth else loaded_session.messages
                for message in messages:
                    content = message.get("content") or ""
                    if isinstance(content, list):
                        content = " ".join(
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                    if q in str(content).lower():
                        item = dict(session, match_type="content")
                        if isinstance(item.get("title"), str):
                            item["title"] = ctx._redact_text(item["title"])
                        results.append(item)
                        break
            except Exception:
                pass

    ctx._attach_projection_metadata_to_rows(results, parsed=parsed)
    return ctx.j(handler, {"sessions": results, "query": q, "count": len(results)})

