const PROVIDER_MODAL_I18N = {
  addTitle: 'provider_modal_add_title',
  editTitle: 'provider_modal_edit_title',
};
const _providerCardEls = new Map(); // providerId -> {card, input, saveBtn, hasKey}
const _providerStateById = new Map();
const _providerExpandedIds = new Set();
const PROVIDER_MODEL_DATALIST_ID = 'providerConfigModelOptions';

function _providerModelRefreshIcon(){
  return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>';
}

function _deriveProviderNameFromBaseUrl(baseUrl){
  const raw=String(baseUrl||'').trim();
  if(!raw) return '';
  try{
    const parsed=new URL(raw, window.location.origin);
    const host=String(parsed.hostname||'').replace(/^www\./,'');
    const pathParts=String(parsed.pathname||'').split('/').filter(Boolean);
    const hostStem=host.split('.').filter(Boolean).join(' ');
    const pathStem=pathParts.length?pathParts[pathParts.length-1].replace(/[-_]+/g,' '):'';
    const name=(pathStem||hostStem||raw).replace(/\b(api|v\d+|openai|chat|model|models|llm|server)\b/gi,' ').replace(/[\W_]+/g,' ').replace(/\s+/g,' ').trim();
    return name ? name.replace(/\b\w/g, ch => ch.toUpperCase()) : raw;
  }catch(_e){
    return raw.replace(/^https?:\/\//i,'').replace(/\/+$/,'').split('/')[0].replace(/^www\./,'') || raw;
  }
}

function _syncProviderNameFromBaseUrl(){
  const nameInput=$('providerConfigName');
  const baseUrlInput=$('providerConfigBaseUrl');
  if(!nameInput||!baseUrlInput) return;
  const current=String(nameInput.value||'').trim();
  if(current) return;
  const derived=_deriveProviderNameFromBaseUrl(baseUrlInput.value);
  if(derived) nameInput.value=derived;
}

function _ensureProviderRefreshButton(provider){
  const saveBtn=$('providerConfigSaveBtn');
  const actions=saveBtn?saveBtn.closest('.app-dialog-actions'):null;
  if(!actions) return;
  let refreshBtn=$('providerConfigRefreshModelsBtn');
  if(!refreshBtn){
    refreshBtn=document.createElement('button');
    refreshBtn.id='providerConfigRefreshModelsBtn';
    refreshBtn.type='button';
    refreshBtn.className='app-dialog-btn provider-config-refresh-models';
    refreshBtn.style.marginRight='auto';
    refreshBtn.style.display='inline-flex';
    refreshBtn.style.alignItems='center';
    refreshBtn.style.gap='6px';
    actions.insertBefore(refreshBtn, actions.firstChild);
  }
  refreshBtn.hidden=false;
  refreshBtn.innerHTML=_providerModelRefreshIcon()+' '+esc(t('providers_refresh_models'));
  refreshBtn.onclick=()=>_refreshProviderModels(provider||{id:''}, refreshBtn);
}

function _ensureProviderModalBindings(){
  const nameInput=$('providerConfigName');
  const baseUrlInput=$('providerConfigBaseUrl');
  if(baseUrlInput&&!baseUrlInput.dataset.providerAutoNameBound){
    baseUrlInput.dataset.providerAutoNameBound='1';
    baseUrlInput.addEventListener('input',_syncProviderNameFromBaseUrl);
    baseUrlInput.addEventListener('change',_syncProviderNameFromBaseUrl);
  }
  if(nameInput&&!nameInput.dataset.providerAutoNameBound){
    nameInput.dataset.providerAutoNameBound='1';
    nameInput.addEventListener('input',()=>{ if(String(nameInput.value||'').trim()) nameInput.dataset.providerAutoNamed='0'; });
  }
}

function _normalizeProviderModels(models){
  if(!Array.isArray(models)) return [];
  const seen=new Set();
  const normalized=[];
  const firstText=(...values)=>{
    for(const value of values){
      const text=String(value||'').trim();
      if(text) return text;
    }
    return '';
  };
  for(const model of models){
    const id=model&&typeof model==='object'
      ? firstText(model.id, model.model, model.name, model.label, model.title)
      : firstText(model);
    const key=id.toLowerCase();
    if(!id||seen.has(key)) continue;
    seen.add(key);
    const label=model&&typeof model==='object'
      ? firstText(model.label, model.title, model.name, model.id, model.model)
      : id;
    normalized.push({
      id,
      label:label||id,
    });
  }
  return normalized;
}

function _ensureProviderModelDatalist(){
  const input=$('providerConfigModel');
  if(!input) return null;
  let datalist=$(PROVIDER_MODEL_DATALIST_ID);
  if(!datalist){
    datalist=document.createElement('datalist');
    datalist.id=PROVIDER_MODEL_DATALIST_ID;
    input.insertAdjacentElement('afterend', datalist);
  }
  input.setAttribute('list', PROVIDER_MODEL_DATALIST_ID);
  return datalist;
}

function _setProviderModelOptions(models){
  const datalist=_ensureProviderModelDatalist();
  if(!datalist) return;
  datalist.innerHTML='';
  for(const model of _normalizeProviderModels(models)){
    const option=document.createElement('option');
    option.value=model.id;
    if(model.label&&model.label!==model.id) option.label=model.label;
    datalist.appendChild(option);
  }
}

function _getProviderModelOptions(){
  const datalist=$(PROVIDER_MODEL_DATALIST_ID);
  if(!datalist) return [];
  return _normalizeProviderModels(Array.from(datalist.options||[]).map(option=>option.value));
}

function _setProviderModalStatus(message='', kind=''){
  const status=$('providerConfigError');
  if(!status) return;
  status.textContent=message||'';
  status.dataset.status=kind||'';
}

function _providerModalPayload(){
  const body={
    provider:$('providerConfigOriginalId')?$('providerConfigOriginalId').value:'',
    name:$('providerConfigName')?$('providerConfigName').value.trim():'',
    base_url:$('providerConfigBaseUrl')?$('providerConfigBaseUrl').value.trim():'',
    api_key:$('providerConfigApiKey')?$('providerConfigApiKey').value.trim():'',
    default_model:$('providerConfigModel')?$('providerConfigModel').value.trim():'',
    context_length:$('providerConfigContext')?$('providerConfigContext').value.trim():'',
  };
  const models=_getProviderModelOptions().map(model=>model.id);
  if(models.length) body.models=models;
  return body;
}

function _providerSelectorValue(value){
  const raw=String(value||'');
  if(window.CSS&&typeof window.CSS.escape==='function') return window.CSS.escape(raw);
  return raw.replace(/\\/g,'\\\\').replace(/"/g,'\\"');
}

function _syncProviderKeyToggle(input, button){
  if(!input||!button) return;
  const hasValue=!!String(input.value||'').trim();
  if(!hasValue){
    input.type='password';
    button.textContent=t(input.dataset.savedKeyHidden==='1'?'providers_saved_key_hidden':'providers_show_key');
    button.disabled=true;
    button.setAttribute('aria-disabled','true');
    button.setAttribute('aria-pressed','false');
    button.title=input.dataset.savedKeyHidden==='1'?t('providers_saved_key_hidden_hint'):'';
    return;
  }
  button.disabled=false;
  button.removeAttribute('aria-disabled');
  button.title='';
  const revealed=input.type==='text';
  button.textContent=t(revealed?'providers_hide_key':'providers_show_key');
  button.setAttribute('aria-pressed', String(revealed));
}

function _toggleProviderKeyInput(input, button){
  if(!input||!button) return;
  const hasValue=!!String(input.value||'').trim();
  if(!hasValue){
    _setProviderModalStatus(t('provider_modal_saved_key_hidden_hint'), 'warning');
    input.type='password';
    _syncProviderKeyToggle(input, button);
    return;
  }
  input.type=input.type==='text'?'password':'text';
  if(hasValue) _setProviderModalStatus();
  _syncProviderKeyToggle(input, button);
}

function _ensureProviderConfigApiKeyToggle(){
  const input=$('providerConfigApiKey');
  if(!input) return;
  let toggleBtn=$('providerConfigApiKeyToggle');
  if(!toggleBtn){
    const field=input.closest('.provider-config-field');
    const row=document.createElement('div');
    row.className='provider-card-row provider-config-api-key-row';
    input.parentNode.insertBefore(row, input);
    row.appendChild(input);
    toggleBtn=document.createElement('button');
    toggleBtn.id='providerConfigApiKeyToggle';
    toggleBtn.type='button';
    toggleBtn.className='provider-card-btn provider-card-btn-ghost';
    row.appendChild(toggleBtn);
    if(field) field.classList.add('provider-config-api-key-field');
  }
  input.type='password';
  input.addEventListener('input',()=>_syncProviderKeyToggle(input, toggleBtn));
  toggleBtn.onclick=()=>_toggleProviderKeyInput(input, toggleBtn);
  _syncProviderKeyToggle(input, toggleBtn);
}

function openProviderConfigModal(provider){
  const overlay=$('providerConfigOverlay');
  if(!overlay) return;
  const editing=provider&&provider.id;
  if(editing&&_providerStateById.has(provider.id)){
    provider=Object.assign({},provider,_providerStateById.get(provider.id));
  }
  const title=$('providerConfigTitle');
  if(title){
    const titleKey = editing ? PROVIDER_MODAL_I18N.editTitle : PROVIDER_MODAL_I18N.addTitle;
    title.textContent=t(titleKey);
    title.setAttribute('data-i18n', titleKey);
  }
  _ensureProviderModalBindings();
  $('providerConfigOriginalId').value=editing?provider.id:'';
  $('providerConfigName').value=editing?(provider.name||provider.display_name||''):'';
  $('providerConfigBaseUrl').value=editing?(provider.base_url||''):'';
  $('providerConfigApiKey').value='';
  const apiKey=$('providerConfigApiKey');
  if(apiKey){
    apiKey.dataset.savedKeyHidden=editing&&provider.has_key?'1':'0';
    const placeholderKey=editing&&provider.has_key?'provider_modal_api_key_placeholder_saved':'provider_modal_api_key_placeholder_new';
    apiKey.placeholder=t(placeholderKey);
    apiKey.setAttribute('data-i18n-placeholder', placeholderKey);
  }
  $('providerConfigModel').value=editing?(provider.default_model||''):'';
  _setProviderModelOptions(editing?(provider.models||[]):[]);
  $('providerConfigContext').value=editing&&provider.context_length?String(provider.context_length):'';
  _syncProviderNameFromBaseUrl();
  _setProviderModalStatus();
  _ensureProviderConfigApiKeyToggle();
  _ensureProviderRefreshButton(provider);
  overlay.style.display='flex';
  overlay.setAttribute('aria-hidden','false');
  setTimeout(()=>{
    try{
      _ensureProviderRefreshButton(provider);
      $('providerConfigName').focus();
    }catch(_e){}
  },0);
}

function closeProviderConfigModal(){
  const overlay=$('providerConfigOverlay');
  if(!overlay) return;
  overlay.style.display='none';
  overlay.setAttribute('aria-hidden','true');
}
window.openProviderConfigModal=openProviderConfigModal;
window.closeProviderConfigModal=closeProviderConfigModal;

async function saveProviderConfigModal(event){
  if(event) event.preventDefault();
  const btn=$('providerConfigSaveBtn');
  _setProviderModalStatus();
  const body=_providerModalPayload();
  if(!body.default_model){
    _setProviderModalStatus(t('provider_modal_default_model_required'), 'error');
    try{$('providerConfigModel').focus();}catch(_e){}
    return;
  }
  if(!body.api_key) delete body.api_key;
  if(!body.context_length) delete body.context_length;
  if(btn){btn.disabled=true;btn.textContent=t('providers_saving');}
  try{
    const res=await api('/api/providers',{method:'POST',body:JSON.stringify(body)});
    if(!res.ok) throw new Error(res.error||t('provider_modal_save_failed'));
    closeProviderConfigModal();
    showToast((res.display_name||res.provider)+' '+res.action);
    _refreshModelDropdownsAfterProviderChange();
    await loadProvidersPanel();
  }catch(e){
    const err=$('providerConfigError');
    if(err) _setProviderModalStatus(e.message||String(e), 'error');
    else showToast(t('error_prefix')+(e.message||String(e)));
  }finally{
    if(btn){btn.disabled=false;btn.textContent=t('save');}
  }
}
window.saveProviderConfigModal=saveProviderConfigModal;

async function _deleteCustomProvider(providerId, btn){
  if(!providerId) return;
  if(btn){btn.disabled=true;btn.textContent=t('providers_removing');}
  try{
    const res=await api('/api/providers/delete',{method:'POST',body:JSON.stringify({provider:providerId,custom:true})});
    if(!res.ok) throw new Error(res.error||t('provider_modal_delete_failed'));
    showToast(t('provider_modal_removed', res.provider));
    _refreshModelDropdownsAfterProviderChange();
    await loadProvidersPanel();
  }catch(e){
    showToast(t('error_prefix')+(e.message||String(e)));
    if(btn){btn.disabled=false;btn.textContent=t('delete_title');}
  }
}

function _formatProviderMeta(p,modelCount){
  const sourceLabel=p.key_source==='oauth'
    ? t('providers_status_oauth')
    : p.key_source==='config_yaml'
      ? t('providers_status_configured')
      : (p.has_key ? t('providers_status_api_key') : t('providers_status_not_configured_label'));
  const metaParts=[];
  if(modelCount>0) metaParts.push(modelCount+' '+(modelCount===1?t('providers_model_singular'):t('providers_model_plural')));
  metaParts.push(sourceLabel);
  return metaParts.join(' · ');
}

function _buildProviderCard(p){
  p=Object.assign({},p,{
    models:_normalizeProviderModels(p.models||[]),
  });
  p.models_total=Number.isFinite(p.models_total)?Math.max(p.models_total,p.models.length):p.models.length;
  _providerStateById.set(p.id,Object.assign({},p));
  const card=document.createElement('div');
  card.className='provider-card';
  card.dataset.provider=p.id;
  if(_providerExpandedIds.has(p.id)) card.classList.add('open');
  const isOauth=p.is_oauth===true;
  const modelCount=Number.isFinite(p.models_total)
    ? p.models_total
    : (Array.isArray(p.models) ? p.models.length : 0);

  const header=document.createElement('button');
  header.type='button';
  header.className='provider-card-header';
  header.innerHTML=`
    <div class="provider-card-info">
      <div class="provider-card-name">${esc(p.display_name)}</div>
      <div class="provider-card-meta">${esc(_formatProviderMeta(p,modelCount))}</div>
    </div>
    ${p.has_key?`<span class="provider-card-badge">${esc(t('providers_status_configured'))}</span>`:''}
    <svg class="provider-card-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M6 9l6 6 6-6"/></svg>
  `;
  card.appendChild(header);

  const body=document.createElement('div');
  body.className='provider-card-body';

  if(isOauth){
    const hint=document.createElement('div');
    hint.className='provider-card-hint';
    if(p.key_source==='config_yaml'){
      hint.textContent=t('providers_oauth_config_yaml_hint');
    } else if(p.auth_error){
      hint.textContent=p.auth_error;
      hint.style.color='var(--accent)';
    } else if(p.has_key){
      hint.textContent=t('providers_oauth_hint');
    } else {
      hint.textContent=t('providers_oauth_not_configured_hint');
      hint.style.color='var(--muted)';
    }
    body.appendChild(hint);
    card.appendChild(body);
    header.addEventListener('click',()=>_toggleProviderCardExpanded(card,p.id));
    return card;
  }

  if(p.is_custom){
    const hint=document.createElement('div');
    hint.className='provider-card-hint';
    const bits=[];
    if(p.base_url) bits.push(p.base_url);
    if(p.default_model) bits.push(t('providers_default_model_meta', p.default_model));
    if(p.context_length) bits.push(t('providers_context_length_meta', p.context_length));
    hint.textContent=bits.length?bits.join(' · '):t('providers_custom_config_yaml_hint');
    body.appendChild(hint);
  }

  let input=null;
  let saveBtn=null;
  if(p.configurable||p.is_custom){
    const field=document.createElement('div');
    field.className='provider-card-field';
    const label=document.createElement('label');
    label.className='provider-card-label';
    label.textContent=t('providers_status_api_key');
    field.appendChild(label);

    const row=document.createElement('div');
    row.className='provider-card-row';
    input=document.createElement('input');
    input.type='password';
    input.className='provider-card-input';
    input.placeholder=p.has_key?t('providers_key_placeholder_saved'):t('providers_key_placeholder_new');
    input.dataset.savedKeyHidden=p.has_key?'1':'0';
    input.autocomplete='off';
    const toggleBtn=document.createElement('button');
    toggleBtn.type='button';
    toggleBtn.className='provider-card-btn provider-card-btn-ghost';
    toggleBtn.onclick=()=>_toggleProviderKeyInput(input, toggleBtn);
    _syncProviderKeyToggle(input, toggleBtn);
    saveBtn=document.createElement('button');
    saveBtn.type='button';
    saveBtn.className='provider-card-btn provider-card-btn-primary';
    saveBtn.textContent=t('providers_save');
    saveBtn.onclick=()=>_saveProviderKey(p.id);
    saveBtn.disabled=true;
    row.appendChild(input);
    row.appendChild(toggleBtn);
    row.appendChild(saveBtn);
    if(p.has_key){
      const removeBtn=document.createElement('button');
      removeBtn.type='button';
      removeBtn.className='provider-card-btn provider-card-btn-danger';
      removeBtn.textContent=t('providers_remove');
      removeBtn.onclick=()=>_removeProviderKey(p.id);
      row.appendChild(removeBtn);
    }
    field.appendChild(row);
    body.appendChild(field);
  }else{
    const hint=document.createElement('div');
    hint.className='provider-card-hint';
    hint.textContent=t('providers_managed_externally_hint');
    body.appendChild(hint);
  }

  if(p.is_custom&&p.editable){
    const actions=document.createElement('div');
    actions.className='provider-card-row';
    const editBtn=document.createElement('button');
    editBtn.type='button';
    editBtn.className='provider-card-btn provider-card-btn-ghost';
    editBtn.textContent=t('edit');
    editBtn.onclick=()=>openProviderConfigModal(p);
    actions.appendChild(editBtn);
    if(p.allow_delete!==false){
      const deleteBtn=document.createElement('button');
      deleteBtn.type='button';
      deleteBtn.className='provider-card-btn provider-card-btn-danger';
      deleteBtn.textContent=t('delete_title');
      deleteBtn.onclick=()=>_deleteCustomProvider(p.id, deleteBtn);
      actions.appendChild(deleteBtn);
    }
    body.appendChild(actions);
  }

  card.appendChild(body);
  _renderProviderCardModels(card,p);
  if(input&&saveBtn){
    _providerCardEls.set(p.id,{card,input,saveBtn,hasKey:p.has_key});
    input.addEventListener('input',()=>{
      _syncProviderKeyToggle(input, input.parentNode?input.parentNode.querySelector('.provider-card-btn-ghost'):null);
      saveBtn.disabled=!input.value.trim();
    });
  }
  header.addEventListener('click',e=>{
    if(e.target.closest('.provider-card-body')) return;
    _toggleProviderCardExpanded(card,p.id);
    if(input&&card.classList.contains('open')) setTimeout(()=>input.focus(),0);
  });
  return card;
}

function _toggleProviderCardExpanded(card, providerId){
  if(!card||!providerId) return;
  card.classList.toggle('open');
  if(card.classList.contains('open')) _providerExpandedIds.add(providerId);
  else _providerExpandedIds.delete(providerId);
}

function _renderProviderCardModels(card,p){
  const body=card?card.querySelector('.provider-card-body'):null;
  if(!body) return;
  const renderedModels=_normalizeProviderModels(p.models||[]);
  const totalCount=Number.isFinite(p.models_total)?p.models_total:renderedModels.length;
  const modelCount=Math.max(totalCount, renderedModels.length);
  let modelSection=body.querySelector('.provider-card-models');
  if(modelCount<=0){
    if(modelSection) modelSection.remove();
    return;
  }
  if(!modelSection){
    modelSection=document.createElement('div');
    modelSection.className='provider-card-models';
    const modelLabel=document.createElement('div');
    modelLabel.className='provider-card-label';
    modelLabel.textContent=t('providers_models_label');
    modelSection.appendChild(modelLabel);
    const modelList=document.createElement('div');
    modelList.className='provider-card-model-tags';
    modelSection.appendChild(modelList);
    body.appendChild(modelSection);
  }
  const modelList=modelSection.querySelector('.provider-card-model-tags');
  if(!modelList) return;
  modelList.innerHTML='';
  for(const m of renderedModels){
    const tag=document.createElement('span');
    tag.className='provider-card-model-tag';
    tag.textContent=m.id||m.label||m;
    modelList.appendChild(tag);
  }
  const hiddenCount=Math.max(0, totalCount - renderedModels.length);
  if(hiddenCount>0){
    const more=document.createElement('span');
    more.className='provider-card-model-tag provider-card-model-tag-more';
    more.textContent=t('providers_models_more', hiddenCount);
    more.title=t('providers_models_more_title');
    modelList.appendChild(more);
  }
}

function _updateProviderCardModels(providerId, models){
  const cardEls=_providerCardEls.get(providerId);
  const card=cardEls?cardEls.card:document.querySelector(`.provider-card[data-provider="${_providerSelectorValue(providerId)}"]`);
  const provider=Object.assign({},_providerStateById.get(providerId)||{id:providerId});
  provider.models=_normalizeProviderModels(models);
  provider.models_total=provider.models.length;
  _providerStateById.set(providerId,provider);
  if(!card) return;
  const meta=card.querySelector('.provider-card-meta');
  if(meta) meta.textContent=_formatProviderMeta(provider,provider.models_total);
  _renderProviderCardModels(card,provider);
}

async function _saveProviderKey(providerId){
  const els=_providerCardEls.get(providerId);
  if(!els) return;
  const key=els.input.value.trim();
  if(!key){
    showToast(t('providers_enter_key'));
    return;
  }
  els.saveBtn.disabled=true;
  els.saveBtn.textContent=t('providers_saving');
  try{
    const res=await api('/api/providers',{method:'POST',body:JSON.stringify({provider:providerId,api_key:key})});
    if(res.ok){
      showToast(res.provider+' '+t('providers_key_updated').toLowerCase());
      els.input.value='';
      _refreshModelDropdownsAfterProviderChange();
      await loadProvidersPanel();
    }else{
      showToast(res.error||t('provider_modal_save_failed'));
      els.saveBtn.disabled=false;
      els.saveBtn.textContent=t('providers_save');
    }
  }catch(e){
    showToast(t('error_prefix')+(e.message||String(e)));
    els.saveBtn.disabled=false;
    els.saveBtn.textContent=t('providers_save');
  }
}

async function _removeProviderKey(providerId){
  const els=_providerCardEls.get(providerId);
  if(!els) return;
  if(els.saveBtn){els.saveBtn.disabled=true;els.saveBtn.textContent=t('providers_removing');}
  try{
    const res=await api('/api/providers/delete',{method:'POST',body:JSON.stringify({provider:providerId})});
    if(res.ok){
      showToast(res.provider+' '+t('providers_key_removed').toLowerCase());
      _refreshModelDropdownsAfterProviderChange();
      await loadProvidersPanel();
    }else{
      showToast(res.error||t('provider_modal_delete_failed'));
      if(els.saveBtn){els.saveBtn.disabled=false;els.saveBtn.textContent=t('providers_save');}
    }
  }catch(e){
    showToast(t('error_prefix')+(e.message||String(e)));
    if(els.saveBtn){els.saveBtn.disabled=false;els.saveBtn.textContent=t('providers_save');}
  }
}

function _refreshModelDropdownsAfterProviderChange(){
  try{
    if(typeof window._invalidateSlashModelCache==='function'){
      window._invalidateSlashModelCache();
    }
    if(typeof window._ensureModelDropdownReady==='function'){
      window._modelDropdownReady=null;
      Promise.resolve(window._ensureModelDropdownReady()).catch(()=>{});
    }else if(typeof populateModelDropdown==='function'){
      Promise.resolve(populateModelDropdown()).catch(()=>{});
    }
  }catch(_e){}
}

async function _refreshProviderModels(providerId, btn){
  btn.disabled=true;
  const orig=btn.innerHTML;
  btn.innerHTML=_providerModelRefreshIcon()+' '+esc(t('providers_refreshing'));
  _setProviderModalStatus(t('providers_refreshing'), 'loading');
  try{
    const body=_providerModalPayload();
    if(!body.api_key){
      _setProviderModalStatus(t('provider_modal_api_key_required_for_refresh'), 'error');
      try{$('providerConfigApiKey').focus();}catch(_e){}
      return;
    }
    const res=await api('/api/models/refresh',{method:'POST',body:JSON.stringify({
      provider:providerId,
      base_url:body.base_url,
      api_key:body.api_key,
    })});
    if(res.ok){
      const models=_normalizeProviderModels(res.models||[]);
      if(!models.length){
        _setProviderModalStatus(res.message||res.error||t('providers_models_refresh_empty'), 'warning');
        return;
      }
      _setProviderModelOptions(models);
      _updateProviderCardModels(providerId, models);
      _setProviderModalStatus(t('providers_models_refreshed', res.provider||providerId), 'success');
      _refreshModelDropdownsAfterProviderChange();
    }else{
      _setProviderModalStatus(res.message||res.error||t('providers_models_refresh_failed'), 'error');
    }
  }catch(e){
    _setProviderModalStatus(t('error_prefix')+(e.message||String(e)), 'error');
  }finally{
    btn.disabled=false;
    btn.innerHTML=orig;
  }
}

if (window.HermesPanelRegistry) {
  window.HermesPanelRegistry.registerSettingsSection('providers', {
    onOpen: () => loadProvidersPanel(),
    onSettingsLoaded: () => loadProvidersPanel(),
  });
}
