let _activeChannelPlatform = 'telegram';
let _channelConfigDrafts = null;
let _channelConfigAdapters = {};
let _channelConfigLoadedFromServer = false;
let _channelGatewayStatus = null;
let _channelGatewayStatusLoaded = false;
const CHANNEL_CONFIG_STORAGE_KEY = 'hermes-channel-config-drafts';
const CHANNEL_CONFIGURED_SECRET_MARKER = '••••••••';
const CHANNEL_ACTIONS = {
  weixinQrLogin: {
    labelKey: 'platform_qr_login',
    successKey: 'platform_qr_login_started',
    failureKey: 'platform_qr_login_failed',
    endpoint: '/api/hermes/weixin/qrcode',
  },
};
const CHANNEL_PLATFORMS = [
  {
    key: 'telegram',
    name: 'Telegram',
    icon: 'TG',
    descKey: 'channels_desc_telegram',
    fields: [
      {key: 'token', type: 'password', label: 'platform_bot_token', hint: 'platform_bot_token_hint', placeholder: '123456:ABC-DEF...', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_group'},
      {key: 'reactions', type: 'checkbox', label: 'platform_reactions', hint: 'platform_reactions_hint'},
      {key: 'free_response_chats', type: 'text', label: 'platform_free_response_chats', hint: 'platform_free_response_chats_hint', placeholder: 'chat_id1,chat_id2'},
      {key: 'mention_patterns', type: 'text', label: 'platform_mention_patterns', hint: 'platform_mention_patterns_hint', placeholder: 'pattern1, pattern2'},
    ],
  },
  {
    key: 'discord',
    name: 'Discord',
    icon: 'DC',
    descKey: 'channels_desc_discord',
    fields: [
      {key: 'token', type: 'password', label: 'platform_bot_token', hint: 'platform_bot_token_hint', placeholder: 'Bot token...', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_channel'},
      {key: 'auto_thread', type: 'checkbox', label: 'platform_auto_thread', hint: 'platform_auto_thread_hint'},
      {key: 'reactions', type: 'checkbox', label: 'platform_reactions', hint: 'platform_reactions_hint'},
      {key: 'free_response_channels', type: 'text', label: 'platform_free_response_channels', hint: 'platform_free_response_channels_hint', placeholder: 'channel_id1,channel_id2'},
      {key: 'allowed_channels', type: 'text', label: 'platform_allowed_channels', hint: 'platform_allowed_channels_hint', placeholder: 'channel_id1,channel_id2'},
      {key: 'ignored_channels', type: 'text', label: 'platform_ignored_channels', hint: 'platform_ignored_channels_hint', placeholder: 'channel_id1,channel_id2'},
      {key: 'no_thread_channels', type: 'text', label: 'platform_no_thread_channels', hint: 'platform_no_thread_channels_hint', placeholder: 'channel_id1,channel_id2'},
    ],
  },
  {
    key: 'slack',
    name: 'Slack',
    icon: 'SL',
    descKey: 'channels_desc_slack',
    fields: [
      {key: 'token', type: 'password', label: 'platform_bot_token', hint: 'platform_bot_token_hint', placeholder: 'xoxb-...', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_channel'},
      {key: 'allow_bots', type: 'checkbox', label: 'platform_allow_bots', hint: 'platform_allow_bots_hint'},
      {key: 'free_response_channels', type: 'text', label: 'platform_free_response_channels', hint: 'platform_free_response_channels_hint', placeholder: 'channel_id1,channel_id2'},
    ],
  },
  {
    key: 'whatsapp',
    name: 'WhatsApp',
    icon: 'WA',
    descKey: 'channels_desc_whatsapp',
    fields: [
      {key: 'enabled', type: 'checkbox', label: 'platform_wa_enabled', hint: 'platform_wa_enabled_hint', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_group'},
      {key: 'free_response_chats', type: 'text', label: 'platform_free_response_chats', hint: 'platform_free_response_chats_hint', placeholder: 'chat_id1,chat_id2'},
      {key: 'mention_patterns', type: 'text', label: 'platform_mention_patterns', hint: 'platform_mention_patterns_hint', placeholder: 'pattern1, pattern2'},
    ],
  },
  {
    key: 'matrix',
    name: 'Matrix',
    icon: 'MX',
    descKey: 'channels_desc_matrix',
    fields: [
      {key: 'token', type: 'password', label: 'platform_access_token', hint: 'platform_access_token_hint', placeholder: 'syt_...', credential: true},
      {key: 'homeserver', type: 'url', label: 'platform_homeserver', hint: 'platform_homeserver_hint', placeholder: 'https://matrix.org', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_room'},
      {key: 'auto_thread', type: 'checkbox', label: 'platform_auto_thread', hint: 'platform_auto_thread_hint_room'},
      {key: 'dm_mention_threads', type: 'checkbox', label: 'platform_dm_mention_threads', hint: 'platform_dm_mention_threads_hint'},
      {key: 'free_response_rooms', type: 'text', label: 'platform_free_response_rooms', hint: 'platform_free_response_rooms_hint', placeholder: 'room_id1,room_id2'},
    ],
  },
  {
    key: 'feishu',
    name: 'Feishu',
    icon: 'FS',
    descKey: 'channels_desc_feishu',
    fields: [
      {key: 'app_id', type: 'text', label: 'platform_app_id', hint: 'platform_app_id_hint', placeholder: 'cli_...', credential: true},
      {key: 'app_secret', type: 'password', label: 'platform_app_secret', hint: 'platform_app_secret_hint', placeholder: 'App Secret', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_group'},
      {key: 'free_response_chats', type: 'text', label: 'platform_free_response_chats', hint: 'platform_free_response_chats_hint', placeholder: 'chat_id1,chat_id2'},
    ],
  },
  {
    key: 'dingtalk',
    name: 'DingTalk',
    icon: 'DT',
    descKey: 'channels_desc_dingtalk',
    fields: [
      {key: 'client_id', type: 'text', label: 'platform_client_id', hint: 'platform_client_id_hint', placeholder: 'Client ID', credential: true},
      {key: 'client_secret', type: 'password', label: 'platform_client_secret', hint: 'platform_client_secret_hint', placeholder: 'Client Secret', credential: true},
      {key: 'allow_all_users', type: 'checkbox', label: 'platform_allow_all_users', hint: 'platform_allow_all_users_hint', credential: true},
      {key: 'allowed_users', type: 'text', label: 'platform_allowed_users', hint: 'platform_allowed_users_hint', placeholder: 'user_id1,user_id2', credential: true},
      {key: 'require_mention', type: 'checkbox', label: 'platform_require_mention', hint: 'platform_require_mention_group'},
      {key: 'free_response_chats', type: 'text', label: 'platform_free_response_chats', hint: 'platform_free_response_chats_hint', placeholder: 'chat_id1,chat_id2'},
    ],
  },
  {
    key: 'qqbot',
    name: 'QQBot',
    icon: 'QQ',
    descKey: 'channels_desc_qqbot',
    fields: [
      {key: 'app_id', type: 'text', label: 'platform_qq_app_id', hint: 'platform_qq_app_id_hint', placeholder: 'App ID', credential: true},
      {key: 'client_secret', type: 'password', label: 'platform_qq_app_secret', hint: 'platform_qq_app_secret_hint', placeholder: 'App Secret', credential: true},
      {key: 'allowed_users', type: 'text', label: 'platform_allowed_users', hint: 'platform_allowed_users_hint', placeholder: 'openid1,openid2', credential: true},
      {key: 'allow_all_users', type: 'checkbox', label: 'platform_allow_all_users', hint: 'platform_allow_all_users_hint', credential: true},
      {key: 'markdown_support', type: 'checkbox', label: 'platform_qq_markdown', hint: 'platform_qq_markdown_hint'},
    ],
  },
  {
    key: 'weixin',
    name: 'Weixin',
    icon: 'WX',
    descKey: 'channels_desc_weixin',
    fields: [
      {key: 'qr_login', type: 'action', action: 'weixinQrLogin', label: 'platform_qr_login', hint: 'platform_qr_login_static_hint'},
      {key: 'token', type: 'password', label: 'platform_weixin_token', hint: 'platform_weixin_token_hint', placeholder: 'Token', credential: true},
      {key: 'account_id', type: 'text', label: 'platform_account_id', hint: 'platform_account_id_hint', placeholder: 'Account ID', credential: true},
    ],
  },
  {
    key: 'wecom',
    name: 'WeCom',
    icon: 'WC',
    descKey: 'channels_desc_wecom',
    fields: [
      {key: 'bot_id', type: 'text', label: 'platform_bot_id', hint: 'platform_bot_id_hint', placeholder: 'Bot ID', credential: true},
      {key: 'secret', type: 'password', label: 'platform_app_secret', hint: 'platform_wecom_secret_hint', placeholder: 'Secret', credential: true},
    ],
  },
];

function _loadChannelConfigDrafts() {
  if (_channelConfigDrafts) return _channelConfigDrafts;
  try {
    const raw = localStorage.getItem(CHANNEL_CONFIG_STORAGE_KEY);
    _channelConfigDrafts = raw ? JSON.parse(raw) : {};
  } catch (_) {
    _channelConfigDrafts = {};
  }
  return _channelConfigDrafts;
}

function _saveChannelConfigDrafts() {
  try {
    localStorage.setItem(CHANNEL_CONFIG_STORAGE_KEY, JSON.stringify(_channelConfigDrafts || {}));
  } catch (_) {}
}

function _mergeChannelConfigDrafts(configs) {
  if (!configs || typeof configs !== 'object' || Array.isArray(configs)) return;
  const drafts = _loadChannelConfigDrafts();
  Object.keys(configs).forEach(key => {
    const values = configs[key];
    if (!values || typeof values !== 'object' || Array.isArray(values)) return;
    drafts[key] = Object.assign({}, values, drafts[key] || {});
  });
  _channelConfigDrafts = drafts;
  _saveChannelConfigDrafts();
}

function _mergeChannelConfigAdapters(configs) {
  if (!configs || typeof configs !== 'object' || Array.isArray(configs)) return;
  _channelConfigAdapters = Object.assign({}, _channelConfigAdapters || {}, configs);
  const drafts = _loadChannelConfigDrafts();
  Object.keys(configs).forEach(key => {
    const values = configs[key];
    if (!values || typeof values !== 'object' || Array.isArray(values)) return;
    const target = drafts[key] || {};
    Object.keys(values).forEach(fieldKey => {
      if (fieldKey === 'source' || fieldKey.endsWith('_configured')) return;
      const current = target[fieldKey];
      if (current === undefined || current === null || String(current).trim() === '') {
        target[fieldKey] = values[fieldKey];
      }
    });
    drafts[key] = target;
  });
  _channelConfigDrafts = drafts;
  _saveChannelConfigDrafts();
}

function _channelAdapterConfig(platformKey) {
  const values = _channelConfigAdapters && _channelConfigAdapters[platformKey];
  if (!values || typeof values !== 'object' || Array.isArray(values)) return null;
  return values;
}

function _ensureChannelConfigLoadedFromServer() {
  if (_channelConfigLoadedFromServer || typeof api !== 'function') return;
  _channelConfigLoadedFromServer = true;
  api('/api/settings').then(settings => {
    _mergeChannelConfigDrafts(settings && settings.channel_platform_configs);
    _mergeChannelConfigAdapters(settings && settings.channel_platform_config_adapters);
    renderChannelsPanel();
  }).catch(() => {});
}

function _ensureChannelGatewayStatusLoaded() {
  if (_channelGatewayStatusLoaded || typeof api !== 'function') return;
  _channelGatewayStatusLoaded = true;
  api('/api/gateway/status').then(status => {
    _channelGatewayStatus = status || null;
    renderChannelsPanel();
  }).catch(() => {});
}

function _channelPlatform(key) {
  return CHANNEL_PLATFORMS.find(p => p.key === key) || CHANNEL_PLATFORMS[0];
}

function _channelDraft(key) {
  const drafts = _loadChannelConfigDrafts();
  if (!drafts[key]) drafts[key] = {};
  return drafts[key];
}

function _channelHasGatewayPlatform(platformKey) {
  if (!_channelGatewayStatus) return false;
  const platforms = Array.isArray(_channelGatewayStatus.platforms) ? _channelGatewayStatus.platforms : [];
  return platforms.some(p => {
    const name = String((p && (p.name || p.platform || p.key)) || '').toLowerCase();
    if (name !== platformKey) return false;
    if (p && Object.prototype.hasOwnProperty.call(p, 'configured')) return p.configured !== false;
    if (p && Object.prototype.hasOwnProperty.call(p, 'enabled')) return p.enabled !== false;
    return true;
  });
}

function _channelIsConfigured(platform) {
  if (!platform) return false;
  if (_channelHasGatewayPlatform(platform.key)) return true;
  if (_channelHasPersistedConfig(platform)) return true;
  const draft = _channelDraft(platform.key);
  return platform.fields.some(field => {
    if (!field.credential) return false;
    const value = draft[field.key];
    return field.type === 'checkbox' ? value === true : !!String(value || '').trim();
  });
}

function _channelHasPersistedConfig(platform) {
  if (!platform) return false;
  if (_channelHasGatewayPlatform(platform.key)) return true;
  const values = _channelAdapterConfig(platform.key);
  if (!values) return false;
  return platform.fields.some(field => {
    if (!field.credential) return false;
    if (values[field.key + '_configured'] === true) return true;
    const value = values[field.key];
    return field.type === 'checkbox' ? value === true : !!String(value || '').trim();
  });
}

function _channelStatusClass(configured) {
  return `channel-status ${configured ? 'channel-status-configured' : 'channel-status-not-configured'}`;
}

function _renderChannelDetailStatus(platform) {
  const badge = $('channelConfigStatusBadge') || document.querySelector('#channelConfigCard .channel-storage-badge');
  const note = $('channelStorageNote') || document.querySelector('#channelConfigCard .channel-storage-note');
  const configured = _channelIsConfigured(platform);
  if (badge) {
    badge.className = `channel-storage-badge ${_channelStatusClass(configured)}`;
    badge.textContent = t(configured ? 'channels_status_configured' : 'channels_status_not_configured');
  }
  if (note) {
    const hasSaveSupport = _channelHasPersistedConfig(platform) || platform.key === 'weixin';
    note.textContent = t(hasSaveSupport ? 'channels_storage_note' : 'channels_storage_pending_note');
  }
}

function _renderChannelPlatformPicker() {
  const picker = $('channelPlatformPicker');
  if (!picker) return;
  picker.innerHTML = CHANNEL_PLATFORMS.map(platform => {
    const active = platform.key === _activeChannelPlatform;
    const configured = _channelIsConfigured(platform);
    return `<button type="button" class="channel-platform-option${active ? ' active' : ''}" data-channel-key="${esc(platform.key)}" onclick="selectChannelPlatform('${esc(platform.key)}')">
      <span class="channel-platform-icon">${esc(platform.icon)}</span>
      <span class="channel-platform-option-name">${esc(platform.name)}</span>
      <span class="${_channelStatusClass(configured)}">${esc(t(configured ? 'channels_status_configured' : 'channels_status_not_configured'))}</span>
    </button>`;
  }).join('');
}

function _channelFieldHtml(platform, field, value) {
  const id = `channel-${platform.key}-${field.key}`;
  const hint = field.hint ? `<p class="setting-hint">${esc(t(field.hint))}</p>` : '';
  let control = '';
  if (field.type === 'checkbox') {
    control = `<label class="channel-switch"><input id="${esc(id)}" data-channel-field="${esc(field.key)}" type="checkbox" ${value === true ? 'checked' : ''}><span>${esc(t('channels_toggle_label'))}</span></label>`;
  } else if (field.type === 'action') {
    const action = CHANNEL_ACTIONS[field.action] || {};
    control = `<button type="button" id="${esc(id)}" class="settings-action-btn channel-action-btn" onclick="runChannelAction('${esc(field.action || '')}')">${esc(t(action.labelKey || field.label))}</button><div id="${esc(id)}-result" class="channel-action-result" aria-live="polite"></div>`;
  } else if (field.type === 'readonly') {
    control = `<div class="channel-readonly-value">${esc(t(field.valueKey) || value || '')}</div>`;
  } else {
    const type = field.type === 'password' ? 'password' : (field.type === 'url' ? 'url' : 'text');
    control = `<input id="${esc(id)}" data-channel-field="${esc(field.key)}" class="channel-config-input" type="${type}" value="${esc(value || '')}" placeholder="${esc(field.placeholder || '')}" autocomplete="off">`;
  }
  return `<div class="channel-setting-row">
    <div class="setting-info"><label class="setting-label" for="${esc(id)}">${esc(t(field.label))}</label>${hint}</div>
    <div class="setting-control">${control}</div>
  </div>`;
}

function renderChannelsPanel() {
  if (!$('channelPlatformPicker') || !$('channelConfigFields')) return;
  _ensureChannelConfigLoadedFromServer();
  _ensureChannelGatewayStatusLoaded();
  const platform = _channelPlatform(_activeChannelPlatform);
  _activeChannelPlatform = platform.key;
  _renderChannelPlatformPicker();
  const title = $('channelConfigTitle');
  const desc = $('channelConfigDescription');
  const fields = $('channelConfigFields');
  if (title) title.textContent = platform.name;
  if (desc) desc.textContent = t(platform.descKey);
  _renderChannelDetailStatus(platform);
  fields.innerHTML = platform.fields.map(field => _channelFieldHtml(platform, field, _channelDraft(platform.key)[field.key])).join('');
}

function selectChannelPlatform(key) {
  _activeChannelPlatform = _channelPlatform(key).key;
  renderChannelsPanel();
}

function _channelFormValues(platform) {
  const values = {};
  for (const field of platform.fields) {
    if (field.type === 'readonly' || field.type === 'action') continue;
    const el = document.querySelector(`[data-channel-field="${field.key}"]`);
    if (!el) continue;
    if (field.type === 'checkbox') {
      values[field.key] = !!el.checked;
      continue;
    }
    values[field.key] = el.value;
  }
  return values;
}

function _channelConfigsForSave(configs) {
  const cleaned = {};
  Object.keys(configs || {}).forEach(platformKey => {
    const values = configs[platformKey];
    if (!values || typeof values !== 'object' || Array.isArray(values)) return;
    cleaned[platformKey] = {};
    Object.keys(values).forEach(fieldKey => {
      if (values[fieldKey] === CHANNEL_CONFIGURED_SECRET_MARKER) return;
      cleaned[platformKey][fieldKey] = values[fieldKey];
    });
  });
  return cleaned;
}

async function runChannelAction(actionKey) {
  const action = CHANNEL_ACTIONS[actionKey];
  if (!action) return;
  try {
    const payload = action.endpoint ? await api(action.endpoint) : null;
    if (actionKey === 'weixinQrLogin') _renderWeixinQrLoginResult(payload);
    if (typeof showToast === 'function') showToast(t(action.successKey));
  } catch (e) {
    if (typeof showToast === 'function') showToast(t(action.failureKey) + (e && e.message ? e.message : ''));
  }
}

function _qrImageSrc(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  if (/^data:image\//i.test(text) || /^blob:/i.test(text)) return text;
  if (/^https?:\/\/.+\.(png|jpe?g|gif|webp|svg)(\?.*)?$/i.test(text)) return text;
  if (text.length > 80 && /^[A-Za-z0-9+/=\r\n]+$/.test(text)) return `data:image/png;base64,${text.replace(/\s+/g, '')}`;
  return '';
}

function _renderWeixinQrLoginResult(payload) {
  const result = $('channel-weixin-qr_login-result');
  if (!result) return;
  const data = payload && typeof payload === 'object' ? payload : {};
  const imageValue = data.image || data.qrcode_url || data.url || data.qrcode || '';
  const imageSrc = _qrImageSrc(imageValue);
  const qrcodeText = String(data.qrcode || data.url || data.qrcode_url || '').trim();
  if (imageSrc) {
    const copyText = qrcodeText && qrcodeText !== imageSrc
      ? `<div style="margin-top:8px"><code style="font-size:12px;word-break:break-all">${esc(qrcodeText)}</code></div>`
      : '';
    result.innerHTML = `<div style="margin-top:10px;display:grid;gap:8px;justify-items:start"><img alt="${esc(t('platform_qr_login_image_alt'))}" src="${esc(imageSrc)}" style="max-width:220px;border:1px solid var(--border2);border-radius:12px;background:#fff;padding:8px">${copyText}</div>`;
    return;
  }
  if (qrcodeText) {
    result.innerHTML = `<div style="margin-top:10px;display:grid;gap:8px"><div class="detail-form-hint">${esc(t('platform_qr_login_text_hint'))}</div><code style="display:block;white-space:pre-wrap;word-break:break-all;padding:10px;border:1px solid var(--border2);border-radius:10px;background:var(--code-bg)">${esc(qrcodeText)}</code><button type="button" class="settings-action-btn" data-copy-text="${esc(qrcodeText)}" onclick="navigator.clipboard && navigator.clipboard.writeText(this.dataset.copyText || '')">${esc(t('platform_qr_login_copy'))}</button></div>`;
    return;
  }
  result.innerHTML = `<div class="detail-form-hint" style="margin-top:10px">${esc(t('platform_qr_login_no_qr'))}</div>`;
}

async function saveChannelConfig(event) {
  if (event && event.preventDefault) event.preventDefault();
  const platform = _channelPlatform(_activeChannelPlatform);
  _channelConfigDrafts = _loadChannelConfigDrafts();
  _channelConfigDrafts[platform.key] = _channelFormValues(platform);
  _saveChannelConfigDrafts();
  try {
    await api('/api/settings', {
      method: 'POST',
      body: JSON.stringify({channel_platform_configs: _channelConfigsForSave(_channelConfigDrafts)}),
    });
  } catch (_) {
    // The current static worker intentionally does not change backend config semantics.
  }
  renderChannelsPanel();
  if (typeof showToast === 'function') showToast(t('channels_draft_saved'));
}

function resetChannelConfigDraft() {
  const platform = _channelPlatform(_activeChannelPlatform);
  _channelConfigDrafts = _loadChannelConfigDrafts();
  delete _channelConfigDrafts[platform.key];
  _saveChannelConfigDrafts();
  renderChannelsPanel();
  if (typeof showToast === 'function') showToast(t('channels_draft_reset'));
}

if (window.HermesPanelRegistry) {
  window.HermesPanelRegistry.registerPanel('channels', {
    onOpen: () => renderChannelsPanel(),
  });
}

