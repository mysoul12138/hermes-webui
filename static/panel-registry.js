(function(){
  const panels = new Map();
  const settingsSections = new Map();

  function normalizeKey(key){
    return String(key || '').trim().toLowerCase();
  }

  function registerPanel(key, handlers){
    const name = normalizeKey(key);
    if(!name) return;
    panels.set(name, handlers || {});
  }

  function registerSettingsSection(key, handlers){
    const name = normalizeKey(key);
    if(!name) return;
    settingsSections.set(name, handlers || {});
  }

  async function runHandler(registry, key, handlerName, context){
    const handlers = registry.get(normalizeKey(key));
    const handler = handlers && handlers[handlerName];
    if(typeof handler !== 'function') return false;
    await handler(context || {});
    return true;
  }

  window.HermesPanelRegistry = Object.assign(window.HermesPanelRegistry || {}, {
    registerPanel,
    registerSettingsSection,
    openPanel: (key, context) => runHandler(panels, key, 'onOpen', context),
    openSettingsSection: (key, context) => runHandler(settingsSections, key, 'onOpen', context),
    settingsLoaded: (key, context) => runHandler(settingsSections, key, 'onSettingsLoaded', context),
  });
})();
