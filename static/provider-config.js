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
  const providerId=(provider&&typeof provider==='object'&&typeof provider.id==='string'&&provider.id.trim())
    ? provider.id.trim()
    : 'custom';
  refreshBtn.hidden=false;
  refreshBtn.innerHTML=_providerModelRefreshIcon()+' '+esc(t('providers_refresh_models'));
  refreshBtn.onclick=()=>_refreshProviderModels(providerId, refreshBtn);
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
  providerId=(providerId&&typeof providerId==='object')?String(providerId.id||'').trim():String(providerId||'').trim();
  if(!providerId) providerId='custom';
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

let _providersPanelLoadPromise = null;

async function _fetchProviderQuotaStatus(force=false){
  const endpoint=force?`/api/provider/quota?refresh=1&ts=${Date.now()}`:'/api/provider/quota';
  const status=await api(endpoint,{cache:'no-store'});
  if(status&&typeof status==='object') status.client_fetched_at=new Date().toISOString();
  return status;
}

async function loadProvidersPanel(){
  const list=$('providersList');
  const empty=$('providersEmpty');
  if(!list) return;
  if(_providersPanelLoadPromise) return _providersPanelLoadPromise;
  const loadPromise=(async()=>{
  try{
    const data=await api('/api/providers');
    const quota=await _fetchProviderQuotaStatus(false).catch(e=>({ok:false,status:'unavailable',quota:null,message:e.message||t('provider_quota_unavailable'),client_fetched_at:new Date().toISOString()}));
    const providers=(data.providers||[]).filter(p=>p.configurable||p.is_oauth||p.is_custom);
    list.innerHTML='';
    const quotaCard=_buildProviderQuotaCard(quota);
    if(quotaCard) list.appendChild(quotaCard);
    if(providers.length===0){
      list.style.display='none';
      if(empty) empty.style.display='';
      return;
    }
    if(empty) empty.style.display='none';
    list.style.display='';
    for(const p of providers){
      list.appendChild(_buildProviderCard(p));
    }
    list.dataset.providersLoaded='1';
  }catch(e){
    if(list.dataset.providersLoaded==='1') return;
    list.innerHTML='<div style="color:var(--error);padding:12px;font-size:13px">Failed to load providers: '+esc(e.message||String(e))+'</div>';
    list.dataset.providersLoaded='0';
  }
  })();
  _providersPanelLoadPromise=loadPromise;
  try{
    return await loadPromise;
  }finally{
    if(_providersPanelLoadPromise===loadPromise) _providersPanelLoadPromise=null;
  }
}

async function _refreshProviderQuota(card,button){
  if(!card) return;
  if(button){
    button.disabled=true;
    button.textContent=t('provider_quota_refreshing');
    button.setAttribute('aria-busy','true');
  }
  let failed=false;
  let next;
  try{
    next=await _fetchProviderQuotaStatus(true);
    failed=next&&next.ok===false;
  }catch(e){
    failed=true;
    next={ok:false,status:'unavailable',quota:null,message:e.message||t('provider_quota_unavailable'),client_fetched_at:new Date().toISOString()};
  }
  try{
    const fresh=_buildProviderQuotaCard(next);
    if(fresh){
      card.replaceWith(fresh);
      if(typeof showToast==='function') showToast(failed?t('provider_quota_refresh_failed'):t('provider_quota_refresh_succeeded'));
      return;
    }
  }catch(e){
    failed=true;
  }
  if(card.isConnected&&button){
    button.disabled=false;
    button.textContent=t('provider_quota_refresh_usage');
    button.removeAttribute('aria-busy');
  }
  if(typeof showToast==='function') showToast(t('provider_quota_refresh_failed'));
}

function _formatProviderQuotaMoney(value){
  if(value===null||value===undefined||value==='') return '—';
  const n=Number(value);
  if(!Number.isFinite(n)) return '—';
  return '$'+n.toFixed(2);
}

