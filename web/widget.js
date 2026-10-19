'use strict';
// Widget bar: read-only clock, session timer and enabled-macro count. Click-through window.
(() => {
  const $ = id => document.getElementById(id);
  const clock = ms => { const t = Math.floor(ms / 1000), h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); };
  let state = null, fetchedAt = 0;
  async function poll() {
    try { state = await window.pywebview.api.state(); fetchedAt = Date.now(); } catch (_) { /* app closing or signed out */ }
    const theme = state?.theme;
    if (theme) for (const [k, v] of [['--accent', theme.accent], ['--surface', theme.surface], ['--ink', theme.text_color], ['--muted', theme.muted_color]]) document.documentElement.style.setProperty(k, v);
  }
  function draw() {
    $('clock').textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    if (!state) return;
    const t = state.timer || {}, elapsed = (t.elapsed_ms || 0) + (t.running ? Date.now() - fetchedAt : 0);
    $('timer').textContent = clock(elapsed);
    $('timer-pill').classList.toggle('on', !!t.running);
    $('macros').textContent = state.enabled == null ? '–' : state.enabled;
    $('macro-pill').classList.toggle('on', state.enabled > 0);
  }
  window.addEventListener('pywebviewready', () => { poll(); setInterval(poll, 3000); });
  setInterval(draw, 500);
  draw();
})();
