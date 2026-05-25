from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_composer_model_dropdown_has_scope_advisory():
    ui = read("static/ui.js")
    style = read("static/style.css")

    assert "model-scope-note" in ui
    assert "model_scope_advisory" in ui
    assert "Applies to this conversation from your next message." in ui
    assert ui.index("dd.appendChild(_scopeNote);") < ui.index("dd.appendChild(_searchRow);")
    assert ".model-scope-note" in style
    assert "position:sticky" in style


def test_composer_model_dropdown_provider_groups_are_collapsible():
    ui = read("static/ui.js")
    style = read("static/style.css")

    assert "const _collapsedModelProviderGroups=new Set();" in ui
    assert "const _modelGroupKey=(m)=>String((m&&m.providerId)||((m&&m.group)||''));" in ui
    assert "className='model-group model-group-toggle'" in ui
    assert "model-group-chevron" in ui
    assert "model-group-count" in ui
    assert "aria-expanded" in ui
    assert "const collapsed=!term&&groupKey&&_collapsedModelProviderGroups.has(groupKey);" in ui
    assert "if(collapsed) continue;" in ui
    assert ".model-group-toggle" in style
    assert ".model-group-toggle.collapsed .model-group-chevron" in style
    assert ".model-group-count" in style


def test_model_group_collapse_preserves_search_focus_and_scroll():
    ui = read("static/ui.js")

    assert "_filterModels(_si.value,{preserveFocus:true,preserveScrollTop:previousScrollTop});" in ui
    assert "const previousScrollTop=dd.scrollTop||0;" in ui
    assert "if(Number.isFinite(opts.preserveScrollTop)) dd.scrollTop=opts.preserveScrollTop;" in ui
    assert "if(!opts.preserveFocus) _si.focus();" in ui


def test_model_selection_toast_describes_conversation_scope():
    boot = read("static/boot.js")
    i18n = read("static/i18n.js")

    assert "model_scope_toast" in boot
    assert "Applies to this conversation from your next message." in i18n
    assert "model_scope_advisory: 'Applies to this conversation from your next message.'" in i18n
    assert "model_scope_toast: 'Applies to this conversation from your next message.'" in i18n
    assert "Model change takes effect in your next conversation" not in boot


def test_settings_default_model_copy_describes_new_conversations():
    html = read("static/index.html")
    i18n = read("static/i18n.js")

    assert 'data-i18n="settings_desc_model"' in html
    assert "Used for new conversations. Existing conversations keep their selected model." in html
    assert "settings_desc_model" in i18n