function _formatProviderQuotaPercent(value){
  if(value===null||value===undefined||value==='') return '—';
  const n=Number(value);
  if(!Number.isFinite(n)) return '—';
  return Math.max(0,Math.min(100,Math.round(n)))+'%';
}

function _formatProviderQuotaReset(value){
  if(!value) return '';
  const d=new Date(value);
  if(Number.isNaN(d.getTime())) return '';
  try{return d.toLocaleString();}catch(e){return value;}
}

function _formatProviderQuotaWindowLabel(accountLimits,w){
  const raw=((w&&w.label)||t('provider_quota_window_fallback')).trim();
  const provider=((accountLimits&&accountLimits.provider)||'').toLowerCase();
  if(provider==='openai-codex'){
    if(raw.toLowerCase()==='session') return t('provider_quota_session_limit');
    if(raw.toLowerCase()==='weekly') return t('provider_quota_weekly_limit');
  }
  return raw||t('provider_quota_window_fallback');
}

function _formatProviderQuotaLastChecked(status){
  const accountLimits=status&&status.account_limits;
  const value=(accountLimits&&accountLimits.fetched_at)||status&&status.client_fetched_at;
  if(!value) return t('provider_quota_last_checked_after_refresh');
  const d=new Date(value);
  if(Number.isNaN(d.getTime())) return t('provider_quota_last_checked_after_refresh');
  try{return t('provider_quota_last_checked',d.toLocaleString());}catch(e){return t('provider_quota_last_checked',value);}
}

function _providerQuotaStateClass(value){
  return String(value||'unavailable').replace(/[^a-z0-9_-]/gi,'').toLowerCase()||'unavailable';
}

function _providerQuotaStatusLabel(value){
  const state=_providerQuotaStateClass(value);
  const key={
    available:'provider_quota_status_available',
    exhausted:'provider_quota_status_exhausted',
    unavailable:'provider_quota_status_unavailable',
    failed:'provider_quota_status_failed',
    checked:'provider_quota_status_checked',
    no_key:'provider_quota_status_no_key',
    invalid_key:'provider_quota_status_invalid_key',
    unsupported:'provider_quota_status_unsupported',
  }[state];
  return key?t(key):state.replace(/_/g,' ');
}

function _providerQuotaWindowMeta(used,reset){
  const meta=[];
  if(used!=='—') meta.push(t('provider_quota_used_meta',used));
  if(reset) meta.push(t('provider_quota_resets_meta',reset));
  return meta;
}

function _providerQuotaRetryAfterText(value){
  const retry=_formatProviderQuotaReset(value);
  return retry?t('provider_quota_retry_after',retry):'';
}

function _providerQuotaUnavailableReason(credential){
  const structured=_providerQuotaRetryAfterText(credential&&credential.retry_after);
  if(structured) return structured;
  const raw=String((credential&&credential.unavailable_reason)||'').trim();
  const match=raw.match(/\bretry after\s+([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.+-]+Z?)/i);
  if(match){
    const parsed=_providerQuotaRetryAfterText(match[1]);
    if(parsed) return parsed;
  }
  return raw;
}

function _providerQuotaPoolShouldDefaultOpen(pool){
  try{
    const saved=localStorage.getItem('hermes-provider-quota-pool-open');
    if(saved==='1') return true;
    if(saved==='0') return false;
  }catch(e){}
  const count=Array.isArray(pool&&pool.credentials)?pool.credentials.length:0;
  return count>0&&count<=3;
}

