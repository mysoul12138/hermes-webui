// ── Session list state & pure utilities ─────────────────────────────────────
// Extracted from sessions.js to separate persistent state and pure helpers
// from rendering/event-handling logic.  Loaded BEFORE sessions.js so all
// globals are available when sessions.js runs.
//

// ── Session source classification ──────────────────────────────────────────
const _MESSAGING_RAW_SOURCES = new Set(['weixin', 'telegram', 'discord', 'slack', 'email']);
const _MESSAGING_SOURCE_LABELS = {
  weixin: 'WeChat',
  telegram: 'Telegram',
  discord: 'Discord',
  slack: 'Slack',
  email: 'Email',
};

function _isMessagingSession(session) {
  if (!session) return false;
  // session_source is set by PR #1294 source normalization
  if (session.session_source === 'messaging') return true;
  // Fallback: check raw_source directly
  const raw = (session.raw_source || session.source_tag || session.source || '').toLowerCase();
  return _MESSAGING_RAW_SOURCES.has(raw);
}

function _isReadOnlySession(session) {
  return !!(session && (session.read_only || session.is_read_only));
}

function _sourceKeyForSession(session) {
  return (session && (session.raw_source || session.source_tag || session.source || '') || '').toLowerCase();
}

function _isCliSession(session) {
  if (!session) return false;
  // session_source is set by upstream normalization for CLI sessions as 'cli'
  if (session.session_source === 'cli') return true;
  // Legacy payloads often use raw/source tags to convey the source.
  const raw = (
    session.raw_source
    || session.source_tag
    || session.source
    || session.source_label
    || ''
  ).toLowerCase();
  if (raw === 'cli') return true;
  // If messaging-like, don't classify as legacy CLI even when is_cli_session is true.
  if (_isMessagingSession(session)) return false;
  return session.is_cli_session === true;
}

function _isDefaultHiddenSession(session) {
  if (!session) return false;
  const sid = String(session.session_id || '');
  const source = _sourceKeyForSession(session);
  return source === 'cron' || session.session_source === 'cron' || sid.startsWith('cron_');
}

function _normalizeMessageForCliImportComparison(message) {
  if (!message || typeof message !== 'object') return message;
  const clone = { ...message };
  delete clone.timestamp;
  delete clone._ts;
  return clone;
}

function _isCliImportRefreshPrefixMatch(localMessages, freshMessages) {
  if (!Array.isArray(localMessages) || !Array.isArray(freshMessages)) return false;
  if (localMessages.length > freshMessages.length) return false;
  for (let i = 0; i < localMessages.length; i += 1) {
    if (JSON.stringify(_normalizeMessageForCliImportComparison(localMessages[i])) !== JSON.stringify(_normalizeMessageForCliImportComparison(freshMessages[i]))) {
      return false;
    }
  }
  return true;
}

// ── Channel label ──────────────────────────────────────────────────────────
function _getChannelLabel(session) {
  if (!session) return '';
  // Use source_label from PR #1294 if available
  if (session.source_label) return session.source_label;
  const raw = (session.raw_source || session.source_tag || session.source || '').toLowerCase();
  return _MESSAGING_SOURCE_LABELS[raw] || raw || '';
}

// ── Session list state variables ───────────────────────────────────────────
let _allSessions = [];  // cached for search filter
let _renamingSid = null;  // session_id currently being renamed (blocks list re-renders)
let _showArchived = false;  // toggle to show archived sessions
let _sessionSelectMode = false;  // batch select mode
const _selectedSessions = new Set();  // selected session IDs
let _allProjects = [];  // cached project list
// Sentinel value for the _activeProject state when filtering to sessions
// that have no project_id assigned. Distinct from real project IDs so the
// equality check below can branch cleanly on it. The literal string is
// not user-visible (the chip renders the localized label) — it just has
// to be something a user-created project_id can never collide with, which
// double-underscore prefixes provide.
const NO_PROJECT_FILTER = '__none__';
let _activeProject = null;  // project_id filter (null = show all, NO_PROJECT_FILTER = unassigned only)
let _showAllProfiles = false;  // false = filter to active profile only
let _otherProfileCount = 0;       // count of sessions from other profiles (server-reported)
let _sessionActionMenu = null;
let _sessionActionAnchor = null;
let _sessionActionSessionId = null;
const _expandedChildSessionKeys = new Set();
const _expandedLineageKeys = new Set();
const _lineageReportCache = new Map();
const _lineageReportInflight = new Map();
let _lineageReportCacheGeneration = 0;
let _sessionVisibleSidebarIds = [];
const SESSION_VIRTUAL_ROW_HEIGHT = 52;
const SESSION_VIRTUAL_BUFFER_ROWS = 12;
const SESSION_VIRTUAL_THRESHOLD_ROWS = 80;
let _sessionVirtualScrollList = null;
let _sessionVirtualScrollRaf = 0;

