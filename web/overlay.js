'use strict';
(() => {
 const $=selector=>document.querySelector(selector);
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const THEMES=window.SacredThemes||{};
 const LEGACY={violet:'sacred-violet',blue:'cobalt',amber:'amber'};
 // Mechanics board: only macros the desktop engine actually provides.
 const CATS=[['editing','Editing'],['building','Building'],['movement','Movement'],['utility','Utility']];
 // Companion tools: no game input, just session helpers.
 const TOOLS=[['keybinds','Keybinds'],['loadouts','Loadouts'],['session','Session'],['practice','Practice'],['notes','Notes'],['system','System']];
 const MECH={
  editing:[['drag','Drag Edit'],['single_edit','Single Edit'],['double_edit','Double Edit'],['quick_reset','Quick Reset']],
  building:[['prefire','Pre-fire'],['wall_replace','Wall Replace'],['auto_build','Auto Build'],['floor_cone','Floor + Cone']],
  movement:[['mantle','Mantle Repeat']],
  utility:[['gun_pullout','Weapon Pullout'],['pickup','Fast Pickup']]
 };
 const ICONS={keybinds:'M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z',loadouts:'M12 3 4 7l8 4 8-4z M4 12l8 4 8-4 M4 17l8 4 8-4',session:'M12 21a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17z M12 8v4.5l3 2 M9.5 2.5h5',practice:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9z M12 12h.01',notes:'M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z M8.5 12h7 M8.5 15.5h7 M8.5 8.5h3',system:'M8 7h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z M10 10h4v4h-4z M9.5 3v4 M14.5 3v4 M9.5 17v4 M14.5 17v4 M3 9.5h4 M3 14.5h4 M17 9.5h4 M17 14.5h4',editing:'M4 20h4L19 9l-4-4L4 16z M13.5 6.5l4 4',building:'m12 3 8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12 4 7.5',movement:'M13 2 4 14h7l-1 8 10-13h-7z',utility:'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M10.5 2h3l.6 2.6 2.3 1 2.3-1.4 2.1 2.1-1.4 2.3 1 2.3 2.6.6v3l-2.6.6-1 2.3 1.4 2.3-2.1 2.1-2.3-1.4-2.3 1-.6 2.6h-3l-.6-2.6-2.3-1-2.3 1.4-2.1-2.1 1.4-2.3-1-2.3L2 13.5v-3l2.6-.6 1-2.3-1.4-2.3 2.1-2.1 2.3 1.4 2.3-1z'};
 const svg=(path,cls='ico')=>`<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
 const DEFAULT_PREFS={hotkey:'TAB',accent:'app',opacity:94,reduced_motion:false,size:'wide',position:'center',glass:false,sounds:true,particles:'none',widgets:false};
 const FONTS=window.SacredFonts||{};
 const DRILLS=['Edit course warm-up (10 min)','Box-fight reps','Aim trainer (10 min)','Piece-control drills','Review one replay'];
 // Per-device conveniences only; the overlay works without storage.
 // Saved through the desktop app (the web view runs in private mode, so browser storage resets).
 let saveTimer,canSave=false;
 const store={get(){return {};},set(v){if(!canSave)return;clearTimeout(saveTimer);saveTimer=setTimeout(()=>invoke('save_tools_state',v).catch(()=>{}),400);}};
 const tools={drills:DRILLS.map(t=>({t,done:false})),notes:'',breakOn:false,breakMin:45,day:'',...store.get()};
 const today=new Date().toISOString().slice(0,10);
 if(tools.day!==today){tools.drills=tools.drills.map(d=>({...d,done:false}));tools.day=today;store.set(tools);}
 const timer={running:false,start:0,elapsed:0,nextBreak:0};
 const mini={endsAt:0,label:''};
 const state={page:'home',focus:'editing',collapsed:new Set(),more:null,account:{},appTheme:null,profileData:{available:false,profiles:[]},live:{macros:{}},loadouts:[],pendingLoadout:null,editing:null,prefs:{...DEFAULT_PREFS},draft:null,hardware:null,heavy:[]};
 let toastTimer;
 function toast(message,error=false){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.toggle('error',error);window.SacredSound?.play(error?'error':'success');toastTimer=setTimeout(()=>$('#toast').textContent='',4000);}
 async function invoke(name,...args){if(!window.pywebview?.api)throw Error('Open the Windows application to use the overlay.');return window.pywebview.api[name](...args);}
 function duration(){const l=state.account.license;if(!state.account.signed_in)return 'Sign in from the desktop app';if(l?.permanent)return 'Permanent license';if(!l?.expires_at)return 'License active';const ms=Math.max(0,Number(l.expires_at)*1000-Date.now());return ms?Math.ceil(ms/86400000)+' days remaining':'License expired';}
 function account(){
  const a=state.account;$('#username').textContent=a.signed_in?a.username:'Signed out';
  $('#avatar').textContent=a.signed_in?a.username.slice(0,2).toUpperCase():'S';
  $('#account-button').dataset.tier=String(a.tier||'').toLowerCase();
  $('#license-time').textContent=duration();
  $('#rail-status').textContent=a.signed_in?'Companion ready':'Sign in required';
  $('#account-popover').innerHTML=`<strong>${escape(a.signed_in?a.username:'Sacred Tweaks')}</strong><small>${escape(a.tier||'Account unavailable')} · ${escape(duration())}</small><button data-action="desktop">Open account in desktop app</button>`;
 }
 // Theme: 'app' mirrors the desktop app; otherwise one of the shared themes.
 function palette(prefs){
  if(prefs.accent==='app'&&state.appTheme){const t=state.appTheme;return {accent:t.accent,accent2:THEMES[t.preset]?.[2]||t.accent,surface:t.surface,ink:t.text_color,muted:t.muted_color,glass:t.glass===true};}
  const id=THEMES[prefs.accent]?prefs.accent:LEGACY[prefs.accent]||'sacred-blue';
  const [,accent,accent2,surface,ink,muted]=THEMES[id]||['','#1E90FF','#38BDF8','#0A1220','#EAF2FF','#93A7C4'];
  return {accent,accent2,surface,ink,muted,glass:prefs.glass===true};
 }
 function applyLook(prefs=state.prefs){
  const p=palette(prefs),root=document.documentElement.style,rgb=hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)).join(',');
  root.setProperty('--accent',p.accent);root.setProperty('--accent-2',p.accent2);root.setProperty('--accent-rgb',rgb(p.accent));
  root.setProperty('--surface',p.surface);root.setProperty('--ink',p.ink);root.setProperty('--muted',p.muted);
  root.setProperty('--opacity',String(prefs.opacity/100));
  document.body.classList.toggle('glass',p.glass);
  document.body.dataset.reduced=String(prefs.reduced_motion);
  document.body.dataset.size=prefs.size;
  if(window.SacredSound)window.SacredSound.enabled=prefs.sounds!==false;
  document.documentElement.style.fontFamily=(FONTS[state.appTheme?.font]||FONTS.system||['',''])[1]||'';
  document.documentElement.dataset.preset=prefs.accent==='app'?state.appTheme?.preset||'':prefs.accent;
  window.SacredParticles?.set({style:prefs.particles,density:40});
 }
 function prefs(){applyLook();$('#footer-key').textContent=state.prefs.hotkey+' TO CLOSE';}
 const guides={
  'Mechanics':'Flip a switch to enable or disable a configured macro. The key shows its enable shortcut. Use ⋮ for status and setup. Emergency stop releases every synthetic input.',
  'Profiles & loadouts':'Preview a saved loadout before applying it; applying stops current macros and releases inputs. Saved profiles can be edited here; editing never activates a macro.',
  'Windows settings':'Choose a shortcut, review the Windows page that opens, and return to Fortnite when finished.',
  'Make it yours':'Pick a theme or Match app, then glass, sounds, opacity, motion, hotkey and position. The overlay uses Wide size. Press Save settings.'
 };
 function intro(title,description,extra='',heading=title){return `<div class="intro"><div><h2>${heading}</h2><p>${description}</p><details class="guide"><summary>How to use this page</summary><p>${escape(guides[title])}</p></details></div>${extra}</div>`;}
 const live=kind=>state.live.macros?.[kind];
 function row(kind,name){
  const m=live(kind),on=!!m?.enabled,ready=!!m&&state.account.signed_in,key=m?.config?.toggle||'–',open=state.more===kind;
  return `<div class="mech-row ${on?'on':''} ${ready?'':'idle'}"><span class="mech-name">${escape(name)}</span><label class="mech-switch" title="${ready?(on?'Disable':'Enable'):'Configure in Macro Studio first'}"><input type="checkbox" role="switch" data-mech="${kind}" aria-label="${escape(name)}" ${on?'checked':''} ${ready?'':'disabled'}><i></i></label><span class="mech-key" title="Enable / disable shortcut">${escape(key)}</span><button class="mech-more" data-more="${kind}" aria-label="More for ${escape(name)}" aria-expanded="${open}">⋮</button></div>${open?`<div class="mech-detail"><p>${escape(m?(m.reason||'Ready')+' · shortcut '+key:state.account.signed_in?'Not configured yet. Set binds and timings in Macro Studio.':'Sign in from the desktop app to use mechanics.')}</p><button class="button small" data-action="desktop">Open Macro Studio ↗</button></div>`:''}`;
 }
 const clock=ms=>{const t=Math.floor(ms/1000),h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;return (h?h+':':'')+String(m).padStart(h?2:1,'0')+':'+String(s).padStart(2,'0');};
 const elapsed=()=>timer.elapsed+(timer.running?Date.now()-timer.start:0);
 function toolBody(cat){
  if(cat==='keybinds'){const rows=Object.entries(state.live.macros||{});return rows.length?rows.map(([k,m])=>`<div class="key-sheet"><strong>${escape(k.replaceAll('_',' '))}</strong><div>${['activation','toggle','edit','select','confirm','place'].filter(f=>m.config?.[f]).map(f=>`<span><small>${f}</small><kbd>${escape(m.config[f])}</kbd></span>`).join('')}</div></div>`).join(''):`<p class="tool-empty">${state.account.signed_in?'Configure macros in Macro Studio to see their binds here.':'Sign in to see your binds.'}</p>`;}
  if(cat==='loadouts')return state.loadouts.length?state.loadouts.slice(0,6).map(l=>`<div class="mech-row"><span class="mech-name">${escape(l.name)}</span><span class="mech-key">${Object.keys(l.macros||{}).length}</span><button class="button small" data-loadout="${escape(l.id)}">Preview</button></div>`).join('')+(state.pendingLoadout?`<div class="mech-detail"><p>${escape(state.pendingLoadout.name)}: ${state.pendingLoadout.macros.map(escape).join(' · ')}. Releases inputs; macros start disabled.</p><button class="button small" data-action="cancel-loadout">Cancel</button> <button class="button small primary" data-apply="${escape(state.pendingLoadout.id)}">Apply</button></div>`:''):`<p class="tool-empty">${state.account.signed_in?'Save loadouts in the desktop app to switch them here.':'Sign in to see your loadouts.'}</p>`;
  if(cat==='session')return `<div class="session-clock ${timer.running?'running':''}" id="session-clock">${clock(elapsed())}</div><div class="tool-actions"><button class="button small ${timer.running?'':'primary'}" data-timer="toggle">${timer.running?'Pause':elapsed()?'Resume':'Start session'}</button><button class="button small" data-timer="reset">Reset</button></div><div class="mini-timers">${[1,3,5,10].map(m=>`<button class="button small" data-mini="${m}">${m} min</button>`).join('')}</div><div class="mini-status ${mini.endsAt>Date.now()?'on':''}" id="mini-status">${mini.endsAt>Date.now()?`${escape(mini.label)} · ${clock(mini.endsAt-Date.now())}`:'Quick timer: pick a length'}</div><div class="mech-row"><span class="mech-name">Break reminder</span><label class="mech-switch"><input type="checkbox" role="switch" data-break aria-label="Break reminder" ${tools.breakOn?'checked':''}><i></i></label></div><label class="field">Remind me every<select data-break-min>${[30,45,60,90].map(m=>`<option value="${m}" ${m===tools.breakMin?'selected':''}>${m} minutes</option>`).join('')}</select></label>`;
  if(cat==='practice'){const done=tools.drills.filter(d=>d.done).length;return `<div class="progress" style="--p:${tools.drills.length?done/tools.drills.length*100:0}%"><i></i><span>${done}/${tools.drills.length} today</span></div>${tools.drills.map((d,i)=>`<label class="drill ${d.done?'done':''}"><input type="checkbox" data-drill="${i}" ${d.done?'checked':''}><span class="tick"></span><span class="drill-text">${escape(d.t)}</span><button class="drill-x" data-drill-remove="${i}" aria-label="Remove ${escape(d.t)}">×</button></label>`).join('')}<form class="drill-add" data-drill-add><input name="drill" maxlength="60" placeholder="Add a drill" aria-label="Add a drill"><button class="button small" type="submit">Add</button></form>`;}
  if(cat==='notes')return `<textarea class="notes" data-notes maxlength="4000" placeholder="Rotations, settings to try, things to practise…" aria-label="Session notes">${escape(tools.notes)}</textarea><p class="tool-empty">Saved on this PC as you type.</p>`;
  if(cat==='system'){const hw=state.hardware,d=hw?.display||{};return (hw?[['CPU',hw.cpu],['GPU',hw.gpu],['Memory',hw.ram_gb?hw.ram_gb+' GB':''],['Display',d.width?`${d.width}×${d.height} · ${d.refresh_hz||'—'} Hz`:'']].map(([k,v])=>`<div class="spec"><span>${k}</span><strong title="${escape(v||'Unavailable')}">${escape(v||'Unavailable')}</strong></div>`).join(''):`<p class="tool-empty">${state.account.signed_in?'Loading device details…':'Sign in to see device details.'}</p>`)+`<div class="tool-actions"><button class="button small" data-settings="game_mode">Game Mode ↗</button><button class="button small" data-settings="display">Display ↗</button></div>`;}
  return '';
 }
 setInterval(()=>{
  const el=document.getElementById('session-clock');if(el)el.textContent=clock(elapsed());
  const ms=document.getElementById('mini-status');if(mini.endsAt){const left=mini.endsAt-Date.now();if(left<=0){mini.endsAt=0;toast(`${mini.label} finished.`);if(ms){ms.textContent='Quick timer: pick a length';ms.classList.remove('on');}}else if(ms)ms.textContent=`${mini.label} · ${clock(left)}`;}
  if(timer.running&&tools.breakOn&&elapsed()>=timer.nextBreak){timer.nextBreak+=tools.breakMin*60000;toast(`Break time: ${tools.breakMin} minutes played. Stretch and hydrate.`);}
 },1000);
 function home(){
  const enabled=Object.values(state.live.macros||{}).filter(m=>m.enabled).length;
  const status=`<div class="board-status"><span class="pill ${enabled?'hot':''}"><span class="pulse"></span>${enabled} enabled · ${state.live.foreground?'Fortnite focused':'Waiting for Fortnite'}</span><button class="button danger" data-action="stop-macros">Emergency stop</button></div>`;
  const signed=state.account.signed_in?'':`<div class="banner"><strong>Sign in needed</strong><span>Open the Sacred Tweaks desktop app and sign in to use mechanics.</span><button class="button small" data-action="desktop">Open desktop app ↗</button></div>`;
  const cols=CATS.map(([cat,label])=>{
   const items=MECH[cat],count=items.filter(([k])=>live(k)?.enabled).length,collapsed=state.collapsed.has(cat);
   return `<section class="mech-col ${collapsed?'collapsed':''} ${state.focus===cat?'focus':''}" id="col-${cat}"><header>${svg(ICONS[cat])}<h3>${label}</h3><span class="count">${count}/${items.length}</span>${count?`<button class="col-off" data-alloff="${cat}" title="Disable every macro in ${label}">All off</button>`:''}<button class="col-toggle" data-collapse="${cat}" aria-expanded="${!collapsed}" aria-label="${collapsed?'Expand':'Collapse'} ${label}">${svg('m6 15 6-6 6 6','chev')}</button></header><div class="mech-list">${items.map(([k,n])=>row(k,n)).join('')}</div></section>`;
  }).join('')+TOOLS.map(([cat,label])=>{const collapsed=state.collapsed.has(cat);return `<section class="mech-col tool-col tool-${cat} ${collapsed?'collapsed':''} ${state.focus===cat?'focus':''}" id="col-${cat}"><header>${svg(ICONS[cat])}<h3>${label}</h3><button class="col-toggle" data-collapse="${cat}" aria-expanded="${!collapsed}" aria-label="${collapsed?'Expand':'Collapse'} ${label}">${svg('m6 15 6-6 6 6','chev')}</button></header><div class="mech-list">${toolBody(cat)}</div></section>`;}).join('');
  return intro('Mechanics','Flip a switch to enable a configured macro. Keys show each enable shortcut.',status,'Your loadout')+signed+(state.heavy.length?`<div class="banner heavy"><strong>Background apps running</strong><span>${state.heavy.slice(0,3).map(a=>escape(a.name)+' ('+escape(a.memory_mb)+' MB)').join(' · ')}. Closing them can free CPU and memory.</span><button class="button small" data-action="dismiss-heavy">Dismiss</button></div>`:'')+`<form class="quick-note" data-quick-note><span class="qn-icon" aria-hidden="true">✎</span><input name="note" maxlength="200" placeholder="Quick note to your Match journal… (Ctrl+N)" aria-label="Quick note"><button class="button small primary" type="submit">Save note</button></form>`+`<div class="board">${cols}</div><div class="notice">Enabled macros respond only while Fortnite has focus. Configure binds, timings and edit paths in Macro Studio. Gameplay automation breaks Epic’s rules; use at your own risk.</div>`;
 }
 function macros(){
  const data=state.profileData;
  const loadouts=state.loadouts.length?state.loadouts.map(l=>`<article class="profile-card"><div class="profile-mark">◈</div><div class="profile-copy"><h3>${escape(l.name)}</h3><p>${Object.keys(l.macros||{}).length} configured macros · appearance</p></div><button class="button" data-loadout="${escape(l.id)}">Preview</button></article>`).join(''):'<div class="empty-state"><strong>No loadouts yet</strong><p>Create one from the main app, then select it here.</p></div>';
  const preview=state.pendingLoadout?`<section class="card wide accent"><div class="label">APPLY PREVIEW</div><h3>${escape(state.pendingLoadout.name)}</h3><p>${state.pendingLoadout.macros.map(escape).join(' · ')}. This releases current inputs and starts every macro disabled.</p><div class="row end"><button class="button" data-action="cancel-loadout">Cancel</button><button class="button primary" data-apply="${escape(state.pendingLoadout.id)}">Apply loadout</button></div></section>`:'';
  const rows=data.profiles?.length?data.profiles.map(p=>`<article class="profile-card"><div class="profile-mark">▤</div><div class="profile-copy"><h3>${escape(p.name)}</h3><p>${escape(p.kind.replaceAll('_',' '))} · Saved profile · Inactive</p></div><button class="button" data-edit-profile="${escape(p.id)}">View & edit</button></article>`).join(''):
   `<div class="empty-state"><strong>${data.available?'No saved profiles yet':'Profiles unavailable'}</strong><p>${data.available?'Save a profile in the main desktop app to see it here.':'Sign in to see your saved profiles.'}</p></div>`;
  const selected=data.profiles?.find(p=>p.id===state.editing);
  const editor=selected?`<section class="card wide accent"><div class="row"><div><div class="label">PROFILE EDITOR</div><h3>${escape(selected.kind.replaceAll('_',' '))}</h3></div><button class="button" data-action="cancel-edit">Close editor</button></div><form id="profile-form"><label class="field">Profile name<input name="profile-name" value="${escape(selected.name)}" maxlength="80" required></label><div class="profile-fields">${Object.entries(selected.config).map(([key,value])=>`<label class="field">${escape(key.replaceAll('_',' '))}${typeof value==='boolean'?`<select data-config-key="${escape(key)}"><option value="true" ${value?'selected':''}>On</option><option value="false" ${!value?'selected':''}>Off</option></select>`:`<input data-config-key="${escape(key)}" ${typeof value==='number'?'type="number" step="any"':'type="text" maxlength="80"'} value="${escape(value)}" required>`}</label>`).join('')}</div><p>Changes save to this profile. They do not load or enable a macro. Use Macro Studio in the main app to activate one.</p><button class="button primary" type="submit">Save profile</button></form></section>`:'';
  return intro('Profiles & loadouts','Switch setups and edit saved configurations.')+
   `<div class="grid"><section class="card wide"><div class="row"><div><div class="label">LOADOUTS</div><h3>Pick a setup</h3></div><button class="button" data-action="desktop">Open full app ↗</button></div><div class="profile-list">${loadouts}</div></section>${preview}<section class="card wide"><div class="row"><div><div class="label">MACRO PROFILES</div><h3>Your saved configurations</h3></div><button class="button" data-action="desktop">Open Macro Studio ↗</button></div><div class="profile-list">${rows}</div></section>${editor}</div>`;
 }
 function windows(){
  return intro('Windows settings','Open supported system pages to review each change yourself.')+
   `<div class="grid"><section class="card wide"><div class="label">SYSTEM SHORTCUTS</div><div class="options">
   ${[['game_mode','Game Mode'],['capture','Capture settings'],['graphics','Graphics preference'],['display','Display settings']].map(([id,label])=>`<button class="button tile" data-settings="${id}">${label} ↗</button>`).join('')}</div></section>
   <section class="card wide"><div class="notice">Opening Windows Settings switches focus away from Fortnite and closes this menu. Changes on those pages are made by you. Windowed Fullscreen is recommended; exclusive fullscreen may cover desktop windows.</div></section></div>`;
 }
 function appearance(){
  const d=state.draft||state.prefs, follow=d.accent==='app', current=THEMES[d.accent]?d.accent:LEGACY[d.accent]||d.accent;
  const swatch=(id,name,a,a2,s,t,special)=>`<label class="theme-swatch ${special?'special':''}" style="--sw-accent:${a};--sw-accent-2:${a2};--sw-surface:${s};--sw-text:${t}"><input type="radio" name="ov-theme" value="${id}" ${id===current?'checked':''}><span class="theme-preview" aria-hidden="true"><i></i><i></i><i></i></span><span class="theme-name">${escape(name)}</span>${special?'<span class="special-badge">Special Theme</span>':''}</label>`;
  const app=state.appTheme;
  const gallery=swatch('app','Match app',app?.accent||'#1E90FF',app?.accent||'#38BDF8',app?.surface||'#0A1220',app?.text_color||'#EAF2FF')+Object.entries(THEMES).map(([id,[n,a,a2,s,t,,sp]])=>swatch(id,n,a,a2,s,t,sp)).join('');
  const sw=(id,title,text,on,disabled=false)=>`<label class="choice switch-row"><span><strong>${title}</strong><small>${text}</small></span><span class="mech-switch"><input id="${id}" type="checkbox" role="switch" ${on?'checked':''} ${disabled?'disabled':''}><i></i></span></label>`;
  return intro('Make it yours','Customize the companion exactly like the desktop app.')+
   `<div class="grid"><section class="card wide"><div class="row"><div><div class="label">THEME</div><h3>${follow?'Following the desktop app':'Companion theme'}</h3></div><span class="pill">${Object.keys(THEMES).length+1} options</span></div><div class="theme-grid" role="radiogroup" aria-label="Overlay theme">${gallery}</div></section>
   <section class="card"><div class="label">EFFECTS</div><div class="stack">${sw('glass','Liquid glass',follow?'Follows the desktop app while Match app is selected.':'Frosted, translucent panels.',follow?palette(d).glass:d.glass,follow)}${sw('sounds','Interface sounds','Clicks, toggles and confirmations.',d.sounds!==false)}${sw('reduced','Reduce motion','Turn off transitions and ambient motion.',d.reduced_motion)}${sw('widgets','Widget bar','Clock, session timer and macro count at the top of Fortnite. Click-through; never takes focus.',d.widgets===true)}</div>
   <label class="field" style="margin-top:16px">Background particles<select id="particles">${Object.entries(window.SacredParticles?.styles||{none:'None'}).map(([k,n])=>`<option value="${k}" ${k===d.particles?'selected':''}>${n}</option>`).join('')}</select></label>
   <p class="hint">Off by default to keep the overlay light over Fortnite.</p>
   <label class="field" style="margin-top:16px">Panel opacity <span id="opacity-label">${d.opacity}%</span><input id="opacity" type="range" min="75" max="100" value="${d.opacity}"></label></section>
   <section class="card"><div class="label">INPUT & LAYOUT</div><label class="field">Open / close hotkey<select id="hotkey">${['TAB','F6','F7','F9','F10','F11'].map(k=>`<option value="${k}" ${k===d.hotkey?'selected':''}>${k}</option>`).join('')}</select></label>
   <p class="hint">The hotkey still reaches the game when this window is hidden. Choose an unused key if Tab opens your inventory.</p>
   <label class="field" style="margin-top:14px">Panel position<select id="position">${[['center','Center'],['left','Left'],['right','Right']].map(([k,n])=>`<option value="${k}" ${k===d.position?'selected':''}>${n}</option>`).join('')}</select></label>
   <p class="hint">Panel size: Wide. The window fits within Fortnite’s available screen area.</p></section>
   <section class="card wide"><div class="label">SETTING PROFILES</div><h3>Save and switch companion setups</h3><p>Keep a look per game or situation, for example Ranked or Creative. Applying a profile changes these settings only.</p><div class="profile-chips">${(tools.profiles||[]).map((p,i)=>`<span class="chip-btn"><button class="button small" data-apply-profile="${i}">${escape(p.name)}</button><button class="chip-x" data-delete-profile="${i}" aria-label="Delete ${escape(p.name)}">×</button></span>`).join('')||'<span class="hint">No saved profiles yet.</span>'}</div><form class="drill-add" data-profile-save style="margin-top:10px"><input name="name" maxlength="30" placeholder="Profile name, e.g. Ranked" aria-label="Profile name"><button class="button small" type="submit">Save current</button></form></section>
   <section class="card wide"><div class="row end"><button class="button" id="reset-appearance">Reset to default</button><button class="button primary" id="save-appearance">Save settings</button></div></section></div>`;
 }
 const pages={home,macros,windows,appearance};
 const titles={home:'Mechanics',macros:'Profiles',windows:'Windows',appearance:'Settings'};
 function render(){
  document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page&&(!b.dataset.cat||b.dataset.cat===state.focus)));
  $('#title').textContent=titles[state.page];
  $('#content').innerHTML=`<div class="page page-${state.page}">${pages[state.page]()}</div>`;
 }
 // Each source fails independently (signed out, offline); the page always renders.
 async function refresh(){
  const [snap,profiles,liveData,loadouts,theme]=await Promise.allSettled(['snapshot','macro_profiles','macro_status','loadouts','app_theme'].map(name=>invoke(name)));
  state.account=snap.status==='fulfilled'?snap.value:{signed_in:false};canSave=!!state.account.signed_in;
  state.profileData=profiles.status==='fulfilled'?profiles.value:{available:false,profiles:[]};
  state.live=liveData.status==='fulfilled'?liveData.value:{macros:{}};
  state.loadouts=loadouts.status==='fulfilled'?loadouts.value.loadouts||[]:[];
  state.appTheme=theme.status==='fulfilled'?theme.value:null;
  applyLook(state.draft||state.prefs);account();render();
  if(state.account.signed_in&&!tools.loaded)invoke('tools_state').then(saved=>{Object.assign(tools,saved||{},{loaded:true});if(tools.day!==today){tools.drills=(tools.drills||[]).map(d=>({...d,done:false}));tools.day=today;}if(state.page==='home')render();}).catch(()=>{});
  if(state.account.signed_in)invoke('heavy_apps').then(r=>{state.heavy=r.heavy||[];if(state.page==='home')render();}).catch(()=>{});
  if(state.account.signed_in&&!state.hardware)invoke('hardware').then(hw=>{state.hardware=hw;if(state.page==='home')render();}).catch(()=>{});
  const failed=[snap,profiles,liveData,loadouts].find(r=>r.status==='rejected');
  if(failed&&state.account.signed_in)toast(failed.reason.message,true);
 }
 async function resetLayout(){state.prefs=await invoke('save_preferences',{...state.prefs,size:'wide',position:'center'});prefs();render();toast('Overlay position reset.');}
 async function init(){
  try{state.prefs={...state.prefs,...await invoke('preferences')};}catch(e){toast(e.message,true);}
  prefs();await refresh();
 }
 function readDraft(){
  const chosen=document.querySelector('input[name="ov-theme"]:checked')?.value||state.prefs.accent;
  return {...state.prefs,accent:chosen,hotkey:$('#hotkey').value,position:$('#position').value,opacity:Number($('#opacity').value),reduced_motion:$('#reduced').checked,sounds:$('#sounds').checked,particles:$('#particles').value,widgets:$('#widgets').checked,glass:chosen==='app'?state.prefs.glass:$('#glass').checked,size:'wide'};
 }
 function closePopover(){$('#account-popover').hidden=true;$('#account-button').setAttribute('aria-expanded','false');}
 function leavePage(page){if(state.draft){state.draft=null;applyLook();}state.page=page;state.more=null;}
 document.addEventListener('click',async e=>{
  const nav=e.target.closest('[data-page]');
  if(nav){leavePage(nav.dataset.page);if(nav.dataset.cat){state.focus=nav.dataset.cat;state.collapsed.delete(nav.dataset.cat);}render();if(nav.dataset.cat){const c=$('#content'),col=$('#col-'+nav.dataset.cat);if(col)c.scrollTo({top:col.getBoundingClientRect().top-c.getBoundingClientRect().top+c.scrollTop-12,behavior:'smooth'});}return;}
  const miniBtn=e.target.closest('[data-mini]');if(miniBtn){const m=Number(miniBtn.dataset.mini);mini.endsAt=Date.now()+m*60000;mini.label=`${m}-minute timer`;render();return;}
  const timerBtn=e.target.closest('[data-timer]');if(timerBtn){if(timerBtn.dataset.timer==='reset'){Object.assign(timer,{running:false,elapsed:0,start:0});}else if(timer.running){timer.elapsed=elapsed();timer.running=false;}else{timer.start=Date.now();timer.running=true;if(!timer.nextBreak||timer.nextBreak<=timer.elapsed)timer.nextBreak=timer.elapsed+tools.breakMin*60000;}invoke('set_timer',timer.running,Math.min(864e5,timer.elapsed)).catch(()=>{});render();return;}
  const drillX=e.target.closest('[data-drill-remove]');if(drillX){e.preventDefault();tools.drills.splice(Number(drillX.dataset.drillRemove),1);store.set(tools);render();return;}
  const allOff=e.target.closest('[data-alloff]');if(allOff){allOff.disabled=true;try{for(const [kind] of MECH[allOff.dataset.alloff])if(live(kind)?.enabled)await invoke('toggle_macro',kind,false);await refresh();toast('Category disabled.');}catch(error){toast(error.message,true);await refresh();}return;}
  const collapse=e.target.closest('[data-collapse]');if(collapse){const c=collapse.dataset.collapse;state.collapsed.has(c)?state.collapsed.delete(c):state.collapsed.add(c);render();return;}
  const more=e.target.closest('[data-more]');if(more){state.more=state.more===more.dataset.more?null:more.dataset.more;render();$(`[data-more="${more.dataset.more}"]`)?.focus();return;}
  const edit=e.target.closest('[data-edit-profile]');if(edit){state.editing=Number(edit.dataset.editProfile);render();$('#profile-form')?.scrollIntoView({block:'nearest'});return;}
  const action=e.target.closest('[data-action]')?.dataset.action;
  try{
   const loadout=e.target.closest('[data-loadout]');if(loadout){state.pendingLoadout=await invoke('preview_loadout',loadout.dataset.loadout);render();return;}
   const apply=e.target.closest('[data-apply]');if(apply){await invoke('apply_loadout',apply.dataset.apply);state.pendingLoadout=null;await refresh();toast('Loadout applied. Macros remain disabled.');return;}
   if(action==='stop-macros'){await invoke('emergency_stop');await refresh();toast('All macros stopped. Inputs released.');return;}
   if(action==='cancel-edit'){state.editing=null;render();return;}
   if(action==='dismiss-heavy'){state.heavy=[];render();return;}
   if(action==='cancel-loadout'){state.pendingLoadout=null;render();return;}
   if(e.target.closest('#reset-layout')){await resetLayout();return;}
   if(action==='desktop'){await invoke('open_desktop');return;}
   if(e.target.closest('#close-button')){window.SacredSound?.play('close');await invoke('close_menu');return;}
   if(e.target.closest('#account-button')){const p=$('#account-popover');p.hidden=!p.hidden;$('#account-button').setAttribute('aria-expanded',String(!p.hidden));return;}
   if(e.target.closest('[data-settings]')){await invoke('open_windows_settings',e.target.closest('[data-settings]').dataset.settings);return;}
   const applyProfile=e.target.closest('[data-apply-profile]');if(applyProfile){const p=(tools.profiles||[])[Number(applyProfile.dataset.applyProfile)];if(p){state.prefs=await invoke('save_preferences',{...DEFAULT_PREFS,...p.prefs,size:'wide'});state.draft=null;prefs();render();toast(`Applied “${p.name}”.`);}return;}
   const delProfile=e.target.closest('[data-delete-profile]');if(delProfile){tools.profiles.splice(Number(delProfile.dataset.deleteProfile),1);store.set(tools);render();return;}
   if(e.target.closest('#save-appearance')){state.prefs=await invoke('save_preferences',readDraft());state.draft=null;prefs();render();toast('Settings saved.');return;}
   if(e.target.closest('#reset-appearance')){state.prefs=await invoke('save_preferences',{...DEFAULT_PREFS});state.draft=null;prefs();render();toast('Settings reset.');return;}
   if(!e.target.closest('.account,.account-popover'))closePopover();
  }catch(error){toast(error.message,true);}
 });
 document.addEventListener('change',async e=>{
  if(e.target.matches('[data-break]')){tools.breakOn=e.target.checked;store.set(tools);timer.nextBreak=elapsed()+tools.breakMin*60000;return;}
  if(e.target.matches('[data-break-min]')){tools.breakMin=Number(e.target.value);store.set(tools);timer.nextBreak=elapsed()+tools.breakMin*60000;return;}
  if(e.target.matches('[data-drill]')){const d=tools.drills[Number(e.target.dataset.drill)];if(d){d.done=e.target.checked;store.set(tools);render();if(tools.drills.every(x=>x.done))toast('All drills done today. Nice work.');}return;}
  const mech=e.target.closest('[data-mech]');
  if(mech){
   mech.disabled=true;
   try{await invoke('toggle_macro',mech.dataset.mech,mech.checked);await refresh();}
   catch(error){mech.checked=!mech.checked;mech.disabled=false;toast(error.message,true);}
   return;
  }
  // Settings preview live; nothing is stored until Save settings.
  if(state.page==='appearance'&&e.target.closest('.page-appearance')){state.draft=readDraft();applyLook(state.draft);if(e.target.name==='ov-theme')render();}
 });
 document.addEventListener('submit',async e=>{
  if(e.target.matches('[data-quick-note]')){e.preventDefault();const input=e.target.elements.note;try{await invoke('quick_note',input.value);input.value='';toast('Saved to your Match journal.');}catch(error){toast(error.message,true);}return;}
  if(e.target.matches('[data-profile-save]')){e.preventDefault();const name=e.target.elements.name.value.trim().slice(0,30);if(!name)return;tools.profiles=(tools.profiles||[]).filter(p=>p.name!==name).concat({name,prefs:{...state.prefs}}).slice(-8);store.set(tools);render();toast(`Saved “${name}”.`);return;}
  if(e.target.matches('[data-drill-add]')){e.preventDefault();const text=e.target.elements.drill.value.trim().slice(0,60);if(text&&tools.drills.length<20){tools.drills.push({t:text,done:false});store.set(tools);render();$('[data-drill-add] input')?.focus();}return;}
  if(e.target.id!=='profile-form')return;
  e.preventDefault();
  const selected=state.profileData.profiles.find(p=>p.id===state.editing);
  if(!selected)return;
  const config={...selected.config};
  for(const element of e.target.querySelectorAll('[data-config-key]')){
   const key=element.dataset.configKey;
   config[key]=typeof config[key]==='boolean'?element.value==='true':typeof config[key]==='number'?Number(element.value):element.value;
   if(typeof config[key]==='number'&&!Number.isFinite(config[key])){toast('Enter a valid number.',true);return;}
  }
  const button=e.target.querySelector('button[type=submit]');button.disabled=true;
  try{await invoke('save_macro_profile',selected.id,e.target.elements['profile-name'].value,config);state.editing=null;await refresh();toast('Profile saved. Macro remains inactive.');}
  catch(error){toast(error.message,true);}finally{button.disabled=false;}
 });
 document.addEventListener('input',e=>{if(e.target.matches('[data-notes]')){tools.notes=e.target.value;store.set(tools);return;}if(e.target.id==='opacity'){$('#opacity-label').textContent=e.target.value+'%';state.draft=readDraft();applyLook(state.draft);}});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!$('#account-popover').hidden){closePopover();$('#account-button').focus();return;}if(state.more){state.more=null;render();return;}window.SacredSound?.play('close');invoke('close_menu').catch(error=>toast(error.message,true));}if(e.ctrlKey&&!e.shiftKey&&e.key.toLowerCase()==='n'){e.preventDefault();if(state.page!=='home'){state.page='home';render();}$('[data-quick-note] input')?.focus();}if(e.ctrlKey&&e.shiftKey&&e.key==='0'){e.preventDefault();resetLayout().catch(error=>toast(error.message,true));}});
 window.SacredOverlay={refresh,opened:()=>window.SacredSound?.play('open')};
 applyLook();account();render();
 if(window.pywebview?.api)init();else window.addEventListener('pywebviewready',init);
})();