function _buildProviderQuotaPoolBreakdown(accountLimits){
  const pool=accountLimits&&accountLimits.pool;
  if(!pool||!Array.isArray(pool.credentials)||pool.credentials.length===0) return '';
  const defaultOpen=_providerQuotaPoolShouldDefaultOpen(pool);
  const total=Number.isFinite(Number(pool.total_credentials))?Number(pool.total_credentials):pool.credentials.length;
  const available=Number.isFinite(Number(pool.available_credentials))?Number(pool.available_credentials):pool.credentials.filter(c=>c&&c.status==='available').length;
  const exhausted=Number.isFinite(Number(pool.exhausted_credentials))?Number(pool.exhausted_credentials):0;
  const failed=Number.isFinite(Number(pool.failed_credentials))?Number(pool.failed_credentials):0;
  const queried=Number.isFinite(Number(pool.queried_credentials))?Number(pool.queried_credentials):0;
  const summaryParts=[t('provider_quota_pool_summary_available',available,total)];
  if(exhausted>0) summaryParts.push(t('provider_quota_pool_summary_exhausted',exhausted));
  if(failed>0) summaryParts.push(t('provider_quota_pool_summary_failed',failed));
  if(queried>0) summaryParts.push(t('provider_quota_pool_summary_checked',queried));
  const planParts=Array.isArray(pool.plans)?pool.plans.filter(Boolean):[];
  const rows=pool.credentials.map((credential,idx)=>{
    const label=(credential&&credential.label)||t('provider_quota_credential_label',idx+1);
    const status=_providerQuotaStateClass(credential&&credential.status);
    const statusText=_providerQuotaStatusLabel(credential&&credential.status);
    const plan=credential&&credential.plan?` · ${credential.plan}`:'';
    const windows=Array.isArray(credential&&credential.windows)?credential.windows:[];
    const details=Array.isArray(credential&&credential.details)?credential.details.filter(Boolean):[];
    const unavailableReason=_providerQuotaUnavailableReason(credential);
    const windowHtml=windows.length?windows.map(w=>{
      const remaining=_formatProviderQuotaPercent(w&&w.remaining_percent);
      const used=_formatProviderQuotaPercent(w&&w.used_percent);
      const reset=_formatProviderQuotaReset(w&&w.reset_at);
      const meta=_providerQuotaWindowMeta(used,reset);
      const detail=(w&&w.detail)?String(w.detail).trim():'';
      return `<div class="provider-quota-pool-window"><span>${esc(_formatProviderQuotaWindowLabel(accountLimits,w))}</span><strong>${esc(remaining)}</strong>${meta.length?`<small>${esc(meta.join(' · '))}</small>`:''}${detail?`<small class="provider-quota-window-detail">${esc(detail)}</small>`:''}</div>`;
    }).join(''):`<div class="provider-quota-pool-note">${esc(unavailableReason||t('provider_quota_pool_no_windows'))}</div>`;
    const detailHtml=details.length?`<div class="provider-quota-pool-details">${details.map(d=>`<span>${esc(d)}</span>`).join('')}</div>`:'';
    return `
      <div class="provider-quota-pool-row provider-quota-pool-row-${status}">
        <div class="provider-quota-pool-row-head">
          <span>${esc(label)}${esc(plan)}</span>
          <strong>${esc(statusText)}</strong>
        </div>
        <div class="provider-quota-pool-windows">${windowHtml}</div>
        ${detailHtml}
      </div>
    `;
  }).join('');
  const planText=planParts.length?`<div class="provider-quota-pool-plans">${esc(t('provider_quota_pool_plans',planParts.join(', ')))}</div>`:'';
  return `
    <details class="provider-quota-pool"${defaultOpen?' open':''}>
      <summary><span class="provider-quota-pool-summary-label"><span class="provider-quota-pool-chevron" aria-hidden="true"></span><span>${esc(t('provider_quota_credential_pool'))}</span></span><strong>${esc(summaryParts.join(' · '))}</strong></summary>
      ${planText}
      <div class="provider-quota-pool-rows">${rows}</div>
    </details>
  `;
}