// ── Pure session state accessors ───────────────────────────────────────────
function _sessionSnapshotById(sid){
  if(!sid)return null;
  if(S.session&&S.session.session_id===sid) return S.session;
  return (_allSessions||[]).find(s=>s&&s.session_id===sid)||null;
}
function _pinnedSessionCount(){
  return (_allSessions||[]).filter(s=>s&&s.pinned&&!s.archived).length;
}
function _getPinnedSessionsLimit(){
  const limit=parseInt(window._pinnedSessionsLimit||3,10);
  return (Number.isFinite(limit)&&limit>0)?limit:3;
}
function _pinnedSessionsLimitMessage(){
  const limit=_getPinnedSessionsLimit();
  return `Only ${limit} conversations can be pinned. Unpin one before pinning another.`;
}
function _worktreeSessionCount(ids){
  return (ids||[]).reduce((count,sid)=>{
    const session=_sessionSnapshotById(sid);
    return count+(session&&session.worktree_path?1:0);
  },0);
}
function _sessionResponseRetainsWorktree(response, session){
  if(response&&typeof response.worktree_retained==='boolean') return response.worktree_retained;
  return !!(session&&session.worktree_path);
}
function _worktreeResponseCount(results){
  return (results||[]).reduce((count,result)=>{
    return count+(_sessionResponseRetainsWorktree(result&&result.response,result&&result.session)?1:0);
  },0);
}
function _sessionArchiveDescription(session){
  return session&&session.worktree_path?t('session_archive_worktree_desc'):t('session_archive_desc');
}
function _sessionArchiveToast(response, session){
  return _sessionResponseRetainsWorktree(response,session)?t('session_archived_worktree'):t('session_archived');
}
function _sessionDeleteDescription(session){
  return session&&session.worktree_path?t('session_delete_worktree_desc'):t('session_delete_desc');
}
function _optimisticallyArchiveSessionInList(sid, archived){
  if(!sid||!Array.isArray(_allSessions)) return;
  let changed=false;
  _allSessions=_allSessions.map(s=>{
    if(!s||s.session_id!==sid) return s;
    changed=true;
    return {...s,archived:!!archived};
  });
  if(changed) renderSessionListFromCache();
}
function _optimisticallyRemoveSessionFromList(sid){
  if(!sid||!Array.isArray(_allSessions)) return;
  const before=_allSessions.length;
  _allSessions=_allSessions.filter(s=>!s||s.session_id!==sid);
  if(_selectedSessions&&_selectedSessions.has(sid)) _selectedSessions.delete(sid);
  if(typeof _dropStaleOptimisticSessionRow==='function') _dropStaleOptimisticSessionRow(sid);
  if(_allSessions.length!==before) renderSessionListFromCache();
}

function _sessionIdFromLocation(){
  if(typeof window==='undefined'||!window.location) return null;
  const marker='/session/';
  const path=window.location.pathname||'';
  const idx=path.indexOf(marker);
  if(idx>=0){
    const raw=path.slice(idx+marker.length).split('/')[0];
    if(raw){try{return decodeURIComponent(raw);}catch(_e){return raw;}}
  }
  try{
    const qs=new URLSearchParams(window.location.search||'');
    return qs.get('session')||qs.get('session_id')||null;
  }catch(_e){return null;}
}
function _sessionUrlForSid(sid){
  const encoded=encodeURIComponent(sid);
  let base;
  try{base=new URL(`session/${encoded}`, document.baseURI||window.location.origin+'/');}
  catch(_e){base=new URL(`/session/${encoded}`, window.location.origin);}
  try{
    const current=new URL(window.location.href);
    current.searchParams.delete('session');
    base.search=current.searchParams.toString();
    base.hash=current.hash;
  }catch(_e){}
  return base.pathname+base.search+base.hash;
}
function _setActiveSessionUrl(sid){
  if(typeof window==='undefined'||!window.history||!sid) return;
  const next=_sessionUrlForSid(sid);
  if(next && next!==(window.location.pathname+window.location.search+window.location.hash)){
    window.history.pushState({session_id:sid},'',next);
  }
}

// ── Render generation counter ──────────────────────────────────────────────
let _renderSessionListGen = 0;

// ── Server time state & time formatting utilities ──────────────────────────
let _serverTimeDelta = 0;       // ms offset: client clock - server clock (for clock-skew compensation)
let _serverTz = '';              // server timezone offset string (e.g. "+0800", "+0000", "-0500")

