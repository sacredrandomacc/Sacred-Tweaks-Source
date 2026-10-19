'use strict';
// Custom dropdowns. Each native <select> stays in the form (FormData, validation and
// change listeners keep working) but is hidden behind a themed trigger + listbox.
// The list is portalled to <body> with fixed positioning so panels never clip it
// and glass blur works behind it.
(() => {
  let open = null; // {select, trigger, list, index}
  const label = select => select.selectedOptions[0]?.textContent || '';
  function sync(select) {
    const wrap = select.closest('.sx');
    if (wrap) wrap.querySelector('.sx-value').textContent = label(select);
  }
  function enhance(select) {
    if (select.dataset.sx || select.multiple || select.size > 1) return;
    select.dataset.sx = '1';
    const wrap = document.createElement('div');
    wrap.className = 'sx';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'sx-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const name = select.labels?.[0]?.textContent?.trim() || select.getAttribute('aria-label') || '';
    if (name) trigger.setAttribute('aria-label', name);
    trigger.innerHTML = '<span class="sx-value"></span><svg class="sx-chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
    wrap.appendChild(trigger);
    if (select.id) for (const l of select.labels || []) l.addEventListener('click', e => { e.preventDefault(); trigger.focus(); });
    sync(select);
    select.addEventListener('change', () => sync(select));
  }
  function place() {
    if (!open) return;
    const r = open.trigger.getBoundingClientRect(), list = open.list, room = innerHeight - r.bottom - 12;
    list.style.minWidth = r.width + 'px';
    list.style.left = Math.min(r.left, innerWidth - list.offsetWidth - 8) + 'px';
    const up = room < Math.min(list.scrollHeight, 280) && r.top > room;
    list.style.top = up ? '' : (r.bottom + 6) + 'px';
    list.style.bottom = up ? (innerHeight - r.top + 6) + 'px' : '';
    list.classList.toggle('up', up);
  }
  function highlight(index) {
    const options = [...open.list.children];
    open.index = Math.max(0, Math.min(options.length - 1, index));
    options.forEach((o, i) => o.classList.toggle('active', i === open.index));
    options[open.index]?.scrollIntoView({block: 'nearest'});
    open.trigger.setAttribute('aria-activedescendant', options[open.index]?.id || '');
  }
  function show(trigger) {
    close();
    const select = trigger.parentNode.querySelector('select');
    if (select.disabled) return;
    const list = document.createElement('ul');
    list.className = 'sx-list';
    list.setAttribute('role', 'listbox');
    const id = 'sx-' + Math.random().toString(36).slice(2, 8);
    list.id = id;
    [...select.options].forEach((option, i) => {
      const li = document.createElement('li');
      li.id = `${id}-${i}`;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', String(option.selected));
      if (option.disabled) li.setAttribute('aria-disabled', 'true');
      li.textContent = option.textContent;
      li.style.setProperty('--i', i);
      li.addEventListener('pointerdown', e => { e.preventDefault(); choose(i); });
      list.appendChild(li);
    });
    document.body.appendChild(list);
    trigger.setAttribute('aria-expanded', 'true');
    trigger.setAttribute('aria-controls', id);
    trigger.closest('.sx').classList.add('open');
    open = {select, trigger, list, index: select.selectedIndex};
    place();
    highlight(select.selectedIndex);
    window.SacredSound?.play('tick');
  }
  function close(focus = false) {
    if (!open) return;
    const {trigger, list} = open;
    trigger.setAttribute('aria-expanded', 'false');
    trigger.closest('.sx')?.classList.remove('open');
    list.classList.add('closing');
    setTimeout(() => list.remove(), 160);
    open = null;
    if (focus) trigger.focus();
  }
  function choose(index) {
    const {select} = open;
    if (select.options[index]?.disabled) return;
    const changed = select.selectedIndex !== index;
    select.selectedIndex = index;
    sync(select);
    close(true);
    window.SacredSound?.play('select');
    if (changed) {
      select.dispatchEvent(new Event('input', {bubbles: true}));
      select.dispatchEvent(new Event('change', {bubbles: true}));
    }
  }
  let typed = '', typedAt = 0;
  document.addEventListener('click', e => {
    const trigger = e.target.closest?.('.sx-trigger');
    if (trigger) { open?.trigger === trigger ? close() : show(trigger); return; }
    if (open && !e.target.closest('.sx-list')) close();
  });
  document.addEventListener('keydown', e => {
    const trigger = e.target.closest?.('.sx-trigger');
    if (!open) {
      if (trigger && ['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) { e.preventDefault(); show(trigger); }
      return;
    }
    if (e.key === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); close(true); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); highlight(open.index + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(open.index - 1); }
    else if (e.key === 'Home') { e.preventDefault(); highlight(0); }
    else if (e.key === 'End') { e.preventDefault(); highlight(open.list.children.length - 1); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(open.index); }
    else if (e.key === 'Tab') close();
    else if (e.key.length === 1) {
      typed = performance.now() - typedAt > 700 ? e.key.toLowerCase() : typed + e.key.toLowerCase();
      typedAt = performance.now();
      const match = [...open.list.children].findIndex(li => li.textContent.toLowerCase().startsWith(typed));
      if (match >= 0) highlight(match);
    }
  }, true);
  addEventListener('resize', () => close());
  document.addEventListener('scroll', e => { if (open && !open.list.contains(e.target)) close(); }, true);
  const scan = root => root.querySelectorAll?.('select').forEach(enhance);
  new MutationObserver(records => {
    for (const r of records) for (const node of r.addedNodes) if (node.nodeType === 1) { node.tagName === 'SELECT' ? enhance(node) : scan(node); }
    if (open && !open.trigger.isConnected) close();
  }).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener('DOMContentLoaded', () => scan(document));
  window.SacredSelect = {sync, enhance};
})();
