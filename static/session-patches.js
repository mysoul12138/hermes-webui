// ── Session list patches (decoupled from upstream sessions.js) ──
// Bug 2: Unread notification dot persists after clicking into a session.
//   Root cause: _hasUnreadForSession() checks _hasSessionCompletionUnread()
//   FIRST — if the flag is set, it returns true immediately without comparing
//   viewed-count vs message-count.  _setSessionViewedCount() updates the count
//   but never clears the completion-unread flag.  So even after loadSession()
//   syncs the viewed count, a stale completion-unread flag keeps the dot lit.
//   Fix: wrap _setSessionViewedCount to also clear completion-unread for the
//   same session.  This is the correct coupling point — whenever the system
//   records "user has seen N messages", the completion-unread flag should be
//   cleared because the user has acknowledged those messages.
//
// Note: Bug 1 (Cron project re-fetch) was removed — upstream PR #3069
// implemented _include_project_hidden_background_sidebar_sessions + default_hidden
// which covers the same functionality.

(function () {
  'use strict';

  // ── Bug 2a: Wrap _setSessionViewedCount to clear completion-unread ──
  // _hasUnreadForSession checks completion-unread FIRST (short-circuits).
  // So updating the viewed count alone is not enough — the flag must go too.
  var _origSetViewed = window._setSessionViewedCount;
  if (typeof _origSetViewed === 'function') {
    window._setSessionViewedCount = function (sid, messageCount) {
      _origSetViewed.call(this, sid, messageCount);
      // When the system records "user has seen N messages", any prior
      // completion-unread flag is stale — the user has acknowledged.
      if (sid && typeof window._clearSessionCompletionUnread === 'function') {
        window._clearSessionCompletionUnread(sid);
      }
    };
  }

  // ── Bug 2b: Clear completion-unread for actively viewed sessions ──
  // Belt-and-suspenders: also clear during polling transitions in case
  // _setSessionViewedCount was bypassed or the flag was re-set between calls.
  var _origMarkPolling = window._markPollingCompletionUnreadTransitions;
  if (typeof _origMarkPolling === 'function') {
    window._markPollingCompletionUnreadTransitions = function (sessions) {
      _origMarkPolling.call(this, sessions);
      if (!Array.isArray(sessions)) return;
      for (var i = 0; i < sessions.length; i++) {
        var s = sessions[i];
        if (!s || !s.session_id) continue;
        if (
          typeof window._isSessionActivelyViewedForList === 'function' &&
          window._isSessionActivelyViewedForList(s.session_id) &&
          typeof window._clearSessionCompletionUnread === 'function'
        ) {
          window._clearSessionCompletionUnread(s.session_id);
        }
      }
    };
  }
})();