function filterSessions(){
  // Immediate client-side title filter (no flicker)
  renderSessionListFromCache();
  // Debounced content search via API for message text
  const q = ($('sessionSearch').value || '').trim();
  clearTimeout(_searchDebounceTimer);
  if (!q) { _contentSearchResults = []; return; }
  _searchDebounceTimer = setTimeout(async () => {
    try {
      const data = await api(`/api/sessions/search?q=${encodeURIComponent(q)}&content=1&depth=5`);
      const titleIds = new Set(_allSessions.filter(s => _sessionDisplayTitle(s).toLowerCase().includes(q.toLowerCase())).map(s=>s.session_id));
      _contentSearchResults = (data.sessions||[]).filter(s => s.match_type === 'content' && !titleIds.has(s.session_id));
      renderSessionListFromCache();
    } catch(e) { /* ignore */ }
  }, 350);
}

function _sessionTimestampMs(session) {
  const raw = Number(session && (session.last_message_at || session.updated_at || session.created_at || 0));
  return Number.isFinite(raw) ? raw * 1000 : 0;
}

function _serverNowMs() {
  // Compensate for clock skew between client and server (issue #1144).
  // Returns an approximation of the current server time in ms.
  return Date.now() - _serverTimeDelta;
}

function _serverTzOptions() {
  // Build a timeZone option from _serverTz (e.g. "+0800" → "Etc/GMT-8").
  // Falls back to undefined (uses browser timezone) when:
  //   - _serverTz is not set or is UTC (no offset to apply)
  //   - _serverTz is malformed
  //   - _serverTz has a fractional-hour component (India +0530, Iran +0330,
  //     Newfoundland -0330, Nepal +0545, etc.) — IANA Etc/GMT zones cannot
  //     express half/quarter-hour offsets; use _formatInServerTz() instead
  //     for correct fractional-offset formatting.
  if (!_serverTz || _serverTz === '+0000' || _serverTz === '-0000') return undefined;
  const m = _serverTz.match(/^([+-])(\d{2})(\d{2})$/);
  if (!m) return undefined;
  if (m[3] !== '00') return undefined;  // fractional offset — caller must use _formatInServerTz
  // IANA Etc/GMT uses inverted sign: UTC+8 → "Etc/GMT-8"
  const sign = m[1] === '+' ? '-' : '+';
  return { timeZone: `Etc/GMT${sign}${parseInt(m[2])}` };
}

function _formatInServerTz(date, options) {
  // Format `date` in the server's wall-clock timezone, including correct
  // handling of fractional-hour offsets that Etc/GMT cannot express.
  //
  // Strategy: shift the timestamp by the server's offset, then format with
  // timeZone:'UTC' so no further conversion is applied — the formatted
  // output reads as the wall-clock time in the server's timezone.
  //
  // Falls back to plain `date.toLocaleString(undefined, options)` (browser
  // timezone) when _serverTz is absent, UTC, or malformed.
  if (!_serverTz || _serverTz === '+0000' || _serverTz === '-0000') {
    return date.toLocaleString(undefined, options);
  }
  const m = _serverTz.match(/^([+-])(\d{2})(\d{2})$/);
  if (!m) return date.toLocaleString(undefined, options);
  const sign = m[1] === '+' ? 1 : -1;
  const offsetMin = sign * (parseInt(m[2]) * 60 + parseInt(m[3]));
  const adjusted = new Date(date.getTime() + offsetMin * 60 * 1000);
  return adjusted.toLocaleString(undefined, { ...options, timeZone: 'UTC' });
}

function _localDayOrdinal(timestampMs) {
  const date = new Date(timestampMs);
  return Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000);
}

function _sessionCalendarBoundaries(nowMs) {
  nowMs = nowMs || _serverNowMs();
  const now = new Date(nowMs);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  const startOfWeek = new Date(startOfToday);
  startOfWeek.setDate(startOfWeek.getDate() - ((startOfWeek.getDay() + 6) % 7));
  const startOfLastWeek = new Date(startOfWeek);
  startOfLastWeek.setDate(startOfLastWeek.getDate() - 7);
  return {
    startOfToday: startOfToday.getTime(),
    startOfYesterday: startOfYesterday.getTime(),
    startOfWeek: startOfWeek.getTime(),
    startOfLastWeek: startOfLastWeek.getTime(),
  };
}

function _formatSessionDate(timestampMs, nowMs) {
  nowMs = nowMs || _serverNowMs();
  const date = new Date(timestampMs);
  const now = new Date(nowMs);
  const options = {month:'short', day:'numeric'};
  if (date.getFullYear() !== now.getFullYear()) options.year = 'numeric';
  return date.toLocaleDateString(undefined, options);
}