function _buildProviderQuotaCard(status){
  if(!status) return null;
  const card=document.createElement('div');
  const state=(status.status||'unavailable').replace(/[^a-z0-9_-]/gi,'').toLowerCase()||'unavailable';
  card.className='provider-quota-card provider-quota-card-'+state;
  const accountLimits=status.account_limits||null;
  const providerBase=status.display_name||status.provider||t('provider_quota_active_provider');
  const provider=(accountLimits&&accountLimits.plan)?`${providerBase} · ${accountLimits.plan}`:providerBase;
  const quota=status.quota||null;
  let body='';
  if(accountLimits&&(status.status==='available'||accountLimits.pool)){
    const windows=Array.isArray(accountLimits.windows)?accountLimits.windows:[];
    const details=Array.isArray(accountLimits.details)&&!accountLimits.pool?accountLimits.details:[];
    const windowHtml=windows.map(w=>{
      const used=_formatProviderQuotaPercent(w&&w.used_percent);
      const reset=_formatProviderQuotaReset(w&&w.reset_at);
      const meta=_providerQuotaWindowMeta(used,reset);
      const detail=(w&&w.detail)?String(w.detail).trim():'';
      return `
        <div class="provider-quota-metric provider-quota-window">
          <span>${esc(_formatProviderQuotaWindowLabel(accountLimits,w))}</span>
          <strong>${esc(_formatProviderQuotaPercent(w&&w.remaining_percent))}</strong>
          ${meta.length?`<small>${esc(meta.join(' · '))}</small>`:''}
          ${detail?`<small class="provider-quota-window-detail">${esc(detail)}</small>`:''}
        </div>
      `;
    }).join('');
    const detailHtml=details.length
      ? `<div class="provider-quota-details">${details.map(d=>`<span>${esc(d)}</span>`).join('')}</div>`
      : '';
    const poolHtml=_buildProviderQuotaPoolBreakdown(accountLimits);
    body=windowHtml+detailHtml+poolHtml;
    if(!body) body=`<div class="provider-quota-message">${esc(status.message||t('provider_quota_account_limits_loaded'))}</div>`;
  }else if(status.status==='available'&&quota){
    body=`
      <div class="provider-quota-metric"><span>${esc(t('provider_quota_metric_remaining'))}</span><strong>${esc(_formatProviderQuotaMoney(quota.limit_remaining))}</strong></div>
      <div class="provider-quota-metric"><span>${esc(t('provider_quota_metric_used'))}</span><strong>${esc(_formatProviderQuotaMoney(quota.usage))}</strong></div>
      <div class="provider-quota-metric"><span>${esc(t('provider_quota_metric_limit'))}</span><strong>${esc(_formatProviderQuotaMoney(quota.limit))}</strong></div>
    `;
  }else{
    body=`<div class="provider-quota-message">${esc(status.message||t('provider_quota_unavailable'))}</div>`;
  }
  card.innerHTML=`
    <div class="provider-quota-header">
      <div>
        <div class="provider-quota-title">${esc(t('provider_quota_title'))}</div>
        <div class="provider-quota-provider">${esc(provider)}</div>
      </div>
      <button type="button" class="provider-card-btn provider-card-btn-ghost" data-provider-quota-refresh>${esc(t('provider_quota_refresh_usage'))}</button>
    </div>
    <div class="provider-quota-status provider-quota-status-${state}">${esc(_providerQuotaStatusLabel(status.status))}</div>
    <div class="provider-quota-body">${body}</div>
    <div class="provider-quota-footer">${esc(_formatProviderQuotaLastChecked(status))}</div>
  `;
  const refreshBtn=card.querySelector('[data-provider-quota-refresh]');
  if(refreshBtn) refreshBtn.addEventListener('click',()=>_refreshProviderQuota(card,refreshBtn));
  const poolDetails=card.querySelector('.provider-quota-pool');
  if(poolDetails){
    poolDetails.addEventListener('toggle',()=>{
      try{localStorage.setItem('hermes-provider-quota-pool-open', poolDetails.open?'1':'0');}catch(e){}
    });
  }
  return card;
}

window.loadProvidersPanel=loadProvidersPanel;
