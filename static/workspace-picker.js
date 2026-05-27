// ── Workspace folder picker (decoupled from upstream panels.js) ──
// Adds a "Browse" button next to workspace path inputs that opens the
// native folder picker dialog, then searches the server filesystem for
// matching directories.
//
// Usage: call addBrowseButton(inputElement, onSelect) after rendering
// the path input.  If the browser doesn't support showDirectoryPicker,
// the button is hidden automatically.

(function () {
  'use strict';

  // ── Helpers ──

  function _t(key, fallback) {
    return (typeof t === 'function' ? t(key) : null) || fallback;
  }

  function _esc(s) {
    if (typeof esc === 'function') return esc(s);
    var d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function _api(path) {
    if (typeof api === 'function') return api(path);
    var rel = path.startsWith('/') ? path.slice(1) : path;
    var url = new URL(rel, document.baseURI || location.href);
    return fetch(url.href, { credentials: 'include' }).then(function (r) {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
  }

  // ── Feature detection ──

  function _supportsFolderPicker() {
    return typeof window.showDirectoryPicker === 'function';
  }

  // ── Native folder picker ──

  async function _openFolderPicker() {
    if (_supportsFolderPicker()) {
      try {
        var handle = await window.showDirectoryPicker({ mode: 'read' });
        return { name: handle.name, handle: handle };
      } catch (e) {
        // User cancelled the dialog
        if (e.name === 'AbortError') return null;
        throw e;
      }
    }
    // Firefox / Safari fallback: hidden <input> with webkitdirectory
    return new Promise(function (resolve) {
      var input = document.createElement('input');
      input.type = 'file';
      input.webkitdirectory = true;
      input.style.display = 'none';
      document.body.appendChild(input);
      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        document.body.removeChild(input);
        if (!file) return resolve(null);
        var parts = (file.webkitRelativePath || '').split('/');
        resolve({ name: parts[0] || '', handle: null });
      });
      input.addEventListener('cancel', function () {
        document.body.removeChild(input);
        resolve(null);
      });
      input.click();
    });
  }

  // ── Server-side folder locate ──

  async function _locateFolderOnServer(name) {
    var qs = new URLSearchParams({ name: name }).toString();
    var data = await _api('/api/workspaces/locate?' + qs);
    return (data && data.matches) || [];
  }

  // ── WSL path suggestion ──

  function _suggestWSLPath(windowsPath) {
    // E:\foo\bar → /mnt/e/foo/bar
    var match = (windowsPath || '').match(/^([A-Za-z]):[\\\/](.*)$/);
    if (!match) return null;
    var drive = match[1].toLowerCase();
    var rest = match[2].replace(/[\\]/g, '/').toLowerCase();
    return '/mnt/' + drive + '/' + rest;
  }

  // ── Render locate results ──

  function _renderLocateResults(matches, inputEl, onSelect) {
    // Find or create the results container
    var container = inputEl.parentNode.querySelector('.ws-locate-results');
    if (!container) {
      container = document.createElement('div');
      container.className = 'ws-locate-results';
      inputEl.parentNode.appendChild(container);
    }
    container.innerHTML = '';

    if (!matches || !matches.length) {
      var hint = document.createElement('div');
      hint.className = 'ws-locate-hint';
      hint.textContent = _t('workspace_locate_no_match', 'No matching folders found. Type the path manually.');
      container.appendChild(hint);
      container.style.display = 'block';
      return;
    }

    var label = document.createElement('div');
    label.className = 'ws-locate-label';
    label.textContent = _t('workspace_locate_select', 'Select a folder:');
    container.appendChild(label);

    matches.forEach(function (m) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ws-locate-item';
      btn.innerHTML =
        '<span class="ws-locate-name">' + _esc(m.label) + '</span>' +
        '<span class="ws-locate-path">' + _esc(m.path) + '</span>';
      btn.addEventListener('click', function () {
        // Fill the input with the selected path
        var path = m.path;
        if (inputEl) {
          inputEl.value = path;
          inputEl.focus();
        }
        container.style.display = 'none';
        if (typeof onSelect === 'function') onSelect(path);
      });
      container.appendChild(btn);
    });

    container.style.display = 'block';
  }

  // ── Add Browse button ──

  function addBrowseButton(inputEl, onSelect) {
    if (!_supportsFolderPicker() && !_supportsFileInputFallback()) {
      return; // No way to pick folders — don't add the button
    }

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ws-browse-btn';
    btn.textContent = _t('workspace_browse', 'Browse…');
    btn.title = _t('workspace_browse_title', 'Pick a folder from your file system');

    btn.addEventListener('click', async function (e) {
      e.preventDefault();
      e.stopPropagation();
      btn.disabled = true;
      btn.textContent = '…';
      try {
        var result = await _openFolderPicker();
        if (!result || !result.name) {
          btn.textContent = _t('workspace_browse', 'Browse…');
          btn.disabled = false;
          return;
        }

        // Search server for matching directories
        btn.textContent = '⟳';
        var matches = await _locateFolderOnServer(result.name);

        if (matches.length === 1) {
          // Single match — fill directly
          if (inputEl) {
            inputEl.value = matches[0].path;
            inputEl.focus();
          }
          if (typeof onSelect === 'function') onSelect(matches[0].path);
        } else if (matches.length > 1) {
          // Multiple matches — show picker
          _renderLocateResults(matches, inputEl, onSelect);
        } else {
          // No match — show hint, put folder name in input for reference
          _renderLocateResults([], inputEl, onSelect);
          if (inputEl && !inputEl.value) {
            inputEl.value = result.name;
            inputEl.focus();
          }
        }
      } catch (err) {
        if (typeof showToast === 'function') {
          showToast(_t('workspace_browse_error', 'Could not browse folders: ') + (err.message || err), 3000, 'error');
        }
      } finally {
        btn.textContent = _t('workspace_browse', 'Browse…');
        btn.disabled = false;
      }
    });

    // Insert the button after the input
    if (inputEl && inputEl.parentNode) {
      // If the input is inside a wrap div, append to the wrap
      var wrap = inputEl.closest('.workspace-form-path-wrap') || inputEl.parentNode;
      wrap.appendChild(btn);
    }

    return btn;
  }

  function _supportsFileInputFallback() {
    // <input webkitdirectory> works in most modern browsers
    var tmp = document.createElement('input');
    tmp.type = 'file';
    return 'webkitdirectory' in tmp;
  }

  // ── CSS ──
  var _styleId = 'ws-picker-style';
  function _ensureStyle() {
    if (document.getElementById(_styleId)) return;
    var style = document.createElement('style');
    style.id = _styleId;
    style.textContent = [
      '.ws-browse-btn{',
      '  display:inline-flex;align-items:center;',
      '  padding:4px 10px;margin-left:6px;',
      '  font-size:12px;border-radius:6px;',
      '  border:1px solid var(--border,#444);',
      '  background:var(--surface,#2a2a2a);',
      '  color:var(--text,#ccc);cursor:pointer;',
      '  white-space:nowrap;flex-shrink:0;',
      '  transition:background .15s,border-color .15s;',
      '}',
      '.ws-browse-btn:hover{background:var(--surface-hover,#333);border-color:var(--accent,#666);}',
      '.ws-browse-btn:disabled{opacity:.5;cursor:default;}',
      '.ws-locate-results{',
      '  margin-top:8px;padding:8px;',
      '  border:1px solid var(--border,#444);border-radius:8px;',
      '  background:var(--surface,#2a2a2a);',
      '  max-height:200px;overflow-y:auto;',
      '}',
      '.ws-locate-label{font-size:11px;color:var(--text-muted,#888);margin-bottom:6px;}',
      '.ws-locate-hint{font-size:12px;color:var(--text-muted,#888);padding:4px 0;}',
      '.ws-locate-item{',
      '  display:flex;flex-direction:column;gap:2px;',
      '  width:100%;padding:6px 8px;margin-bottom:2px;',
      '  border:none;border-radius:6px;',
      '  background:transparent;cursor:pointer;text-align:left;',
      '  transition:background .1s;',
      '}',
      '.ws-locate-item:hover{background:var(--surface-hover,#333);}',
      '.ws-locate-name{font-size:13px;font-weight:500;color:var(--text,#ccc);}',
      '.ws-locate-path{font-size:11px;color:var(--text-muted,#888);word-break:break-all;}',
    ].join('\n');
    document.head.appendChild(style);
  }

  // Ensure styles are added when the script loads
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _ensureStyle);
  } else {
    _ensureStyle();
  }

  // ── Exports ──
  window.addBrowseButton = addBrowseButton;
  window._supportsFolderPicker = _supportsFolderPicker;
  window._suggestWSLPath = _suggestWSLPath;
  window._locateFolderOnServer = _locateFolderOnServer;
})();