function _formatRelativeSessionTime(timestampMs, nowMs) {
  if (!timestampMs) return t('session_time_unknown');
  nowMs = nowMs || _serverNowMs();
  const diffMs = Math.max(0, nowMs - timestampMs);
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const {startOfToday, startOfYesterday, startOfWeek, startOfLastWeek} = _sessionCalendarBoundaries(nowMs);
  const dayDiff = Math.max(0, _localDayOrdinal(nowMs) - _localDayOrdinal(timestampMs));
  if (timestampMs >= startOfToday) {
    if (diffMs < minute) return t('session_time_minutes_ago', 1);
    if (diffMs < hour) {
      const minutes = Math.floor(diffMs / minute);
      return t('session_time_minutes_ago', minutes);
    }
    const hours = Math.floor(diffMs / hour);
    return t('session_time_hours_ago', hours);
  }
  if (timestampMs >= startOfYesterday) return t('session_time_days_ago', 1);
  if (timestampMs >= startOfWeek) return t('session_time_days_ago', dayDiff);
  if (timestampMs >= startOfLastWeek) return t('session_time_last_week');
  return _formatSessionDate(timestampMs, nowMs);
}

function _sessionTimeBucketLabel(timestampMs, nowMs) {
  if (!timestampMs) return t('session_time_bucket_older');
  nowMs = nowMs || _serverNowMs();
  const {startOfToday, startOfYesterday, startOfWeek, startOfLastWeek} = _sessionCalendarBoundaries(nowMs);
  if (timestampMs >= startOfToday) return t('session_time_bucket_today');
  if (timestampMs >= startOfYesterday) return t('session_time_bucket_yesterday');
  if (timestampMs >= startOfWeek) return t('session_time_bucket_this_week');
  if (timestampMs >= startOfLastWeek) return t('session_time_bucket_last_week');
  return t('session_time_bucket_older');
}

// ── Session lineage helpers ────────────────────────────────────────────────
function _isChildSession(s){
  return !!(s&&s.parent_session_id&&s.relationship_type==='child_session');
}

function _sessionLineageKey(s, sessionIdsInList, sessionsById){
  if(!s||!s.session_id) return null;
  if(_isChildSession(s)) return null;
  if(s.session_source==='fork') return null;
  const lineageKey=s._lineage_root_id||s.lineage_root_id||null;
  if(lineageKey) return lineageKey;
  // WebUI-native context compression may only persist parent_session_id:
  // the preserved parent snapshot is marked pre_compression_snapshot while
  // the new continuation points at it.  When both rows are in the sidebar
  // payload, still collapse them into one conversation (#2489).
  const parent=s.parent_session_id&&sessionsById?sessionsById.get(s.parent_session_id):null;
  if(s.pre_compression_snapshot||parent&&parent.pre_compression_snapshot){
    let root=s;
    const seen=new Set();
    while(root&&root.parent_session_id&&sessionsById&&sessionsById.has(root.parent_session_id)&&!seen.has(root.parent_session_id)){
      const next=sessionsById.get(root.parent_session_id);
      if(!next||_isChildSession(next)||next.session_source==='fork'||!(root.pre_compression_snapshot||next.pre_compression_snapshot)) break;
      seen.add(root.session_id);
      root=next;
    }
    return root&&root.session_id||s.parent_session_id||s.session_id;
  }
  // If parent_session_id points to another session in the current list,
  // this is a subagent/fork child without compression metadata — don't
  // collapse it into lineage (#494).
  if(s.parent_session_id && sessionIdsInList && sessionIdsInList.has(s.parent_session_id)){
    return null;
  }
  return s.parent_session_id || null;
}

function _sessionLineageContainsSession(s, sid){
  if(!s||!sid) return false;
  if(s.session_id===sid) return true;
  if(Array.isArray(s._lineage_segments)&&s._lineage_segments.some(seg=>seg&&seg.session_id===sid)) return true;
  if(Array.isArray(s._child_sessions)&&s._child_sessions.some(child=>child&&child.session_id===sid)) return true;
  return false;
}

// ── Session display title utilities ────────────────────────────────────────
function _sessionDisplayTitle(s){
  const title=String((s&&(s.display_title||s._state_db_title||s.title))||'Untitled').trim();
  return title||'Untitled';
}

function _sessionTitleIsDefaultWebUI(rawTitle){
  const title=String(rawTitle||'').replace(/\s+/g,' ').trim();
  return title==='Hermes WebUI'||/^Hermes WebUI #\d+$/.test(title);
}

function _sessionTitleTags(rawTitle){
  if(_sessionTitleIsDefaultWebUI(rawTitle)) return [];
  return String(rawTitle||'').match(/#[\w-]+/g)||[];
}
