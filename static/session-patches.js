// ── Session list patches (decoupled from upstream sessions.js) ──
// Bug 1: Cron sessions not appearing when "Cron Jobs" project chip is selected.
//   Root cause: project chip click calls renderSessionListFromCache() which only
//   re-renders cached data. The initial page load fetches /api/sessions WITHOUT
//   include_cron=1, so cron sessions are filtered server-side and never reach
//   _allSessions. Selecting the cron project needs a full re-fetch.
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

(function () {
  'use strict';

  // ── Bug 1: Cron project selection needs server re-fetch ──
  var _origRenderFromCache = window.renderSessionListFromCache;
  if (typeof _origRenderFromCache === 'function') {
    var _cronFetchDone = false;
    window.renderSessionListFromCache = function () {
      // Run original render first so the sidebar is up-to-date.
      _origRenderFromCache.apply(this, arguments);

      // After rendering, check if the "Cron Jobs" chip is the active project.
      var chips = document.querySelectorAll('.project-chip.active');
      for (var i = 0; i < chips.length; i++) {
        if ((chips[i].textContent || '').indexOf('Cron') !== -1) {
          if (!_cronFetchDone && typeof window.renderSessionList === 'function') {
            _cronFetchDone = true;
            window.renderSessionList();
          }
          return;
        }
      }
      // Reset when project is cleared or changed away from cron.
      _cronFetchDone = false;
    };
  }

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
