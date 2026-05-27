from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
SESSION_LIST_STATE_JS = (ROOT / "static" / "session-list-state.js").read_text(encoding="utf-8")


def test_default_hidden_session_recognizes_cron_rows():
    assert "function _isDefaultHiddenSession(session)" in SESSION_LIST_STATE_JS
    assert "source === 'cron'" in SESSION_LIST_STATE_JS
    assert "session.session_source === 'cron'" in SESSION_LIST_STATE_JS
    assert "sid.startsWith('cron_')" in SESSION_LIST_STATE_JS


def test_project_filter_keeps_cron_rows_when_project_selected():
    assert "const defaultVisible=profileFiltered.filter(s=>_activeProject||!_isDefaultHiddenSession(s));" in SESSIONS_JS
    assert ":(_activeProject?profileFiltered.filter(s=>s.project_id===_activeProject):defaultVisible)" in SESSIONS_JS
