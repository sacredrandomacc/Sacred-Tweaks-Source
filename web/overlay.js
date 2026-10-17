'use strict';
(() => {
 const $=selector=>document.querySelector(selector);
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const state={page:'overview',account:{},prefs:{hotkey:'TAB',accent:'violet',opacity:94,reduced_motion:false}};
 let toastTimer;
 function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;toastTimer=setTimeout(()=>$('#toast').textContent='',4000);}
 async function invoke(name,...args){if(!window.pywebview?.api)throw Error('Open the Windows application to use the overlay.');return window.pywebview.api[name](...args);}
 function duration(){const l=state.account.license;if(!state.account.signed_in)return 'Sign in from the desktop app';if(l?.permanent)return 'Permanent license';if(!l?.expires_at)return 'License active';const seconds=Math.max(0,Number(l.expires_at)*1000-Date.now());return seconds?Math.ceil(seconds/86400000)+' days remaining':'License expired';}
 function account(){
  const a=state.account;$('#username').textContent=a.signed_in?a.username:'Signed out';
  $('#avatar').textContent=a.signed_in?a.username.slice(0,2).toUpperCase():'S';
  $('#account-button').dataset.tier=String(a.tier||'').toLowerCase();
  $('#license-time').textContent=duration();
  $('#rail-status').textContent=a.signed_in?'Companion ready':'Sign in required';
  $('#account-popover').innerHTML=`<strong>${escape(a.signed_in?a.username:'Sacred Tweaks')}</strong><small>${escape(a.tier||'Account unavailable')} · ${escape(duration())}</small><button data-action="desktop">Open account in desktop app</button>`;
 }
 function prefs(){
  document.body.dataset.accent=state.prefs.accent;
  document.body.dataset.reduced=String(state.prefs.reduced_motion);
  document.documentElement.style.setProperty('--opacity',String(state.prefs.opacity/100));
  $('#footer-key').textContent=state.prefs.hotkey+' TO CLOSE';
 }
 function intro(title,description){return `<div class="intro"><div><h2>${title}</h2><p>${description}</p></div><span class="pill">SACRED / LIVE</span></div>`;}
 function overview(){
  return intro('Your session, at a glance','A quiet control space that appears only when you ask for it.')+
   `<div class="grid"><section class="card"><div class="label">ACCOUNT STATUS</div><div class="metric">${state.account.signed_in?'Connected':'Signed out'}</div><p>${escape(state.account.signed_in?state.account.username+' · '+state.account.tier+' membership':'Sign in from the main desktop app to access licensed settings.')}</p></section>
   <section class="card"><div class="label">LICENSE</div><div class="metric">${escape(duration())}</div><p>Account and tier information come from the current desktop session.</p></section>
   <section class="card wide"><div class="row"><div><div class="label">QUICK ACCESS</div><h3>Make your next change deliberately.</h3><p>Preview supported performance settings, adjust the overlay, or open the full desktop workspace.</p></div><button class="button primary" data-action="desktop">Open desktop app ↗</button></div></section>
   <section class="card wide"><div class="notice">The companion is a separate Windows window. It does not read Fortnite memory or draw into the game. Borderless windowed mode is required for reliable visibility. Third-party app or macro safety cannot be guaranteed.</div></section></div>`;
 }
 function performance(){
  const allowed=state.account.permissions?.performance;
  return intro('Performance, under your control','Inspect a preset while playing. Apply changes later from the desktop app with Fortnite closed.')+
   `<div class="grid"><section class="card wide"><div class="label">PREVIEW A PRESET</div><form id="preview-form" class="stack"><div class="options">
   <label class="choice"><input name="preset" type="radio" value="performance" checked><strong>Maximum FPS</strong><small>Frame rate first</small></label>
   <label class="choice"><input name="preset" type="radio" value="balanced"><strong>Balanced</strong><small>Clarity and responsiveness</small></label></div>
   <label class="field">Target frame rate<input name="fps" type="number" min="30" max="1000" value="144"></label>
   <div class="row"><p>Preview reads supported local settings. It does not apply changes while Fortnite runs.</p><button class="button primary" type="submit" ${allowed?'':'disabled'}>Preview changes</button></div></form></section>
   <section class="card wide"><div class="label">REVIEW</div><div id="preview-result" class="result">${allowed?'Select a preset to inspect the proposed changes.':'Performance access is unavailable for this account.'}</div></section></div>`;
 }
 function windows(){
  return intro('Windows settings','Open supported system pages to review each change yourself.')+
   `<div class="grid"><section class="card wide"><div class="label">SYSTEM SHORTCUTS</div><div class="options">
   ${[['game_mode','Game Mode'],['capture','Capture settings'],['graphics','Graphics preference'],['display','Display settings']].map(([id,label])=>`<button class="button" data-settings="${id}">${label} ↗</button>`).join('')}</div></section>
   <section class="card wide"><div class="notice">Opening Windows Settings switches focus away from Fortnite and closes this menu. Changes on those pages are made by you.</div></section></div>`;
 }
 function appearance(){
  return intro('Make it yours','Adjust the companion’s shortcut and presentation.')+
   `<div class="grid"><section class="card"><div class="label">INPUT</div><label class="field">Open / close hotkey<select id="hotkey">${['TAB','F6','F7','F9','F10','F11'].map(k=>`<option value="${k}" ${k===state.prefs.hotkey?'selected':''}>${k}</option>`).join('')}</select></label>
   <p style="margin-top:13px">The hotkey still reaches the game when this window is hidden. Choose an unused key if Tab opens your inventory.</p></section>
   <section class="card"><div class="label">COLOR</div><label class="field">Accent<select id="accent">${[['violet','Violet'],['blue','Steel blue'],['amber','Warm amber']].map(([k,n])=>`<option value="${k}" ${k===state.prefs.accent?'selected':''}>${n}</option>`).join('')}</select></label>
   <label class="field" style="margin-top:18px">Panel opacity <span id="opacity-label">${state.prefs.opacity}%</span><input id="opacity" type="range" min="75" max="100" value="${state.prefs.opacity}"></label></section>
   <section class="card wide"><div class="row"><label class="choice"><input id="reduced" type="checkbox" ${state.prefs.reduced_motion?'checked':''}><strong>Reduce motion</strong><small>Turn off interface transitions</small></label><button class="button primary" id="save-appearance">Save appearance</button></div></section></div>`;
 }
 const pages={overview,performance,windows,appearance};
 function render(){
  document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page));
  $('#title').textContent=state.page[0].toUpperCase()+state.page.slice(1);
  $('#content').innerHTML=`<div class="page">${pages[state.page]()}</div>`;
 }
 async function refresh(){try{state.account=await invoke('snapshot');account();render();}catch(e){toast(e.message);}}
 async function init(){
  try{state.prefs=await invoke('preferences');prefs();await refresh();}catch(e){toast(e.message);}
 }
 document.addEventListener('click',async e=>{
  const nav=e.target.closest('[data-page]');if(nav){state.page=nav.dataset.page;render();return;}
  const action=e.target.closest('[data-action]')?.dataset.action;
  try{
   if(action==='desktop'){await invoke('open_desktop');return;}
   if(e.target.closest('#close-button')){await invoke('close_menu');return;}
   if(e.target.closest('#account-button')){const p=$('#account-popover');p.hidden=!p.hidden;$('#account-button').setAttribute('aria-expanded',String(!p.hidden));return;}
   if(e.target.closest('[data-settings]')){await invoke('open_windows_settings',e.target.closest('[data-settings]').dataset.settings);return;}
   if(e.target.closest('#save-appearance')){
    state.prefs=await invoke('save_preferences',{hotkey:$('#hotkey').value,accent:$('#accent').value,opacity:Number($('#opacity').value),reduced_motion:$('#reduced').checked});
    prefs();toast('Appearance saved.');return;
   }
   if(!e.target.closest('.account,.account-popover')){$('#account-popover').hidden=true;$('#account-button').setAttribute('aria-expanded','false');}
  }catch(error){toast(error.message);}
 });
 document.addEventListener('input',e=>{if(e.target.id==='opacity')$('#opacity-label').textContent=e.target.value+'%';});
 document.addEventListener('submit',async e=>{
  if(e.target.id!=='preview-form')return;e.preventDefault();
  try{
   const form=new FormData(e.target);const fps=Number(form.get('fps'));
   if(!Number.isInteger(fps))throw Error('Enter a whole-number frame-rate target.');
   const result=await invoke('preview_performance',form.get('preset'),fps);
   const rows=(result.changes||[]).map(c=>`<div>${escape(c.key)}: ${escape(c.current??'Not set')} → ${escape(c.proposed)}</div>`).join('');
   $('#preview-result').innerHTML=rows||'No supported changes are needed.';
  }catch(error){toast(error.message);}
 });
 document.addEventListener('keydown',e=>{if(e.key==='Escape')invoke('close_menu').catch(error=>toast(error.message));});
 window.SacredOverlay={refresh};
 window.addEventListener('pywebviewready',init);
})();
